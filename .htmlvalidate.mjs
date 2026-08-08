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
  },
};
