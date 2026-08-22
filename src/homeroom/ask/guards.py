"""The lexical guards: what a sentence may not say, and what numbers it contains.

These are deliberately blunt. A sentence that trips one is withheld and
counted, never shown, and a false positive costs a true sentence while a false
negative costs the project its founding rule, so the lexicon errs toward
withholding. Every list here is in both languages, because the narration is.

Three guards:

* :func:`judgment_hits` finds ranking, grading, scoring, better/worse, and
  recommendation language. ADR 0002 says Homeroom refuses to rank; this is the
  function that makes a model sentence obey it.
* :func:`numbers_in` extracts every number a sentence states, so the verifier
  can check each one against the cells the sentence cites.
* :func:`says_not_published` and :func:`renders_absence_as_value` decide whether
  a sentence about a withheld or unpublished cell says so honestly or turns the
  absence into a zero, a "none", or a "no students".
"""

from __future__ import annotations

import re

_JUDGMENT_EN = (
    r"better|worse|best|worst|top|bottom|superior|inferior|excellent|poor|"
    r"great school|good school|bad school|strong school|weak school|"
    r"good choice|bad choice|right choice|wrong choice|"
    r"above average|below average|average school|"
    r"rank(?:s|ed|ing)?|rating|rated|rate it|"
    r"scores?|scored|scoring|letter grade|a grade of|grade of [a-f]|"
    r"grades? (?:this|the) school|"
    r"recommend(?:s|ed|ation|ations)?|"
    r"(?:should|ought to) (?:(?:you|i|we|they) )?(?:send|enroll|choose|pick)|"
    r"worth (?:it|sending|enrolling)|"
    r"outperform(?:s|ed|ing)?|underperform(?:s|ed|ing)?|"
    r"stars?|out of (?:5|10|100)|/10\b|/100\b|"
    r"one of the (?:best|worst)|"
    r"safe school|unsafe|dangerous"
)
_JUDGMENT_ES = (
    r"mejor(?:es)?|peor(?:es)?|superior(?:es)?|inferior(?:es)?|excelente|"
    r"buena escuela|mala escuela|gran escuela|escuela fuerte|escuela débil|"
    r"buena opción|mala opción|buena elección|mala elección|"
    r"por encima del promedio|por debajo del promedio|"
    r"clasificaci[oó]n|clasificad[ao]|ranking|"
    r"calificaci[oó]n|calificad[ao]|puntaje|puntuaci[oó]n|nota de|"
    r"recomiend[oa]|recomendaci[oó]n|recomendad[ao]|"
    r"deber[ií]a(?:s|n)? (?:inscribir|enviar|elegir|matricular)|"
    r"vale la pena|"
    r"estrellas?|de (?:5|10|100) puntos|"
    r"una de las (?:mejores|peores)|"
    r"escuela segura|insegur[ao]|peligros[ao]"
)
JUDGMENT = re.compile(rf"\b(?:{_JUDGMENT_EN}|{_JUDGMENT_ES})\b", re.IGNORECASE)
"""Ranking, grading, scoring, better/worse, and recommendation language, EN and ES.

``grade`` alone is not here: "Grade 3" is a row on every page. The grading
sense is caught by its phrasings ("letter grade", "a grade of", "grades this
school"). ``higher`` and ``lower`` are not here either: a comparison claim may
say a school's rate is higher than the district's, because the page shows both
figures side by side, and the verifier checks the arithmetic; what it may not
say is that higher is better.
"""

LETTER_GRADE = re.compile(
    r"\b(?:grade|nota|calificaci[oó]n)\s*[:=]?\s*[A-F][+-]?(?![\w-])|"
    r"\b(?:give|gave|gets?|got|earns?|deserves?|doy|dar[ií]a|merece)\s+"
    r"(?:it\s+|le\s+)?(?:an?\s+|una?\s+)?[A-F][+-]?(?![\w-])",
    re.IGNORECASE,
)
"""``grade: B+``, ``give it a B``, and friends: the shapes a letter grade takes."""


def judgment_hits(text: str) -> list[str]:
    """Every judgment phrase in ``text``, lowercased, in order. Empty means clean."""
    hits = [m.group(0).lower() for m in JUDGMENT.finditer(text)]
    hits.extend(m.group(0).lower() for m in LETTER_GRADE.finditer(text))
    return hits


YEAR_RANGE = re.compile(r"\b20\d\d\s?[-\u2013/]\s?(?:20)?\d\d\b")
"""An academic year as prose writes it: ``2024-25``, ``2024\u201325``, ``2024/2025``."""

NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![\w,]*\d)")
"""A number as prose states it: digits, optional thousands commas, optional fraction.

Spanish narration is told to write numbers the way the evidence does (comma
thousands, point decimal), which is also how CDE's own Spanish materials and
the pages write them (:func:`homeroom.i18n.format_number`).
"""


def numbers_in(text: str) -> list[str]:
    """Every number ``text`` states, normalised (commas stripped).

    Academic-year ranges are removed first, so ``2024-25`` is not read as the
    two numbers 2024 and 25; the verifier allows years separately.
    """
    out: list[str] = []
    for whole, fraction in NUMBER.findall(YEAR_RANGE.sub(" ", text)):
        token = whole.replace(",", "")
        if fraction:
            token = f"{token}.{fraction}"
        out.append(token)
    return out


def number_forms(value: float) -> set[str]:
    """Every normalised spelling of a published value a sentence may use.

    ``512.0`` may be written ``512``; ``12.3`` must be ``12.3`` (``12`` is a
    different number, and so is ``12.30``, which is not how the page writes it).
    """
    if float(value).is_integer():
        return {str(int(value))}
    return {f"{value:.1f}", repr(float(value))}


_NOT_PUBLISHED = re.compile(
    r"not published|withheld|did not publish|does not publish|not release|"
    r"no (?:\w+ ){0,2}figure|no published|was not reported|not reported|"
    r"not available|nothing (?:was |is )?published|never (?:published|reported)|"
    r"(?:file|state) (?:does not|never|did not) mention|"
    r"suppressed|masked|"
    r"no (?:se )?public[oó]|no (?:fue|está|esta) publicad|sin (?:dato|cifra)|"
    r"retenid|no (?:se )?inform[oó]|no disponible|no report[oó]|suprimid|"
    r"no hay (?:una )?cifra|no public[oó]",
    re.IGNORECASE,
)


def says_not_published(text: str) -> bool:
    """True if the sentence says, in either language, that the figure is absent."""
    return _NOT_PUBLISHED.search(text) is not None


_ABSENCE_AS_VALUE = re.compile(
    r"\b(?:zero|none(?! (?:was|is|were|are) (?:published|reported))|nobody|"
    r"no students|no pupils|no children|"
    r"cero|nadie|no hay (?:estudiantes|alumnos|ni[nñ][oa]s)|"
    r"ning[uú]n(?:[oa]s?)? (?:estudiantes?|alumn[oa]s?|ni[nñ][oa]s?))\b|"
    r"(?<![\d.,])0(?![\d,]|\.\d)",
    re.IGNORECASE,
)
"""Zero in words, or a bare ``0`` (with or without a percent sign) in digits.

The guard runs only on sentences that cite a withheld or unpublished cell, so
a genuine published zero, cited as the reported cell it is, is never caught.
"""


def renders_absence_as_value(text: str) -> bool:
    """True if a sentence turns an absent figure into a zero or a "none".

    Numbers are not checked here: the verifier checks every number in every
    sentence against the cells it cites, and a withheld cell allows none.
    """
    return _ABSENCE_AS_VALUE.search(text) is not None


def year_tokens(year: str) -> set[str]:
    """``2024-25`` may be written as ``2024-25``, ``2024``, ``25``, or ``2025``."""
    tokens = {year}
    start, _, end = year.partition("-")
    if start.isdigit():
        tokens.add(start)
        if end.isdigit():
            tokens.add(end)
            tokens.add(start[: len(start) - len(end)] + end)
    return tokens
