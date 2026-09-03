#!/usr/bin/env python3
"""Redraw the 1200x630 link-preview cards, one per language.

    uv run --with pillow python tools/make_social_card.py

Writes ``src/homeroom/assets/social-card.en.png`` and ``…es.png``. They live
inside the package, not beside it, so ``build_site`` can find them from an
installed wheel as well as from this checkout; ``site.py`` copies them into the
output only when the build has been told the origin it will be served from,
which is the same condition every other addressed artifact is written under.

This is out-of-band on purpose and is not part of ``make verify``. Rasterising
text needs a font renderer, and ``dependencies = []`` in pyproject.toml is a
property this project keeps: Pillow is pulled in by ``--with`` for the length of
this one command and never enters ``uv.lock``.

**Nothing here is retyped.** The wording comes out of ``homeroom.i18n`` and the
colours out of ``homeroom.render``. A card is the only thing a reader sees
before deciding whether to open the page, so a second hand-maintained copy of
the tagline would be the copy that drifts, and the drifting copy would be the
one doing the talking. The Spanish card is not a translation step either: it is
generated from the same table that renders the Spanish pages, because Spanish is
a launch requirement here rather than a later phase.

The rule under the tagline is the one this project holds above the others -- it
refuses to rank schools. A preview that showed a name and a tagline and left
that out would be the single published surface omitting it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from homeroom.i18n import LOCALES, Locale, text  # noqa: E402  (needs the path above)
from homeroom.render import LIGHT  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "src" / "homeroom" / "assets"

WIDTH, HEIGHT = 1200, 630
MARGIN = 88

DOMAIN = "homeroom.chelseakr.com"

#: Tried in order. The pages ask for a system sans; these are the closest real
#: files on the platforms this is likely to be regenerated from. Both cards need
#: the accented characters Spanish uses, which every candidate below carries.
FONT_CANDIDATES = {
    "bold": (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
    "regular": (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ),
}


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES[weight]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    raise SystemExit(
        f"no {weight} font found. Tried: {', '.join(FONT_CANDIDATES[weight])}. "
        f"Add a path for this platform rather than falling back to a bitmap "
        f"font, which would render an unreadable card."
    )


def _wrap(
    draw: ImageDraw.ImageDraw, body: str, font: ImageFont.FreeTypeFont, limit: int
) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in body.split():
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= limit or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render(locale: Locale) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), LIGHT["surface"])
    draw = ImageDraw.Draw(image)
    content_width = WIDTH - 2 * MARGIN

    # One accent rule down the left edge. The pages are built from borders and
    # whitespace rather than fills, and the card is not a different design.
    draw.rectangle([(0, 0), (10, HEIGHT)], fill=LIGHT["accent"])

    y = MARGIN
    draw.text(
        (MARGIN, y),
        text(locale, "site_name"),
        font=_font("bold", 92),
        fill=LIGHT["ink"],
    )
    y += 148

    tagline_font = _font("regular", 38)
    for line in _wrap(draw, text(locale, "site_tagline"), tagline_font, content_width):
        draw.text((MARGIN, y), line, font=tagline_font, fill=LIGHT["ink-2"])
        y += 54

    y += 34
    draw.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill=LIGHT["rule-strong"], width=2)
    y += 40

    rule_font = _font("bold", 27)
    for line in _wrap(
        draw, text(locale, "footer_no_ranking"), rule_font, content_width
    ):
        draw.text((MARGIN, y), line, font=rule_font, fill=LIGHT["accent"])
        y += 38

    draw.text(
        (MARGIN, HEIGHT - MARGIN - 24),
        DOMAIN,
        font=_font("regular", 26),
        fill=LIGHT["ink-3"],
    )
    return image


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for locale in LOCALES:
        destination = OUTPUT_DIR / f"social-card.{locale}.png"
        render(locale).save(destination, format="PNG", optimize=True)
        print(
            f"wrote {destination.relative_to(REPO_ROOT)} ({destination.stat().st_size} bytes)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
