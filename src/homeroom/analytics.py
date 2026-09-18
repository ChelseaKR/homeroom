"""Google Analytics 4 on the published site, added after rendering.

Owner decision, 2026-09-17: GA4 on every public site, with the privacy copy and
every "no tracking" claim updated to match. This reverses the rule that the
school pages carry no script (AGENTS.md rule 7, ADR 0001), on the owner's
instruction, and the documents that stated it now say what runs.

It is a step between rendering and serving, not a change to the renderer. The
renderer still writes pages with no script, and every gate that reads its output
(`make pages` over the fixture build, `tools/ask-optin.mjs`'s zero-requests
check) still reads exactly that. `make publish` then runs :func:`add_to_tree`
over its staging tree before weighing it, so the committed ``site/`` -- the
bytes served -- carries the addition, and `tests/test_published_site.py` holds
every published page to it.

What it adds, and nothing else:

* ``analytics.js`` at the site root: the loader, with the measurement ID, the
  production host and the opt-out labels written into it.
* One ``<script src="analytics.js" defer integrity="sha384-...">`` in each
  page's ``<head>``: a relative path, like every other link on the site, and
  pinned to the loader's own hash, so a browser refuses an ``analytics.js``
  that is not the one the page was published with.
* On every page but the landing page, one short note -- "This site uses Google
  Analytics..." -- with a link to the disclosure and an empty slot the loader
  fills with the "Opt out of analytics" button. It goes at the end of the
  footer where a page has one, and at the end of ``<main>`` where the page
  closes on its notices instead (county and district pages).
* On the landing page, the full disclosure in each language section
  (``#privacy-en``, ``#privacy-es``), with the button.

The loader itself refuses to do anything unless the page is served from
``homeroom.chelseakr.com``, the browser sends neither Global Privacy Control nor
Do Not Track, and the reader has not opted out. It sets Consent Mode v2
defaults (ad storage, ad user data and ad personalization denied everywhere;
analytics storage denied in the EEA, the UK and Switzerland), turns Google
signals and ad personalization off, and sends one page view whose address is
the path plus any ``utm_*`` tags and nothing else. The site is not a
single-page app: every page is a document load.

With :data:`GA4_MEASUREMENT_ID` empty, :func:`add_to_tree` changes nothing and
writes nothing, so turning GA off is one line and a ``make publish``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path

from homeroom.i18n import LOCALES, Locale, text

GA4_MEASUREMENT_ID = "G-PMC113MW2C"
"""The web stream of GA4 property 554882251 (14-month retention, Google signals
off on the property). Public by design: it is in every page view's request."""

PRODUCTION_HOST = "homeroom.chelseakr.com"
"""The only host the loader runs on. A local preview, a fixture build and any
other copy of these files load nothing."""

OPT_OUT_KEY = "homeroom.chelseakr.com:analytics-opt-out"
"""Where the footer choice is remembered, in the reader's localStorage."""

SCRIPT_NAME = "analytics.js"
MARKER = 'data-analytics="ga4"'
"""On everything this module adds, so a second run can tell it already ran."""

_MEASUREMENT_ID = re.compile(r"^G-[A-Z0-9]{4,20}$")

CONSENT_DENIED_REGIONS: tuple[str, ...] = (
    # EU member states
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
    "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES",
    "SE",
    # EU territories with their own ISO codes
    "AX", "GF", "GP", "MQ", "MF", "RE", "YT",
    # Rest of the EEA, the UK and Switzerland
    "IS", "LI", "NO", "GB", "CH",
)  # fmt: skip
"""Where Consent Mode denies ``analytics_storage`` by default (ISO 3166-1)."""

_HEAD_CLOSE = "</head>"
_FOOTER_END = "</div>\n</footer>"
_MAIN_END = "</main>"
_LANDING_SECTION_END = "</section>"
_HTML_LANG = re.compile(r'<html lang="(en|es)">')

LOADER = """/* Google Analytics 4 for homeroom.chelseakr.com. Added to the published pages by
   homeroom.analytics (owner decision, 2026-09-17). Loads nothing off the production
   host, under Global Privacy Control or Do Not Track, or after "Opt out of
   analytics". */
(function () {
  "use strict";
  var ID = __ID__;
  var HOST = __HOST__;
  var KEY = __KEY__;
  var REGIONS = __REGIONS__;
  var LABELS = __LABELS__;
  var w = window;
  var d = document;
  var n = navigator;

  function signal() {
    if (n.globalPrivacyControl === true) return true;
    var dnt = n.doNotTrack || w.doNotTrack || n.msDoNotTrack;
    return dnt === "1" || dnt === "yes";
  }
  function stored() {
    try {
      return w.localStorage.getItem(KEY) === "1";
    } catch (e) {
      return false;
    }
  }
  function optedOut() {
    return signal() || stored();
  }
  function scrubbedPath(path) {
    return path.split("/").map(function (part) {
      return part === "" || (part.length <= 100 && /^[a-z0-9]+(?:[-_.][a-z0-9]+)*$/i.test(part))
        ? part : ":redacted";
    }).join("/");
  }
  function campaign(search) {
    var kept = [];
    var keys = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id"];
    var params = new URLSearchParams(search);
    for (var i = 0; i < keys.length; i++) {
      var value = params.get(keys[i]);
      if (value) kept.push(keys[i] + "=" + encodeURIComponent(value.slice(0, 100)));
    }
    return kept.length ? "?" + kept.join("&") : "";
  }
  function referrer() {
    if (!d.referrer) return "";
    try {
      var url = new URL(d.referrer);
      if (url.origin === w.location.origin) return url.origin + scrubbedPath(url.pathname) + campaign(url.search);
      return url.origin + "/";
    } catch (e) {
      return "";
    }
  }
  function clearCookies() {
    var own = { _ga: true };
    own["_ga_" + ID.slice(2)] = true;
    var labels = w.location.hostname.split(".");
    var domains = [""];
    for (var i = 0; i < labels.length - 1; i++) domains.push(labels.slice(i).join("."));
    d.cookie.split(";").forEach(function (pair) {
      var name = pair.split("=")[0].trim();
      if (!own[name]) return;
      domains.forEach(function (domain) {
        d.cookie = name + "=; Max-Age=0; path=/" + (domain ? "; domain=" + domain : "");
      });
    });
  }

  var loaded = false;
  function load() {
    if (loaded || !ID || w.location.hostname !== HOST || optedOut()) return false;
    loaded = true;
    Object.defineProperty(w, "ga-disable-" + ID, { configurable: true, get: optedOut });
    var layer = (w.dataLayer = w.dataLayer || []);
    function gtag() {
      layer.push(arguments);
    }
    gtag("consent", "default", {
      ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied",
      analytics_storage: "denied", region: REGIONS
    });
    gtag("consent", "default", {
      ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied",
      analytics_storage: "granted"
    });
    gtag("set", "ads_data_redaction", true);
    gtag("js", new Date());
    gtag("config", ID, {
      send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false
    });
    var page = {
      page_location: w.location.origin + scrubbedPath(w.location.pathname) + campaign(w.location.search),
      page_title: d.title.slice(0, 300)
    };
    var from = referrer();
    if (from) page.page_referrer = from;
    gtag("set", page);
    gtag("event", "page_view");
    var script = d.createElement("script");
    script.async = true;
    script.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(ID);
    d.head.appendChild(script);
    return true;
  }

  function storageWorks() {
    try {
      var current = w.localStorage.getItem(KEY);
      w.localStorage.setItem(KEY, current === null ? "0" : current);
      if (current === null) w.localStorage.removeItem(KEY);
      return true;
    } catch (e) {
      return false;
    }
  }
  function renderControls(changed) {
    var slots = d.querySelectorAll(".analytics-opt-out");
    var off = stored();
    for (var i = 0; i < slots.length; i++) {
      var slot = slots[i];
      var holder = slot.closest("[lang]");
      var labels = LABELS[holder && LABELS[holder.getAttribute("lang")] ? holder.getAttribute("lang") : "en"];
      var button = slot.querySelector("button");
      var status = slot.querySelector("[role=status]");
      if (!button) {
        button = d.createElement("button");
        button.type = "button";
        button.style.font = "inherit";
        button.style.minHeight = "24px";
        button.style.marginInlineStart = "0.5em";
        button.style.cursor = "pointer";
        button.addEventListener("click", toggle);
        status = d.createElement("span");
        status.setAttribute("role", "status");
        status.style.marginInlineStart = "0.5em";
        slot.appendChild(button);
        slot.appendChild(status);
      }
      button.textContent = off ? labels.optIn : labels.optOut;
      status.textContent = off ? labels.off : changed ? labels.on : "";
      slot.hidden = false;
    }
  }
  function toggle() {
    var optOut = !stored();
    try {
      if (optOut) w.localStorage.setItem(KEY, "1");
      else w.localStorage.removeItem(KEY);
    } catch (e) {
      return;
    }
    if (optOut) clearCookies();
    else load();
    renderControls(true);
  }

  if (optedOut() && ID) clearCookies();
  load();
  if (storageWorks()) renderControls(false);
})();
"""


def measurement_id(raw: str = GA4_MEASUREMENT_ID) -> str | None:
    """The configured ID, or ``None`` when it is empty (GA off)."""
    value = raw.strip()
    if not value:
        return None
    if not _MEASUREMENT_ID.fullmatch(value):
        raise ValueError(f"not a GA4 measurement ID: {value!r}")
    return value


def loader(measurement: str) -> str:
    """The text of ``analytics.js`` for one measurement ID."""
    labels = {
        locale: {
            "optOut": text(locale, "analytics_opt_out"),
            "optIn": text(locale, "analytics_opt_in"),
            "off": text(locale, "analytics_off_status"),
            "on": text(locale, "analytics_on_status"),
        }
        for locale in LOCALES
    }
    values = {
        "__ID__": json.dumps(measurement),
        "__HOST__": json.dumps(PRODUCTION_HOST),
        "__KEY__": json.dumps(OPT_OUT_KEY),
        "__REGIONS__": json.dumps(list(CONSENT_DENIED_REGIONS)),
        "__LABELS__": json.dumps(labels, ensure_ascii=False, sort_keys=True),
    }
    script = LOADER
    for token, value in values.items():
        script = script.replace(token, value)
    return script


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _slot() -> str:
    return '<span class="analytics-opt-out" hidden></span>'


def _note(locale: Locale, prefix: str) -> str:
    return (
        f'<p class="analytics-note" lang="{locale}" {MARKER}>'
        f"{_escape(text(locale, 'analytics_note'))} "
        f'<a href="{prefix}index.html#privacy-{locale}">'
        f"{_escape(text(locale, 'analytics_link'))}</a>{_slot()}</p>\n"
    )


def _disclosure(locale: Locale) -> str:
    return (
        f'<h3 id="privacy-{locale}" {MARKER}>'
        f"{_escape(text(locale, 'analytics_link'))}</h3>\n"
        f"<p>{_escape(text(locale, 'privacy_body'))}</p>\n"
        f"<p>{_escape(text(locale, 'privacy_cookies'))}</p>\n"
        f"<p>{_escape(text(locale, 'privacy_opt_out'))}{_slot()}</p>\n"
    )


def _replace_once(source: str, anchor: str, replacement: str, where: str) -> str:
    count = source.count(anchor)
    if count != 1:
        raise ValueError(f"{where}: expected one {anchor!r}, found {count}")
    return source.replace(anchor, replacement)


def integrity(script: str) -> str:
    """The Subresource Integrity value for one loader text."""
    digest = hashlib.sha384(script.encode("utf-8")).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def add_to_page(source: str, relative: Path, pinned: str) -> str:
    """One page with GA added. ``relative`` is its path under the site root.

    ``pinned`` is the loader's :func:`integrity` value. Refuses (raises) a page
    that already carries the addition or whose shape it does not recognize,
    rather than guessing where a note belongs.
    """
    where = str(relative)
    if MARKER in source:
        raise ValueError(f"{where}: already carries Google Analytics")
    prefix = "../" * (len(relative.parts) - 1)
    script = (
        f'<script src="{prefix}{SCRIPT_NAME}" defer integrity="{pinned}" '
        f"{MARKER}></script>\n"
    )
    page = _replace_once(source, _HEAD_CLOSE, script + _HEAD_CLOSE, where)
    if relative.as_posix() == "index.html":
        for section_locale in LOCALES:
            opening = f'<section lang="{section_locale}"'
            start = page.find(opening)
            end = page.find(_LANDING_SECTION_END, start)
            if start < 0 or end < 0 or page.count(opening) != 1:
                raise ValueError(f"{where}: no single {opening!r} section")
            page = page[:end] + _disclosure(section_locale) + page[end:]
        return page
    match = _HTML_LANG.search(page)
    if match is None:
        raise ValueError(f"{where}: no <html lang> naming en or es")
    locale: Locale = "en" if match.group(1) == "en" else "es"
    note = _note(locale, prefix)
    if _FOOTER_END in page:
        return _replace_once(page, _FOOTER_END, note + _FOOTER_END, where)
    return _replace_once(page, _MAIN_END, note + _MAIN_END, where)


def add_to_tree(root: Path, raw_id: str = GA4_MEASUREMENT_ID) -> int:
    """Add GA to every page under ``root`` and write the loader. Returns pages changed.

    With no measurement ID configured this changes nothing, and says so.
    """
    measurement = measurement_id(raw_id)
    if measurement is None:
        return 0
    pages = sorted(root.rglob("*.html"))
    if not pages:
        raise ValueError(f"{root}: no pages to add Google Analytics to")
    script = loader(measurement)
    pinned = integrity(script)
    for path in pages:
        relative = path.relative_to(root)
        source = path.read_text(encoding="utf-8")
        path.write_text(add_to_page(source, relative, pinned), encoding="utf-8")
    (root / SCRIPT_NAME).write_bytes(script.encode("utf-8"))
    return len(pages)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add Google Analytics 4 to a rendered site tree, in place."
    )
    parser.add_argument("root", type=Path, help="the rendered site directory")
    args = parser.parse_args(argv)
    changed = add_to_tree(args.root)
    if changed:
        print(f"analytics: Google Analytics 4 added to {changed} pages in {args.root}")
    else:
        print("analytics: no measurement ID configured; nothing added")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
