// Run axe-core over every built page, headlessly, in a jsdom DOM.
//
// This is the WCAG gate the README's standards table promises from the first school
// page. It loads each page into a real DOM implementation and runs axe-core's WCAG
// 2.0/2.1/2.2 A and AA rule sets plus the best-practice set, and exits non-zero on any
// violation. Every page is checked in both languages, because an English page that
// passes and a Spanish page that does not is the exact failure the parity commitment
// exists to prevent.
//
// It is not a substitute for a person using the pages: jsdom does no layout and paints
// no pixels, so rules that depend on rendered geometry or colour cannot fire here.
// Those are named below and in README.md under what still needs a person; colour
// contrast is measured separately, off the palette itself, in tests/test_pages.py.
//
// Usage: node tools/a11y.mjs <directory-of-html-files>

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";
import axe from "axe-core";

const TAGS = [
  "wcag2a",
  "wcag2aa",
  "wcag21a",
  "wcag21aa",
  "wcag22aa",
  "best-practice",
];

// Rules jsdom cannot decide. Left running they report "incomplete", not "pass", and a
// gate that treats an unrunnable rule as a pass teaches a reader the wrong thing.
//
// That was the intent and it was not what the code did. `results.violations` is the
// only list this file used to read, so EVERY undetermined rule was dropped, whether or
// not it was declared here. Measured over the 17 built pages: axe returns
// `violations: []` and `incomplete: color-contrast, landmark-one-main,
// page-has-heading-one` on every one of them. Two of those three were declared
// nowhere — not here, not in docs/accessibility-walkthrough.md, not in
// docs/HELP-WANTED.md — and the gate printed "17 page(s) ... clean" over them.
//
// So the undetermined list is now read, and an undetermined rule that is not declared
// below FAILS. Each entry carries the reason, and every run prints which rules were
// actually undetermined and on how many pages, so the declaration cannot quietly stop
// describing the run.
const UNDETERMINED_UNDER_JSDOM = new Map([
  [
    "color-contrast",
    "no layout, no painted pixels; measured off the palette itself in tests/test_pages.py",
  ],
  [
    "target-size",
    "SC 2.5.8 needs box geometry. Declared ahead of need: these pages ship no " +
      "interactive target, so axe has never returned it undetermined here.",
  ],
  [
    "landmark-one-main",
    "axe's own check reports `error-occurred` under jsdom rather than a verdict; " +
      "asserted structurally below instead (exactly one <main> per page)",
  ],
  [
    "page-has-heading-one",
    "same `error-occurred` under jsdom; asserted structurally below instead " +
      "(exactly one <h1> per page)",
  ],
]);

async function checkPage(path) {
  const html = readFileSync(path, "utf8");
  // "outside-only" gives an eval to inject axe with, without ever running a script that
  // came out of the page. These pages ship no script, and the checker should not start
  // executing one if that ever changes.
  // axe probes for a canvas to decide whether it can sample colours. jsdom has none, so
  // it reports that once per page. Everything else the page or axe says is forwarded.
  const console_ = new VirtualConsole();
  console_.forwardTo(console, { jsdomErrors: "none" });
  console_.on("jsdomError", (error) => {
    if (!/getContext\(\) method/.test(error.message)) {
      console.error(error.message);
    }
  });

  const dom = new JSDOM(html, {
    pretendToBeVisual: true,
    runScripts: "outside-only",
    virtualConsole: console_,
  });
  const { window } = dom;
  window.eval(axe.source);
  const results = await window.axe.run(window.document, {
    runOnly: { type: "tag", values: TAGS },
    resultTypes: ["violations"],
  });
  // The two structural rules axe cannot decide here are decided directly, on the same
  // DOM axe was handed. Declaring a rule undetermined puts the gap on the record; this
  // closes it, which is better, and it is three lines.
  const structure = {
    main: window.document.querySelectorAll("main").length,
    h1: window.document.querySelectorAll("h1").length,
  };
  dom.window.close();
  return { results, structure };
}

const dir = process.argv[2];
if (!dir) {
  console.error("usage: node tools/a11y.mjs <directory-of-html-files>");
  process.exit(2);
}

// How one page's axe result becomes findings. Extracted so the self-test below can
// exercise it without a DOM, and so the two lists are classified in one place rather
// than at two call sites that can drift apart.
//
//   violations  -> always a finding, DECLARED OR NOT. A rule that returned a violation
//                  is a rule that ran.
//   incomplete  -> a finding only when the rule is NOT declared undecidable here.
//                  Declared, it is counted and printed but does not fail.
function classify(results) {
  return {
    violations: results.violations,
    undeclared: results.incomplete
      .map((entry) => entry.id)
      .filter((id) => !UNDETERMINED_UNDER_JSDOM.has(id)),
  };
}

// Run on every invocation, because a suppression that has quietly widened prints the
// same green line as one that never fired. Costs nothing; it is four objects.
//
// The second case is the one this exists for: until 2026-09-08 the violations list was
// filtered by UNDETERMINED_UNDER_JSDOM too, so a real, DECIDED violation of a declared
// rule was dropped and the page printed `ok`.
function selfTest() {
  const declared = [...UNDETERMINED_UNDER_JSDOM.keys()][0];
  const cases = [
    [
      "an undeclared violation fails",
      { violations: [{ id: "image-alt" }], incomplete: [] },
      1,
      0,
    ],
    [
      "a violation of a DECLARED rule still fails",
      { violations: [{ id: declared }], incomplete: [] },
      1,
      0,
    ],
    [
      "an undeclared undetermined rule fails",
      { violations: [], incomplete: [{ id: "image-alt" }] },
      0,
      1,
    ],
    [
      "a declared undetermined rule does not fail",
      { violations: [], incomplete: [{ id: declared }] },
      0,
      0,
    ],
  ];
  for (const [what, results, expectedViolations, expectedUndeclared] of cases) {
    const got = classify(results);
    if (
      got.violations.length !== expectedViolations ||
      got.undeclared.length !== expectedUndeclared
    ) {
      console.error(
        `self-test failed: ${what} \u2014 got ${got.violations.length} violation(s) and ` +
          `${got.undeclared.length} undeclared undetermined rule(s), expected ` +
          `${expectedViolations} and ${expectedUndeclared}`,
      );
      process.exit(2);
    }
  }
}

selfTest();

const pages = readdirSync(dir)
  .filter((name) => name.endsWith(".html"))
  .sort();

if (pages.length === 0) {
  console.error(`no .html files in ${dir}; build the pages first`);
  process.exit(2);
}

// Both languages have to be present, or a green gate would mean nothing more than
// "the English pages are fine".
const locales = new Set(
  pages.map((name) => name.split(".").at(-2)).filter(Boolean),
);
for (const required of ["en", "es"]) {
  if (!locales.has(required)) {
    console.error(`no ${required} pages in ${dir}; both languages must be checked`);
    process.exit(2);
  }
}

let failed = 0;
/** rule id -> how many pages returned it undetermined. */
const undetermined = new Map();
/** page name -> what its structure actually was, when it was wrong. */
const structuralFailures = [];

for (const name of pages) {
  const { results, structure } = await checkPage(join(dir, name));

  // Undetermined is not a pass. An undetermined rule nobody declared is a rule this
  // gate silently stopped checking, which is the failure the declaration exists for.
  for (const entry of results.incomplete) {
    undetermined.set(entry.id, (undetermined.get(entry.id) ?? 0) + 1);
  }
  const { undeclared } = classify(results);

  // The backstop for the two structural rules declared above.
  if (structure.main !== 1 || structure.h1 !== 1) {
    structuralFailures.push(
      `${name}: ${structure.main} <main> and ${structure.h1} <h1> (each must be exactly 1)`,
    );
  }

  // `classify` does NOT filter violations by UNDETERMINED_UNDER_JSDOM. That map is a
  // declaration about rules axe cannot DECIDE here, and until 2026-09-08 it was also
  // applied to the list of rules axe HAD decided \u2014 so a real `color-contrast` or
  // `target-size` violation would have been dropped and the page printed `ok`. A rule
  // that returns a violation is a rule that ran; that it was expected to be
  // undecidable makes the finding more interesting, not less, and the declaration stale.
  const { violations } = classify(results);
  if (violations.length === 0 && undeclared.length === 0) {
    console.log(`ok   ${name}  (${TAGS.join(", ")})`);
    continue;
  }
  if (undeclared.length > 0) {
    failed += undeclared.length;
    console.error(`FAIL ${name}`);
    for (const id of undeclared) {
      console.error(
        `  [undetermined] ${id}: axe could not decide this rule here and it is not ` +
          "declared in UNDETERMINED_UNDER_JSDOM. Either the rule became undecidable " +
          "under jsdom (declare it, with the reason and how it is checked instead) " +
          "or something on the page broke it.",
      );
    }
  }
  if (violations.length === 0) continue;
  failed += violations.length;
  console.error(`FAIL ${name}`);
  for (const v of violations) {
    console.error(`  [${v.impact}] ${v.id}: ${v.help}`);
    if (UNDETERMINED_UNDER_JSDOM.has(v.id)) {
      console.error(
        `    NOTE: ${v.id} is declared in UNDETERMINED_UNDER_JSDOM as a rule axe ` +
          "cannot decide here, and axe has just decided it. Fix the page, then remove " +
          "the declaration \u2014 it is describing a gap that no longer exists.",
      );
    }
    console.error(`    ${v.helpUrl}`);
    for (const node of v.nodes.slice(0, 5)) {
      console.error(`    at ${node.target.join(" ")}`);
      console.error(`      ${node.failureSummary?.replace(/\n/g, "\n      ")}`);
    }
    if (v.nodes.length > 5) {
      console.error(`    ...and ${v.nodes.length - 5} more`);
    }
  }
}

if (structuralFailures.length > 0) {
  console.error(`\nFAIL structural backstop, ${structuralFailures.length} page(s):`);
  for (const line of structuralFailures) console.error(`  ${line}`);
  failed += structuralFailures.length;
}

if (failed > 0) {
  console.error(`\n${failed} accessibility finding(s)`);
  process.exit(1);
}

console.log(
  `\n${pages.length} page(s) in ${[...locales].sort().join(" and ")} clean ` +
    `against ${TAGS.length} rule sets`,
);
console.log(
  `  structural backstop: ${pages.length}/${pages.length} page(s) have exactly one ` +
    "<main> and exactly one <h1>",
);
if (undetermined.size === 0) {
  console.log("  no rule was undetermined on any page");
} else {
  console.log("  undetermined here, declared, and NOT counted as passing:");
  for (const [id, count] of [...undetermined].sort()) {
    console.log(
      `    ${id} (${count}/${pages.length} page(s)) — ${UNDETERMINED_UNDER_JSDOM.get(id)}`,
    );
  }
}
const unobserved = [...UNDETERMINED_UNDER_JSDOM.keys()].filter(
  (id) => !undetermined.has(id),
);
if (unobserved.length > 0) {
  // Not a failure: a rule can be declared ahead of need, or be inapplicable to this
  // directory's pages. It is printed so a declaration cannot go stale unseen — the
  // reason each one is declared is in the map above.
  console.log(`  declared but never undetermined here: ${unobserved.join(", ")}`);
}
