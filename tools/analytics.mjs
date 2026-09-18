// Prove what the Google Analytics loader does, in a browser-shaped DOM.
//
// `homeroom.analytics` adds GA4 to the published pages after rendering (owner
// decision, 2026-09-17). `make analytics-gate` runs it over a copy of the fixture
// build, and this reads that copy: its `analytics.js`, and one page of each shape
// (the landing page, a school page in each language, a county page, an ask page).
//
// For each scenario the loader is run in jsdom against a stubbed navigator,
// location and storage, and the result is read back:
//
//   * served from homeroom.chelseakr.com, no signal: exactly one gtag.js script,
//     the Consent Mode v2 defaults and the config in order, one page view whose
//     address is the path plus utm_* only;
//   * Global Privacy Control, each Do Not Track form, the stored opt-out, and any
//     other host: no dataLayer, no script, no kill switch -- nothing;
//   * the footer button: opts out (flag stored, cookies removed, label and
//     status change), opts back in (GA starts), in both languages;
//   * axe finds nothing on each page with the button rendered.
//
// Then the negative controls: the GPC guard and the host guard are removed from a
// copy of the loader, the removal is asserted to have happened exactly once, and
// the same scenario must now see GA load. A harness that cannot see a missing
// guard would pass a loader without one, so it has to prove it can.
//
// Usage: node tools/analytics.mjs <site-directory-with-analytics-added>

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";
import axe from "axe-core";

const site = process.argv[2];
if (!site) {
  console.error("usage: node tools/analytics.mjs <site-directory>");
  process.exit(2);
}
const loaderPath = join(site, "analytics.js");
if (!existsSync(loaderPath)) {
  console.error(`no ${loaderPath}; run python -m homeroom.analytics over the tree first`);
  process.exit(2);
}
const LOADER = readFileSync(loaderPath, "utf8");
const ID = LOADER.match(/var ID = "(G-[A-Z0-9]+)";/)?.[1];
if (!ID) {
  console.error("analytics.js names no measurement ID");
  process.exit(2);
}
const HOST = "homeroom.chelseakr.com";

function firstPage(dir, suffix) {
  const found = readdirSync(join(site, dir))
    .filter((name) => name.endsWith(suffix))
    .sort()[0];
  if (!found) throw new Error(`no ${suffix} page in ${dir || "."}`);
  return join(dir, found);
}
const PAGES = {
  landing: "index.html",
  schoolEn: firstPage("", ".en.html"),
  schoolEs: firstPage("", ".es.html"),
  county: firstPage("county", ".en.html"),
  ask: firstPage("ask", ".es.html"),
};

let failures = 0;
function check(name, ok, detail = "") {
  if (!ok) failures += 1;
  console.log(`${ok ? "pass" : "FAIL"}  ${name}${ok || !detail ? "" : ` -- ${detail}`}`);
}

/** One page load with the loader run in it. */
function visit(page, { host = HOST, search = "", gpc, dnt, dntWhere = "navigator", stored, blockStorage, loader = LOADER } = {}) {
  const html = readFileSync(join(site, page), "utf8");
  const console_ = new VirtualConsole();
  console_.on("jsdomError", (error) => {
    if (!/getContext\(\) method/.test(error.message)) console.error(error.message);
  });
  const dom = new JSDOM(html, {
    url: `https://${host}/${page}${search}`,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole: console_,
  });
  const { window } = dom;
  if (gpc !== undefined) Object.defineProperty(window.navigator, "globalPrivacyControl", { value: gpc });
  if (dnt !== undefined) {
    const target = dntWhere === "window" ? window : window.navigator;
    Object.defineProperty(target, dntWhere === "ms" ? "msDoNotTrack" : "doNotTrack", { value: dnt });
  }
  if (stored) window.localStorage.setItem("homeroom.chelseakr.com:analytics-opt-out", "1");
  if (blockStorage) {
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new window.DOMException("blocked", "SecurityError");
      },
    });
  }
  window.document.cookie = "_ga=GA1.1.1.1; path=/";
  window.document.cookie = `_ga_${ID.slice(2)}=GS1.1.1; path=/`;
  window.eval(loader);
  return dom;
}

function layer(dom) {
  return (dom.window.dataLayer ?? []).map((entry) => JSON.parse(JSON.stringify(Array.from(entry))));
}
function gtagScripts(dom) {
  return Array.from(dom.window.document.querySelectorAll('script[src*="googletagmanager.com"]'));
}
function nothingLoaded(dom) {
  return (
    dom.window.dataLayer === undefined &&
    gtagScripts(dom).length === 0 &&
    Object.getOwnPropertyDescriptor(dom.window, `ga-disable-${ID}`) === undefined
  );
}

// ---- Loads, with the agreed configuration ------------------------------------

{
  const dom = visit(PAGES.schoolEn, { search: "?utm_source=flyer&student=Ada" });
  const commands = layer(dom);
  const scripts = gtagScripts(dom);
  check("production host, no signal: one async gtag.js for the ID", scripts.length === 1 && scripts[0].async && scripts[0].src === `https://www.googletagmanager.com/gtag/js?id=${ID}`);
  const [regional, global, redaction, js, config, set, event] = commands;
  check("consent: EEA/UK/CH analytics denied, ads denied", regional?.[0] === "consent" && regional[2].analytics_storage === "denied" && regional[2].ad_user_data === "denied" && regional[2].region.includes("DE") && regional[2].region.includes("GB") && regional[2].region.includes("CH") && !regional[2].region.includes("US"));
  check("consent: analytics granted elsewhere, ads still denied", global?.[2].analytics_storage === "granted" && global[2].ad_storage === "denied" && global[2].ad_personalization === "denied");
  check("ads_data_redaction then js", redaction?.[1] === "ads_data_redaction" && js?.[0] === "js");
  check("config: signals and ad personalization off, manual page view", config?.[0] === "config" && config[1] === ID && config[2].allow_google_signals === false && config[2].allow_ad_personalization_signals === false && config[2].send_page_view === false);
  check("one page view, address = path + utm only", set?.[0] === "set" && set[1].page_location === `https://${HOST}/${PAGES.schoolEn}?utm_source=flyer` && event?.[1] === "page_view" && commands.length === 7, JSON.stringify(set));
  check("the kill switch reads the opt-out live", dom.window[`ga-disable-${ID}`] === false);
  check("cookies left alone when not opted out", dom.window.document.cookie.includes("_ga="));
  dom.window.close();
}

// ---- Loads nothing ------------------------------------------------------------

for (const [label, options] of [
  ["Global Privacy Control", { gpc: true }],
  ["Do Not Track (navigator)", { dnt: "1" }],
  ['Do Not Track "yes"', { dnt: "yes" }],
  ["Do Not Track (window)", { dnt: "1", dntWhere: "window" }],
  ["Do Not Track (msDoNotTrack)", { dnt: "1", dntWhere: "ms" }],
  ["the stored opt-out", { stored: true }],
  ["another host (a fixture or preview)", { host: "homeroom.example" }],
  ["localhost", { host: "localhost" }],
]) {
  const dom = visit(PAGES.schoolEs, options);
  const w = dom.window;
  const landed =
    (options.gpc === undefined || w.navigator.globalPrivacyControl === true) &&
    (options.dnt === undefined || [w.navigator.doNotTrack, w.doNotTrack, w.navigator.msDoNotTrack].includes(options.dnt)) &&
    (!options.stored || w.localStorage.getItem("homeroom.chelseakr.com:analytics-opt-out") === "1") &&
    (!options.host || w.location.hostname === options.host);
  check(`${label}: the setup took effect`, landed);
  check(`${label}: nothing loads`, nothingLoaded(dom), JSON.stringify(layer(dom)).slice(0, 200));
  if (options.stored || options.gpc || options.dnt) {
    check(`${label}: this site's GA cookies removed`, !/(^|; )_ga=/.test(w.document.cookie) && !w.document.cookie.includes(`_ga_${ID.slice(2)}=`));
  }
  dom.window.close();
}

// ---- The button -----------------------------------------------------------------

for (const [page, lang, optOut, optIn, off] of [
  [PAGES.schoolEn, "en", "Opt out of analytics", "Opt back in", "Analytics is off in this browser."],
  [PAGES.schoolEs, "es", "Desactivar las analíticas", "Volver a activarlas", "Las analíticas están desactivadas en este navegador."],
  [PAGES.county, "en", "Opt out of analytics", "Opt back in", "Analytics is off in this browser."],
  [PAGES.ask, "es", "Desactivar las analíticas", "Volver a activarlas", "Las analíticas están desactivadas en este navegador."],
]) {
  const dom = visit(page);
  const d = dom.window.document;
  const buttons = d.querySelectorAll(".analytics-opt-out button");
  check(`${page}: one button, labelled in ${lang}`, buttons.length === 1 && buttons[0].textContent === optOut, buttons[0]?.textContent);
  buttons[0].click();
  check(`${page}: opting out stores the flag and relabels`, dom.window.localStorage.getItem("homeroom.chelseakr.com:analytics-opt-out") === "1" && buttons[0].textContent === optIn && d.querySelector(".analytics-opt-out [role=status]").textContent === off);
  check(`${page}: opting out removes the GA cookies and stops hits`, !/(^|; )_ga=/.test(d.cookie) && dom.window[`ga-disable-${ID}`] === true);
  buttons[0].click();
  check(`${page}: opting back in clears the flag`, dom.window.localStorage.getItem("homeroom.chelseakr.com:analytics-opt-out") === null && buttons[0].textContent === optOut);
  dom.window.close();
}

{
  const dom = visit(PAGES.schoolEn, { stored: true });
  const button = dom.window.document.querySelector(".analytics-opt-out button");
  check("a later page reads the stored choice", button?.textContent === "Opt back in" && nothingLoaded(dom));
  button.click();
  check("opting back in on a page where GA never loaded starts it", gtagScripts(dom).length === 1 && layer(dom).some((c) => c[0] === "event" && c[1] === "page_view"));
  dom.window.close();
}

{
  const dom = visit(PAGES.landing);
  const buttons = dom.window.document.querySelectorAll(".analytics-opt-out button");
  const sections = Array.from(buttons).map((b) => b.closest("[lang]").getAttribute("lang"));
  check("landing: the disclosure carries a button in each language", buttons.length === 2 && sections.join() === "en,es" && buttons[1].textContent === "Desactivar las analíticas");
  check("landing: both disclosures are there", Boolean(dom.window.document.getElementById("privacy-en")) && Boolean(dom.window.document.getElementById("privacy-es")));
  dom.window.close();
}

{
  const dom = visit(PAGES.schoolEn, { blockStorage: true });
  check("storage blocked: no button, since the choice could not be kept", dom.window.document.querySelectorAll(".analytics-opt-out button").length === 0 && dom.window.document.querySelector(".analytics-opt-out").hidden === true);
  dom.window.close();
}

// ---- Accessibility of what the loader adds ---------------------------------------

for (const page of Object.values(PAGES)) {
  const dom = visit(page);
  dom.window.eval(axe.source);
  const results = await dom.window.axe.run(dom.window.document, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
    resultTypes: ["violations"],
  });
  const violations = results.violations.filter((v) => v.id !== "color-contrast");
  check(`${page}: axe finds nothing with the button rendered`, violations.length === 0, violations.map((v) => v.id).join(", "));
  dom.window.close();
}

// ---- Negative controls: the harness must see a missing guard ---------------------

for (const [label, guard, options] of [
  ["GPC guard", "    if (n.globalPrivacyControl === true) return true;\n", { gpc: true }],
  ["host guard", "|| w.location.hostname !== HOST ", { host: "homeroom.example" }],
]) {
  const count = LOADER.split(guard).length - 1;
  check(`negative control (${label}): the guard is in the loader exactly once`, count === 1, `found ${count}`);
  const sabotaged = LOADER.replace(guard, "");
  check(`negative control (${label}): the removal landed`, sabotaged !== LOADER && !sabotaged.includes(guard));
  const dom = visit(PAGES.schoolEn, { ...options, loader: sabotaged });
  check(`negative control (${label}): without it, the harness sees GA load`, !nothingLoaded(dom));
  dom.window.close();
}

if (failures) {
  console.error(`analytics: ${failures} check(s) failed`);
  process.exit(1);
}
console.log("analytics: every check passed");
