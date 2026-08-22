# 0003. Add a grounded question-answering layer at the edges, and never let it rank

Status: Accepted (owner-directed change of direction)
Date: 2026-08-21
Deciders: Chelsea Kelly-Reif
Amends: ADR 0001 (the school pages stay script-free and static; this ADR adds a
separate, optional ask page and a separate, optional runtime service outside
them). ADR 0002 is not amended: it binds the new surface first.

## Context

Until this decision Homeroom had no AI in the product. The README's standards
table said "AI Evaluation: N/A (no prompt, retrieval, or model-version
surface)", `docs/RESPONSIBLE-TECH-AUDITS.md` said the same, and the only AI
anywhere near the repo was the AI-assisted development disclosed in the README.
Those statements were true and are now false, which is why this ADR exists and
why the same change series rewrites every document that made them.

The owner has directed that the product gain real AI at runtime: a family
should be able to ask, in English or Spanish, what a school's page is actually
saying ("Is chronic absenteeism a problem here?", "How many kids are English
learners?", "What does 'chronic absenteeism' mean and how is it measured?") and
get an answer in plain language. The pages already put every figure beside its
district and statewide context and name its suppression state; what they do not
do is answer a question.

The danger is specific. A language model asked about a school will, unless
prevented, do the three things this project exists to refuse: it will invent a
number where the state published none (the portfolio's dominant defect,
"absence rendered as a value"), it will compare things that do not share a
denominator or a year, and it will summarize a school into a judgment. The
founding rule (ADR 0002) is that Homeroom refuses to rank schools. A model that
says "this is a good school" or "better than most in the district" is a ranker
wearing a different costume, and it would be the most-read sentence on the page.

## Decision

Add runtime AI in one bounded role, behind an explicit opt-in, as an optional
service that the static site works without:

**The model structures the question and narrates the answer; the published
CDE-derived dataset is the only evidence; a verifier sits between the model and
the reader.**

Concretely:

1. **One school per request, and only what its page shows.** The service
   (`homeroom.ask`) answers about exactly one school. The evidence it gives the
   model is that school's own measure records, each with the district and
   statewide figure the page already shows beside it, each in one of the same
   three states (published, withheld, nothing published), each carrying its
   source file, academic year, and unit. No other school's figures are ever in
   the request. The model cannot rank schools it cannot see.

2. **Structuring before answering.** The model's first job is to turn the
   question into a structured lookup: which measures, which of the district or
   statewide context cells, whether a definition is wanted, or whether the
   question is one the data cannot answer. The lookup names measures only from
   the catalog the service supplies; anything else is dropped. A question about
   a school's principal, its safety, its "vibe", or anything outside the
   acquired CDE files is classified as outside the data and answered with what
   *is* known, never with a guess.

3. **Ranking refusal is enforced, not requested.** Every form of "which school
   is better", "rank these", "give it a grade", "is this a good school", "should
   I send my kid here" is classified as a judgment question. The refusal text a
   family reads is a fixed, reviewed, bilingual string from `i18n.py`; the model
   never writes it. The model may still pick the measures the question touched,
   and those are narrated on their own terms. Then a second, independent guard
   scans every sentence the model wrote, in both languages, for ordering,
   grading, scoring, better/worse, and recommendation language, and withholds
   any sentence that carries it. Withheld sentences are counted and the count is
   shown. Zero tolerance is a test, not an aspiration: a dedicated adversarial
   evaluation suite of ranking-bait phrasings (direct, indirect, comparative,
   "just between us", bilingual, embedded inside a legitimate question) is
   committed with the harness, and its target is zero.

4. **Every substantive claim cites a record and is verified before display.**
   The model answers as a list of claims, each citing one or more record
   identifiers of the form `school CDS | measure | academic year`, or a passage
   identifier from the committed corpus of CDE definitions. The verifier then
   checks, programmatically, that every cited record exists for this school,
   that every number in the sentence is a number one of its cited records
   actually publishes (or a year, a grade label, or the CDS code), that a
   sentence about a withheld or unpublished record carries no digit and says
   "not published" or "withheld" in the reader's language, that a comparison
   cites the school record and its own district or statewide cell and states
   the direction the arithmetic actually has, and that a quoted definition is a
   verbatim substring of the corpus passage it cites. A claim that fails any
   check is withheld, not repaired, and the count of withheld claims is shown
   beside the answer. An answer whose every claim was withheld is an honest
   empty answer, and says so.

5. **Suppression is narrated faithfully.** A withheld cell is never "zero",
   "none", or "no students"; it is "not published", and when asked why, the
   answer is CDE's small-cell rule, quoted from the corpus. This is the second
   dedicated evaluation suite, scored on "absence rendered as a value", with
   the suppressed ground truth read from the real acquired files at run time
   rather than typed into the cases.

6. **Comparisons only on the page's own basis.** The model may compare a school
   figure to its district or statewide figure only where the page already
   shows that pair: same measure, same file, same year, same unit. It may not
   introduce a benchmark of its own, compare a 2024-25 rate to a 2025-26 count,
   or combine measures into anything resembling a score. The verifier enforces
   this by construction: a comparison claim must cite exactly one record and
   speak only about that record's own three cells.

7. **Definitions come from CDE's own words.** A committed `corpus/` holds the
   text of CDE's published file-structure and glossary pages for the measures
   the site uses, with URL, retrieval date, and SHA-256 of the retrieved page,
   split into addressable passages. A definition is answered by quoting a
   passage verbatim; a paraphrase without a verified quote is withheld.

8. **Spanish at runtime, labeled.** The model narrates in the reader's
   language. Spanish narration is labeled AI-translated and not reviewed, in
   Spanish, on the page; the fixed strings around it (labels, refusals,
   disclaimers) come from the same reviewed-by-author catalogs as the rest of
   the site and are parity-gated the same way.

9. **Honest refusals.** A CDS code the build does not carry, a measure the
   state did not publish for this school, a question outside what the acquired
   files can answer: each gets a fixed, bilingual, specific answer that says
   what is not known and points at what is.

Consequential choices:

- **The school pages do not change shape.** They remain static, script-free,
  and free of off-origin requests (ADR 0001, tested). The opt-in is a plain link
  from each school page to a separate ask page for that school and language,
  which is the only page in the build that carries a script, and that script
  makes no request of any kind until the reader submits a question. A build
  that is not given a service endpoint renders no ask page and no link, and is
  byte-identical to a build before this ADR. Both facts are tested.
- **Provider and model.** The public `anthropic` Python SDK, with
  `claude-sonnet-5` as the configurable default. Amazon Bedrock is supported
  through the same SDK as an alternative provider. The credential comes only
  from the environment; no key is ever written to the repository or to any file
  the service creates. The SDK is an optional extra: the core package stays
  stdlib-only, and `homeroom.ask` imports it lazily.
- **No question is stored.** The service keeps no request body, writes no
  question text to disk or logs, and returns nothing it did not compute for that
  request. The provider's own retention applies while the request is processed;
  a deployment must document that subprocessor relationship before the service
  is exposed to families.
- **Cost is bounded from the first commit.** Per-client rate limiting and a hard
  daily cap live in the service, a refused request leaves the page intact, and
  the stable system prompt is cached with the provider.
- **Nothing here deploys.** A deployment shape (one function with a public URL,
  cost-bounded, CORS locked to the site's origin) is prepared as a template and
  a runbook and was applied on 2026-08-22 by the owner's decision (stack
  `homeroom-ask`, us-west-2, Bedrock `global.anthropic.claude-sonnet-4-6`;
  parameters and rollback in `deploy/ask/README.md`). Whether the service is
  exposed to real families
  is the owner's decision, the same as whether the pages are.
- **The evaluation is model-independent and committed.** Five suites live with
  their harness: ranking refusal, suppression fidelity, citation grounding,
  comparability, and question structuring (including vague and unanswerable
  questions scored on "refused to guess"). Measured numbers are committed only
  from a recorded live run that names the provider, model, prompt version,
  commit, and date, and a test rejects a results file without that provenance.
  A suite that was not run says `not_run`; it never carries a number.

## Consequences

- Several public claims become false and are rewritten in the same change
  series: "AI Evaluation: N/A" in the README, `docs/ROADMAP.md`, and
  `docs/RESPONSIBLE-TECH-AUDITS.md` now read "applies, under ADR 0003"; the
  Governance section of the audits record activates; the threat model gains a
  fifth trust boundary (the reader's question crosses to a model provider) and
  the residual-risk register gains rows for it.
- Every AI output is labeled, in both languages, as AI-generated, unofficial,
  not a ranking, and not a recommendation, and the non-affiliation notice
  stays on every page that carries it.
- ADR 0002's enforcement moves up a level. The `Measure` type made a masked
  cell unreadable as a number; the verifier makes an unverifiable sentence
  unshowable. The cost is that some true sentences are withheld because they
  could not be checked, and the project accepts that cost: a withheld true
  sentence is an absence the page admits, and a shown false one is a lie.
- The runtime gains a network surface, a credential, a cost, and a provider
  dependency. Each of those is a new way to fail and is owned: the service
  fails closed to the static page on any provider error, rate limit, or cap.
- The evaluation numbers are only as good as the model they were run on, and
  the results files say which. A suite run on a different model than the code
  default is recorded as exactly that.
- Spanish narration is model output and is labeled as such. RR-06 (Spanish
  reviewed only by its author) now has a sibling: Spanish narration reviewed by
  nobody at all, stated on the page.

## Alternatives considered

- **Build-time AI only (pre-written explanations per school).** Rejected by the
  owner: it does not answer a family's question, and 10,534 pre-written
  narratives would be 10,534 unreviewed statements about real schools.
- **A free conversational agent over the whole dataset.** Rejected. With every
  school in context the model can rank, and a prompt is not a guardrail. One
  school per request makes ranking structurally impossible rather than
  discouraged.
- **Let the model write the refusal.** Rejected. The refusal is the
  most-scrutinized sentence the product will ever produce, and a fixed string
  can be reviewed once; a generated one has to be re-verified every time.
- **Trust the model's citations.** Rejected. A citation the code did not resolve
  is decoration. The verifier is the product; the model is a draft.
- **Embeddings for definition retrieval.** Not needed. The corpus is a handful
  of CDE pages, retrieval is by measure key and lexical match, and the citation
  contract (verbatim quote of an addressable passage) does not depend on how the
  passage was found.
