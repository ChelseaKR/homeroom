// HTML conformance and markup-level accessibility rules for the built school pages.
//
// Where a rule is waived or tightened, the reason is here rather than in a commit
// message: a waived rule with no reason beside it is indistinguishable from an
// oversight.
export default {
  extends: [
    "html-validate:recommended",
    "html-validate:document",
    "html-validate:a11y",
  ],
  rules: {
    // The WHATWG spec writes the doctype lowercase and HTML5 is case-insensitive here.
    "doctype-style": ["error", { style: "lowercase" }],
    // Strict: every <th> must carry a scope, not only those in tables that mix row
    // and column headers. Every table here is a data table whose row header names the
    // measure, and a cell read out without its row header is exactly the failure this
    // catches: a withheld figure announced as a bare number.
    "wcag/h63": ["error", { strict: true }],
    // The default 70-character cap is an SEO convention, not an accessibility
    // criterion, and the variable in these titles is a school name CDE chose. Some
    // California school names are long enough on their own to blow a 70-character
    // budget, and truncating the name to fit would make the page harder to identify,
    // not easier. Raised, not disabled, so a runaway title still fails.
    "long-title": ["error", { maxlength: 110 }],
    // Retargeted 2026-09-07, when the pages stopped inlining their stylesheet
    // (issue #95) and started linking `homeroom.css`. html-validate's default for
    // this rule is `target: "all"`, which asks for an SRI hash on same-origin
    // resources too; "crossorigin" is the rule's own other documented setting.
    //
    // Narrowed rather than disabled, and this is the reason rather than a
    // preference. The rule's documentation says SRI exists "to prevent tampering
    // or manipulation from Content Delivery Networks (CDN), rouge proxies,
    // malicious entities". `homeroom.css` is none of those: it is written by the
    // same build, committed in the same tree, published in the same artifact, and
    // served from the same origin as the page naming it. Anyone able to replace it
    // can replace the page's `integrity` attribute in the same edit, so the hash
    // would assert nothing that is not already asserted by the page being intact.
    //
    // What it would cost is real and measured: `integrity="sha384-..."` is 84 bytes
    // a page, 1.96 MB across 23,305 pages, and it would re-couple every page's
    // bytes to the stylesheet's content -- so a one-line CSS edit would rewrite all
    // 23,305 pages, which is the coupling this change exists to break. It would
    // also make a *stale cached* stylesheet fail integrity and be dropped, leaving
    // a reader an unstyled page where today they get a very slightly old one.
    //
    // This does not turn into a rule that cannot fail. An off-origin `<link>` or
    // `<script src>` still fails it, and is separately refused outright by
    // `test_no_page_carries_a_script_or_reaches_off_the_page_for_an_asset`, which
    // allows no absolute URL in a stylesheet href at all. Both were checked by
    // pointing a fixture page at a CDN and confirming each went red.
    "require-sri": ["error", { target: "crossorigin" }],
  },
};
