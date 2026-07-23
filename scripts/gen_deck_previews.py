#!/usr/bin/env python3
"""Regenerate the deck preview thumbnails used in the "How it works" cards.

Each lifecycle card (PRD / Design Doc / ADR) shows a crisp static screenshot of
its deck's title slide instead of a live scaled-down iframe (which read as
cramped, especially full-width on mobile). Re-run this after editing a deck:

    python3 scripts/gen_deck_previews.py     # needs: pip install playwright && playwright install chromium

Writes docs/decks/previews/{prd,design,adr}.png (1000x640 @2x). Commit the PNGs.

Two more previews, docs/decks/previews/roadmap.png and board.png, are NOT
generated here: they are screenshots of the product's own viewer
(.gitban/views/{roadmap,board}.html in the product repo), captured at 1200x768 /
1400x896 @2x with the top nav (.viewer-nav) hidden and the brand text swapped
gitban->kaichi. Regenerate them from the product repo if those views change; the
aspect ratio (1.5625) matches these deck previews.
"""
import pathlib

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
DECKS = {
    "prd": "docs/decks/PRD-011-live-html-roadmap-view.html",
    "design": "docs/decks/DD-021-cwd-pin-git-operations.html",
    "adr": "docs/decks/ADR-078-lifecycle-deck-generation-as-skill-pair.html",
}
OUTDIR = ROOT / "docs" / "decks" / "previews"


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for key, src in DECKS.items():
            uri = (ROOT / src).resolve().as_uri()
            page = browser.new_page(viewport={"width": 1000, "height": 640}, device_scale_factor=2)
            page.goto(uri)
            page.wait_for_timeout(900)  # let fonts + the title slide settle
            out = OUTDIR / f"{key}.png"
            page.screenshot(path=str(out))  # viewport = the deck's title slide
            print(f"wrote {out.relative_to(ROOT)}")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
