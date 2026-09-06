// Prove the ask page makes no request until a question is submitted.
//
// ADR 0003 promises that the ask page, the only page in the build that carries a
// script, reaches nowhere until the reader acts. A static check can see that there is
// one inline script and no subresource; it cannot see what the script does on load.
// This loads every ask page into a jsdom DOM with scripts running, stubs every way a
// page could reach the network (fetch, XMLHttpRequest, sendBeacon, WebSocket,
// EventSource), and asserts zero calls after load and after the event loop settles.
// Then it types a question, submits the form, and asserts exactly one POST to the
// configured endpoint with the expected JSON body, feeds it a canned answer, and
// checks the answer is rendered as text, never as markup.
//
// It also holds the promise ADR 0003 and the README's standards table both
// publish and nothing else in the repository checks -- that a reader is told how
// many sentences the verifier withheld. No test renders an answer, so if this
// does not check it, nothing does. Three canned answers are rendered per page and
// the withheld paragraph is matched whole, against the page's own locale string
// with the response's count substituted, so the assertion reads in both languages
// and cannot be satisfied by a digit that happens to appear elsewhere.
//
// Usage: node tools/ask-optin.mjs <site-directory>   (reads <site-directory>/ask/*.html)

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";

const site = process.argv[2];
if (!site) {
  console.error("usage: node tools/ask-optin.mjs <site-directory>");
  process.exit(2);
}
const dir = join(site, "ask");
if (!existsSync(dir)) {
  console.error(`no ${dir}; build the site with --ask-endpoint first`);
  process.exit(2);
}
const pages = readdirSync(dir).filter((n) => n.endsWith(".html")).sort();
if (pages.length === 0) {
  console.error(`no ask pages in ${dir}`);
  process.exit(2);
}

const CANNED = {
  status: "answered",
  kind: "judgment",
  locale: "en",
  refusal: "FIXED-REFUSAL <b>not markup</b>",
  intro: "FIXED-INTRO",
  claims: [
    {
      kind: "figure",
      text: "CLAIM-TEXT <img src=x onerror=alert(1)>",
      quote: null,
      citations: [
        { id: "x|enrollment.total|2025-26|school", type: "cell", label: "All students", scope: "school", year: "2025-26", anchor: "students" },
        { id: "fsabd#4", type: "passage", label: "File Structure", url: "https://www.cde.ca.gov/ds/ad/fsabd.asp", title: "File Structure" },
      ],
    },
  ],
  withheld: 2,
  labels: { ai: "LABEL-AI", language: "LABEL-LANG" },
  provenance: { model: "canned-model", is_fixture: true },
};

// Each page renders three answers: CANNED's own count, then this one, then zero.
// A second, different count is what separates a page that reads the response from
// one carrying a number fixed in the script or baked into the locale string --
// with a single payload the two are indistinguishable. Zero renders no line at
// all, which is the one case the paragraph is deliberately absent.
const SECOND_WITHHELD = 7;

const tick = () => new Promise((r) => setTimeout(r, 20));

async function check(name) {
  const html = readFileSync(join(dir, name), "utf8");
  const calls = [];
  let reply = CANNED;
  const console_ = new VirtualConsole();
  console_.on("jsdomError", (e) => console.error(`  ${name}: ${e.message}`));
  const dom = new JSDOM(html, {
    url: "https://site.example/ask/" + name,
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole: console_,
    beforeParse(window) {
      window.fetch = (url, init) => {
        calls.push({ kind: "fetch", url: String(url), init });
        return Promise.resolve({ json: () => Promise.resolve(reply) });
      };
      window.XMLHttpRequest = function () { calls.push({ kind: "xhr" }); throw new Error("xhr"); };
      window.WebSocket = function () { calls.push({ kind: "ws" }); throw new Error("ws"); };
      window.EventSource = function () { calls.push({ kind: "es" }); throw new Error("es"); };
      window.navigator.sendBeacon = () => { calls.push({ kind: "beacon" }); return false; };
    },
  });
  const { window } = dom;
  const { document } = window;
  await tick();
  await tick();
  if (calls.length !== 0) {
    throw new Error(`${name}: ${calls.length} network call(s) on load: ${JSON.stringify(calls)}`);
  }
  const form = document.getElementById("ask-form");
  const field = document.getElementById("ask-question");
  if (!form || !field || form.hidden) {
    throw new Error(`${name}: the form is missing or still hidden after the script ran`);
  }
  const strings = JSON.parse(document.getElementById("ask-strings").textContent);
  const submit = async (question) => {
    field.value = question;
    form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    await tick();
    await tick();
  };
  await submit("  Is chronic absenteeism a problem here?  ");
  if (calls.length !== 1 || calls[0].kind !== "fetch") {
    throw new Error(`${name}: expected exactly one fetch on submit, got ${JSON.stringify(calls)}`);
  }
  const [call] = calls;
  if (call.url !== strings.endpoint || !call.url.startsWith("https://ask.example.invalid/")) {
    throw new Error(`${name}: fetched ${call.url}, expected ${strings.endpoint}`);
  }
  const body = JSON.parse(call.init.body);
  const expected = { cds: strings.cds, locale: strings.locale, question: "Is chronic absenteeism a problem here?" };
  if (JSON.stringify(body) !== JSON.stringify(expected) || call.init.method !== "POST" || call.init.credentials !== "omit") {
    throw new Error(`${name}: unexpected request ${JSON.stringify(call.init)}`);
  }
  const answer = document.getElementById("answer");
  const text = answer.textContent;
  for (const needle of ["FIXED-REFUSAL <b>not markup</b>", "FIXED-INTRO", "CLAIM-TEXT <img src=x onerror=alert(1)>", "LABEL-AI", "LABEL-LANG", "canned-model"]) {
    if (!text.includes(needle)) {
      throw new Error(`${name}: answer does not show ${JSON.stringify(needle)}`);
    }
  }
  if (answer.querySelector("b, img")) {
    throw new Error(`${name}: service text was parsed as markup`);
  }
  // The withheld count, matched as the whole paragraph the script appends rather
  // than as a digit somewhere in the answer. `text.includes("2")` used to stand
  // here and was satisfied by the citation year "2025-26" on every render, so the
  // assertion stayed green with the withheld paragraph deleted outright (#68).
  // The string is the page's own `ask_withheld_count` with the response's count
  // substituted, which is what the script builds, so this reads in both locales
  // without a word of English hardcoded here.
  const template = strings.withheld;
  if (typeof template !== "string" || !template.includes("{count}")) {
    throw new Error(
      `${name}: the page carries no withheld string with a {count} placeholder: ${JSON.stringify(template)}`,
    );
  }
  const [withheldPrefix] = template.split("{count}");
  if (!withheldPrefix) {
    throw new Error(`${name}: the withheld string is a bare count: ${JSON.stringify(template)}`);
  }
  const paragraphs = () => [...answer.querySelectorAll("p")].map((p) => p.textContent);
  const withheldSentence = (count) => template.replace("{count}", String(count));
  const expectWithheld = (count) => {
    const shown = paragraphs().filter((line) => line === withheldSentence(count));
    if (shown.length !== 1) {
      throw new Error(
        `${name}: withheld count not shown; expected exactly one paragraph reading ` +
          `${JSON.stringify(withheldSentence(count))}, got ${JSON.stringify(paragraphs())}`,
      );
    }
  };
  expectWithheld(CANNED.withheld);
  const links = [...answer.querySelectorAll("a")].map((a) => a.getAttribute("href"));
  if (!links.some((h) => h.endsWith("#students")) || !links.includes("https://www.cde.ca.gov/ds/ad/fsabd.asp")) {
    throw new Error(`${name}: citation links missing: ${JSON.stringify(links)}`);
  }
  if (document.activeElement !== document.getElementById("answer-heading")) {
    throw new Error(`${name}: focus did not move to the answer heading`);
  }
  // Submitting an empty question sends nothing.
  await submit("   ");
  if (calls.length !== 1) {
    throw new Error(`${name}: an empty question made a request`);
  }
  // A second answer, carrying a different count: the number the reader sees is
  // read from the response, not fixed in the script or in the locale string.
  reply = { ...CANNED, withheld: SECOND_WITHHELD };
  await submit("How many students are enrolled?");
  if (calls.length !== 2) {
    throw new Error(`${name}: expected a second fetch on the second question, got ${JSON.stringify(calls)}`);
  }
  expectWithheld(SECOND_WITHHELD);
  // An answer that withheld nothing shows no count at all, which is the one case
  // the paragraph is deliberately not rendered.
  reply = { ...CANNED, withheld: 0 };
  await submit("How many students are enrolled?");
  if (calls.length !== 3) {
    throw new Error(`${name}: expected a third fetch on the third question, got ${JSON.stringify(calls)}`);
  }
  const stray = paragraphs().filter((line) => line.startsWith(withheldPrefix));
  if (stray.length !== 0) {
    throw new Error(`${name}: a withheld count was shown for an answer that withheld nothing: ${JSON.stringify(stray)}`);
  }
  window.close();
  console.log(`ok   ask/${name}  (no request on load; one POST on submit; text-only render; withheld count shown)`);
}

let failed = 0;
for (const name of pages) {
  try {
    await check(name);
  } catch (error) {
    failed += 1;
    console.error(`FAIL ${error.message}`);
  }
}
if (failed) {
  console.error(`${failed} ask page(s) failed the opt-in check`);
  process.exit(1);
}
console.log(`${pages.length} ask page(s) make no request until a question is submitted`);
