# Corpus: CDE's own words about the measures

These files are the text of California Department of Education web pages,
retrieved by `tools/corpus_fetch.py` and committed so the ask layer (ADR 0003)
can answer "what does this measure mean and how is it measured?" by quoting CDE
verbatim. Nothing in the ask layer paraphrases a definition: a claim that cites
a passage must contain a quote that appears, word for word, on the cited page,
or the verifier withholds it.

`manifest.json` records, per page: the URL, the retrieval date (UTC), the
"Last Reviewed" date the page itself states, the SHA-256 of the raw HTML as
received and of the text file as written, the passage count, and which measure
families the page documents. The loader (`homeroom.ask.corpus`) re-hashes every
text file on load and refuses a file whose hash no longer matches, so a
hand-edited corpus cannot be quoted as CDE's text.

| Key | Page | Documents |
|-----|------|-----------|
| `fsabd` | File Structure: Chronic Absenteeism Data | D3 field definitions; the small-cell suppression rule; what "chronically absent" means in the file |
| `filesabd` | Chronic Absenteeism Data (downloadable files) | The suppression note; CDE's caution about comparing across years (2019-20 not released) |
| `cwa` | Child Welfare & Attendance | The statutory definition of a chronic absentee (EC 60901(c)(1)) |
| `fsenrcensus` | File Structure: Census Day Enrollment Data | D2 reporting categories (race/ethnicity, gender, ELAS, student groups); what Census Day is |
| `filesenrcensus` | Census Day Enrollment Data (downloadable files) | The single-day snapshot definition |
| `fspubschls` | File Structure: Public Schools and Districts | D1 directory fields (charter, status, grade span) |

To refresh: from the repository root, with network access,
`uv run python tools/corpus_fetch.py` (or `--only <key>`). A changed text file
is upstream drift; read the diff before committing it, and re-run the
evaluation suites, because a definition the model quotes may have moved.

These pages are public California state documents. Their text is reproduced
here for citation; the copyright notice on cde.ca.gov applies.
