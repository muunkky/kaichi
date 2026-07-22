# Kaichi landing page

Landing page for the product (rebranded **gitban → Kaichi**). Self-contained
static site — no React, no Babel, no proprietary runtime. Loads instantly.

Destined for `muunkky/kaichi` → `https://muunkky.github.io/kaichi/`. Runs in
**parallel with the existing `gitban-site`**; the old site stays live until it's
retired.

## Files

| File | Role |
|------|------|
| `index.html` | The deployable page. Self-contained (fonts from Google Fonts; everything else inline). GitHub Pages serves this. |
| `og.png` | Social-card image (1200×630). **Placeholder — still the old gitban card; regenerate for Kaichi.** |
| `docs/decks/*.html` | The three real lifecycle decks (PRD-011, DD-021, ADR-078), shown as live iframe previews + click-to-open lightbox. |
| `Kaichi.dc.html` | The **design source** — the Claude Design container. Keep editing this in Claude Design, then re-compile. |
| `compile.py` | Compiles `Kaichi.dc.html` → `index.html` (`BASE_URL`, title, description at the top). |
| `verify.py` | Headless-browser smoke test (hero, deck lightbox, Esc-to-close, chip toggles, form submit). |
| `.nojekyll` | Serve files as-is (no Jekyll processing). |

## Why a compile step

`Kaichi.dc.html` is a Claude Design "document container" — it only renders through
Claude Design's `support.js`, which pulls React + ReactDOM + Babel (~3 MB) from a CDN
and transpiles in the browser on every load. `compile.py` resolves all of it statically:

- `style-hover=` / `style-focus=` → real CSS `:hover` / `:focus` rules
- `{{ bindings }}`, `<sc-if>` conditionals, `onClick`/`onSubmit` → one small vanilla-JS block
- `data-reveal` → scroll-in animation via `IntersectionObserver`

Interactive behavior (deck lightbox, contact-form submit state, toggle chips, scroll
reveal) is preserved exactly.

## Working on it

Edit `index.html` directly (plain HTML/CSS/JS), **or** keep designing in Claude Design
and re-compile:

```bash
python3 compile.py     # regenerates index.html; fails loudly on any unresolved dc construct
python3 verify.py      # optional — needs: pip install playwright && playwright install chromium
```

## Deploy

1. Create a repo named `kaichi` under `muunkky`.
2. Commit this folder's contents (`index.html` at repo root).
3. Settings → Pages → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`.
4. Live at `https://muunkky.github.io/kaichi/`. All asset paths are relative; only the
   social-card tags use the absolute `BASE_URL` in `compile.py`.
