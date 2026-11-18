"""The ask page: the one page in the build that carries a script, and the opt-in.

ADR 0001 keeps the school pages static and script-free, and ADR 0003 keeps
them that way. The ask layer's front end is therefore a separate page per
school and language, ``ask/<cds>.<locale>.html``, reached by a plain link from
the school page. Three promises, each held by a test:

* The school page gains one link and nothing else; a build not given an
  endpoint renders neither the link nor this page and is byte-identical to a
  build before ADR 0003.
* This page carries exactly one inline script and no other subresource, and
  that script makes no request of any kind until the reader submits a
  question. ``tools/ask-optin.mjs`` loads the page in a DOM with ``fetch``
  stubbed and asserts zero calls on load and one on submit.
* Everything the reader sees before and around the answer is a fixed string
  from ``i18n.py``: the labels, the refusals, the non-affiliation notice, the
  "what you can ask" list. The script builds the answer with ``textContent``
  only; nothing from the service is ever parsed as markup.

Without JavaScript the page still reads: the explanation, the list of what
can be asked, the non-affiliation notice, and a link back to the school page,
which is complete without it.
"""

from __future__ import annotations

import json

from homeroom.i18n import OTHER_LOCALE, Locale, cde_text_lang, text
from homeroom.profiles import SchoolProfile
from homeroom.render import STYLESHEET, _cde, _esc, language_switch, page_name

ASK_DIR = "ask"

QUESTION_MAX_LENGTH = 600
"""How long a question may be, in characters. The box enforces it
(``maxlength``) and the hint under the label says it in words
(``ask_page_hint_length``); ``tests/test_askpage.py`` holds the number in the
words to this one."""

ASK_STYLE = """
.ask-form { max-width: 44rem; margin: 1rem 0 2rem; }
.ask-form label { display: block; font-weight: 600; margin-bottom: .4rem; }
.ask-form .ask-hint { color: var(--ink-2); font-size: .9rem; margin: 0 0 .4rem; }
.ask-form .ask-error { font-weight: 600; margin: .4rem 0 0; }
.ask-form .ask-error:empty { margin: 0; }
.ask-form textarea {
  width: 100%; min-height: 6rem; font: inherit; padding: .6rem .7rem;
  border: 1px solid var(--ink-3); border-radius: 3px;
  background: var(--raised); color: var(--ink);
}
.ask-form button {
  margin-top: .8rem; font: inherit; font-weight: 600; padding: .6rem 1.2rem;
  border: 1px solid var(--accent); border-radius: 3px;
  background: var(--accent); color: var(--raised); cursor: pointer;
}
.ask-form button[disabled] { opacity: .6; cursor: default; }
.answer { max-width: 44rem; }
.answer ol { padding-left: 1.3rem; }
.answer li { margin: 0 0 1rem; }
.answer .cites { display: block; font-size: .86rem; color: var(--ink-2); margin-top: .25rem; }
.answer blockquote { margin: .5rem 0 0; padding: .4rem .9rem; border-left: 3px solid var(--rule-strong); color: var(--ink-2); font-size: .95rem; }
.answer .label { font-size: .9rem; color: var(--ink-2); }
"""

SCRIPT = """
(function () {
  "use strict";
  var strings = JSON.parse(document.getElementById("ask-strings").textContent);
  var form = document.getElementById("ask-form");
  var field = document.getElementById("ask-question");
  var button = document.getElementById("ask-send");
  var answer = document.getElementById("answer");
  var heading = document.getElementById("answer-heading");
  var error = document.getElementById("ask-error");
  if (!form || !field || !button || !answer || !error) { return; }
  form.hidden = false;

  function el(tag, className, textContent) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (textContent !== undefined) { node.textContent = textContent; }
    return node;
  }
  function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }
  function note(message) {
    var box = el("div", "note");
    box.appendChild(el("p", null, message));
    return box;
  }
  function cde(node) {
    if (strings.cde_lang) { node.lang = strings.cde_lang; }
    return node;
  }
  function citationLink(citation) {
    var a = document.createElement("a");
    if (citation.type === "passage") {
      a.href = citation.url || strings.school_page;
      a.rel = "noopener";
      a.textContent = strings.cde_page + ": ";
      a.appendChild(cde(el("span", null, citation.title || citation.label)));
    } else if (citation.type === "source") {
      a.href = strings.school_page + "#sources";
      a.textContent = strings.on_page + ": " + citation.label;
    } else {
      a.href = strings.school_page + "#" + (citation.anchor || "main");
      var where = citation.scope === "school" ? strings.scope_school
        : citation.scope === "district" ? strings.scope_district : strings.scope_state;
      a.textContent = strings.on_page + ": " + citation.label + " (" + where
        + (citation.year ? ", " + citation.year : "") + ")";
    }
    return a;
  }
  function show(data) {
    clear(answer);
    if (data.refusal) { answer.appendChild(note(data.refusal)); }
    if (data.intro) { answer.appendChild(el("p", null, data.intro)); }
    if (data.claims && data.claims.length) {
      var list = el("ol");
      data.claims.forEach(function (claim) {
        var item = el("li");
        item.appendChild(el("span", null, claim.text));
        if (claim.quote) { item.appendChild(cde(el("blockquote", null, claim.quote))); }
        if (claim.citations && claim.citations.length) {
          var cites = el("span", "cites", strings.citations + ": ");
          claim.citations.forEach(function (citation, index) {
            if (index) { cites.appendChild(document.createTextNode("; ")); }
            cites.appendChild(citationLink(citation));
          });
          item.appendChild(cites);
        }
        list.appendChild(item);
      });
      answer.appendChild(list);
    }
    if (typeof data.withheld === "number" && data.withheld > 0) {
      answer.appendChild(el("p", "label", strings.withheld.replace("{count}", String(data.withheld))));
    }
    if (data.labels) {
      answer.appendChild(el("p", "label", data.labels.ai));
      answer.appendChild(el("p", "label", data.labels.language));
    }
    if (data.provenance && data.provenance.model) {
      answer.appendChild(el("p", "label", strings.model + ": " + data.provenance.model
        + (data.provenance.is_fixture ? " " + strings.fixture : "")));
    }
    heading.hidden = false;
    heading.focus();
  }
  // An empty question is answered in words, beside the box, and nothing is
  // sent. The message is the box's description (aria-describedby), so it is
  // announced once: when focus has to move to the box, the screen reader reads
  // the box and its description, and the alert is told to stay quiet; when
  // focus is already in the box nothing would be read, so the alert speaks.
  function refuse() {
    var here = document.activeElement === field;
    if (here) { error.removeAttribute("aria-live"); }
    else { error.setAttribute("aria-live", "off"); }
    error.textContent = strings.empty;
    field.value = "";
    field.setAttribute("aria-invalid", "true");
    if (!here) { field.focus(); }
  }
  function accept() {
    if (error.textContent) { error.textContent = ""; }
    field.removeAttribute("aria-invalid");
  }
  field.addEventListener("input", accept);
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var question = field.value.trim();
    if (!question) { refuse(); return; }
    accept();
    button.disabled = true;
    clear(answer);
    answer.appendChild(el("p", "label", strings.sending));
    fetch(strings.endpoint, {
      method: "POST",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ cds: strings.cds, locale: strings.locale, question: question })
    }).then(function (response) {
      return response.json();
    }).then(function (data) {
      show(data);
    }).catch(function () {
      clear(answer);
      answer.appendChild(note(strings.unavailable));
      heading.hidden = false;
      heading.focus();
    }).then(function () {
      button.disabled = false;
    });
  });
})();
"""


def ask_page_name(cds_code: str, locale: Locale) -> str:
    """The file one school's ask page lands in, relative to the site root."""
    return f"{ASK_DIR}/{page_name(cds_code, locale)}"


def _strings(profile: SchoolProfile, locale: Locale, endpoint: str) -> str:
    """The data the script reads: fixed strings, the endpoint, and the school.

    Serialized with ``ensure_ascii`` and ``<`` escaped, so the JSON block can
    never close its own ``<script>`` tag whatever a string contains.

    ``cde_lang`` is the language of the two things in an answer that are CDE's
    words and not Homeroom's: a passage quoted verbatim, and the title of the
    CDE page it came from. The script marks them with it, the way ``_cde``
    marks every CDE name on the static pages, so a Spanish screen reader does
    not read English with Spanish phonemes (WCAG 2.2 SC 3.1.2). On an English
    page the attribute would be redundant, so the key is absent and the page's
    bytes are what they were.
    """
    data = {
        "endpoint": endpoint.rstrip("/") + "/ask",
        "cds": profile.school.cds_code,
        "locale": locale,
        "school_page": f"../{page_name(profile.school.cds_code, locale)}",
        "sending": text(locale, "ask_page_sending"),
        "empty": text(locale, "ask_page_error_empty"),
        "unavailable": text(locale, "ask_refusal_unavailable"),
        "withheld": text(locale, "ask_withheld_count"),
        "citations": text(locale, "ask_page_citations"),
        "on_page": text(locale, "ask_page_on_page"),
        "cde_page": text(locale, "ask_page_cde_page"),
        "model": text(locale, "ask_page_model"),
        "fixture": text(locale, "ask_page_fixture"),
        "scope_school": text(locale, "col_this_school"),
        "scope_district": text(locale, "col_district"),
        "scope_state": text(locale, "col_state"),
    }
    cde_lang = cde_text_lang(locale)
    if cde_lang is not None:
        data["cde_lang"] = cde_lang
    return json.dumps(data, ensure_ascii=True, sort_keys=True).replace("<", "\\u003c")


def render_ask_page(
    profile: SchoolProfile, *, locale: Locale, endpoint: str, is_fixture: bool
) -> str:
    school = profile.school
    other = OTHER_LOCALE[locale]
    title = (
        text(locale, "ask_page_title").format(school=school.name)
        + " · "
        + text(locale, "site_name")
    )
    back = f"../{page_name(school.cds_code, locale)}"
    switch = page_name(school.cds_code, other)
    fixture = (
        '<div class="note">\n'
        f'<p><span class="note-title">{_esc(text(locale, "fixture_banner_title"))}</span> '
        f"{_esc(text(locale, 'fixture_banner_body'))}</p>\n</div>"
        if is_fixture
        else ""
    )
    body = "\n".join(
        [
            f'<a class="skip-link" href="#main">{_esc(text(locale, "skip_to_content"))}</a>',
            '<header class="site">\n<div class="wrap bar">\n'
            '<p class="brand">'
            f'<span class="brand-name">{_esc(text(locale, "site_name"))}</span>'
            f'<span class="brand-tag">{_esc(text(locale, "site_tagline"))}</span></p>\n'
            f"{language_switch(locale, switch)}\n</div>\n</header>",
            '<main id="main" class="wrap">',
            f'<p class="eyebrow">{_esc(text(locale, "ask_page_eyebrow"))}</p>',
            f"<h1>{_esc(text(locale, 'ask_page_heading'))} {_cde(school.name, locale)}</h1>",
            fixture,
            f'<p><a href="{_esc(back)}">{_esc(text(locale, "ask_page_back"))}</a></p>',
            '<div class="note">\n'
            f'<p><span class="note-title">{_esc(text(locale, "ask_page_label_title"))}</span> '
            f"{_esc(text(locale, 'ask_label_ai'))}</p>\n"
            f"<p>{_esc(text(locale, 'footer_no_ranking'))}</p>\n"
            "</div>",
            f"<p>{_esc(text(locale, 'ask_page_intro'))}</p>",
            f"<p>{_esc(text(locale, 'ask_page_examples'))}</p>",
            # `novalidate`: the script answers an empty question itself, in the
            # page's language and beside the box; the browser's own bubble is in
            # the browser's language and reaches a question of only spaces never.
            '<form id="ask-form" class="ask-form" hidden novalidate>',
            f'<label for="ask-question">{_esc(text(locale, "ask_page_label_question"))}</label>',
            f'<p id="ask-hint" class="ask-hint">{_esc(text(locale, "ask_page_hint_length"))}</p>',
            f'<textarea id="ask-question" name="question" maxlength="{QUESTION_MAX_LENGTH}" '
            'required autocomplete="off" aria-describedby="ask-hint ask-error"></textarea>',
            '<p id="ask-error" class="ask-error" role="alert"></p>',
            f'<button id="ask-send" type="submit">{_esc(text(locale, "ask_page_button"))}</button>',
            "</form>",
            f'<noscript><p class="note">{_esc(text(locale, "ask_page_noscript"))}</p></noscript>',
            f'<h2 id="answer-heading" tabindex="-1" hidden>{_esc(text(locale, "ask_page_answer_heading"))}</h2>',
            '<section id="answer" class="answer" aria-live="polite" '
            f'aria-label="{_esc(text(locale, "ask_page_answer_heading"))}"></section>',
            "</main>",
            '<footer>\n<div class="wrap">\n'
            f"<p>{_esc(text(locale, 'footer_no_ranking'))}</p>\n"
            f"<p>{_esc(text(locale, 'footer_unaffiliated'))}</p>\n"
            "</div>\n</footer>",
            f'<script type="application/json" id="ask-strings">{_strings(profile, locale, endpoint)}</script>',
            f"<script>{SCRIPT}</script>",
        ]
    )
    description = text(locale, "ask_page_intro")
    return (
        "<!doctype html>\n"
        f'<html lang="{locale}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n"
        f'<meta name="description" content="{_esc(description)}">\n'
        '<meta name="robots" content="noindex">\n'
        f'<link rel="alternate" hreflang="{locale}" href="{_esc(page_name(school.cds_code, locale))}">\n'
        f'<link rel="alternate" hreflang="{other}" href="{_esc(switch)}">\n'
        f"<style>\n{STYLESHEET}{ASK_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )
