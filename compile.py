#!/usr/bin/env python3
"""
compile.py — turn the Kaichi Claude-Design container (Kaichi.dc.html) into a
single self-contained, runtime-free index.html that deploys to GitHub Pages.

The .dc.html is a Claude Design "document container": it only renders through
the proprietary support.js runtime (React + Babel from a CDN), which compiles
these authoring conveniences in the browser:

  - style-hover="…" / style-focus="…"  → pseudo-class styles
  - {{ binding }}                        → values from the <script type=text/x-dc> component
  - <sc-if value="{{ x }}">              → conditional blocks
  - data-reveal                          → scroll-in animation

This compiler resolves all of that statically:

  - style-hover/style-focus  → real CSS rules via [data-hv]/[data-fc] selectors
  - the interactive bindings (deck lightbox, contact-form submit state, toggle
    chips, scroll reveal) → one small dependency-free vanilla-JS block

Output loads instantly, needs no React/Babel/CDN, and is directly editable.
Re-run after editing the .dc source in Claude Design:  python3 compile.py
"""
import re
import sys
import pathlib

SRC = pathlib.Path(__file__).parent / "Kaichi.dc.html"
OUT = pathlib.Path(__file__).parent / "index.html"

# Absolute base URL where the site is published — used ONLY for the social-card
# tags (og:url / og:image / twitter:image) and <link rel=canonical>, which must
# be absolute. Every other asset path is relative, so it works under any subpath.
# If the repo stays named `gitban-site`, change this to
# "https://muunkky.github.io/gitban-site/" and recompile.
BASE_URL = "https://muunkky.github.io/kaichi/"

# Cloudflare Web Analytics — cookieless and privacy-first, so it needs no consent
# banner and doesn't undercut the product's zero-telemetry positioning. Kept as a
# plain constant (not inlined) because its {"token": ...} braces would collide with
# the f-string page template below.
ANALYTICS = (
    "<!-- Cloudflare Web Analytics -->"
    "<script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' "
    "data-cf-beacon='{\"token\": \"279ef5211db8443c931c62dade939329\"}'></script>"
    "<!-- End Cloudflare Web Analytics -->"
)

PAGE_TITLE = "Kaichi — AI code you can ship"
PAGE_DESC = (
    "Kaichi is a context manager and state-governance MCP that uses AI to build "
    "production-grade software — architected, tested, reviewed, and fully documented. "
    "Merge-ready PRs your team can own, not prototypes to rebuild."
)

src = SRC.read_text(encoding="utf-8")

# --- extract the <helmet> (head content) and the <x-dc> body template ----------
helmet = re.search(r"<helmet>(.*?)</helmet>", src, re.S).group(1).strip()

xdc = re.search(r"<x-dc>(.*?)</x-dc>", src, re.S).group(1)
# drop the helmet from the body template (it's the first thing inside x-dc)
body = xdc.replace(re.search(r"<helmet>.*?</helmet>", src, re.S).group(0), "", 1)

# --- 1. style-hover / style-focus  → attribute-selector CSS rules --------------
# Inline styles beat external rules on specificity, so the generated pseudo
# rules use !important to win over the element's base inline style.
hover_rules = []
focus_rules = []


def _important(css: str) -> str:
    out = []
    for decl in css.split(";"):
        decl = decl.strip()
        if decl:
            out.append(decl + " !important")
    return ";".join(out) + ";"


def _sub_pseudo(attr: str, store: list, kind: str):
    counter = {"n": 0}

    def repl(m):
        counter["n"] += 1
        idx = len(store) + 1
        store.append((idx, m.group(1)))
        return f'data-{kind}="{idx}"'

    return repl


# assign hover ids
def repl_hover(m):
    idx = len(hover_rules) + 1
    hover_rules.append((idx, m.group(1)))
    return f'data-hv="{idx}"'


def repl_focus(m):
    idx = len(focus_rules) + 1
    focus_rules.append((idx, m.group(1)))
    return f'data-fc="{idx}"'


body = re.sub(r'\sstyle-hover="([^"]*)"', repl_hover, body)
body = re.sub(r'\sstyle-focus="([^"]*)"', repl_focus, body)

# --- 2. deck cards: onClick binding → data-deck ------------------------------
for key, tok in (("prd", "openPrd"), ("design", "openDesign"), ("adr", "openAdr")):
    body = body.replace(f'onClick="{{{{ {tok} }}}}"', f'data-deck="{key}"')

# --- 3. toggle chips: onClick + style bindings → class + data-chip -----------
CHIPS = [
    ("proto", "needProto", "needProtoStyle", False),
    ("rewrite", "needRewrite", "needRewriteStyle", False),
    ("backlog", "needBacklog", "needBacklogStyle", False),
    ("tests", "needTests", "needTestsStyle", False),
    ("trial", "needTrial", "needTrialStyle", False),
    ("milestone", "needMilestone", "needMilestoneStyle", False),
    ("delivery", "toggleDelivery", "deliveryStyle", True),   # active by default
    ("enable", "toggleEnable", "enableStyle", False),
    ("license", "toggleLicense", "licenseStyle", False),
]
for name, click, style, active in CHIPS:
    cls = "kai-chip is-active" if active else "kai-chip"
    body = body.replace(
        f'onClick="{{{{ {click} }}}}" style="{{{{ {style} }}}}"',
        f'class="{cls}" data-chip="{name}"',
    )

# --- 4. lead form ------------------------------------------------------------
body = body.replace('onSubmit="{{ onSubmit }}"', "data-lead-form")
body = body.replace("Thanks{{ firstName }}", 'Thanks<span data-firstname></span>')

# --- 5. sc-if blocks → plain divs toggled by JS ------------------------------
body = body.replace(
    '<sc-if value="{{ submitted }}" hint-placeholder-val="{{ false }}">',
    '<div data-if="submitted" style="display:none">',
)
body = body.replace(
    '<sc-if value="{{ notSubmitted }}" hint-placeholder-val="{{ true }}">',
    '<div data-if="notSubmitted">',
)
body = body.replace(
    '<sc-if value="{{ lightboxOpen }}" hint-placeholder-val="{{ false }}">',
    '<div data-if="lightbox" style="display:none">',
)
body = body.replace("</sc-if>", "</div>")

# --- 6. lightbox internals ---------------------------------------------------
body = body.replace('onClick="{{ closeDeck }}"', "data-close")
body = body.replace('onClick="{{ stop }}"', "data-stop")
body = body.replace("{{ activeType }}", '<span data-lb="type"></span>')
body = body.replace("{{ activeTitle }}", '<span data-lb="title"></span>')
body = body.replace('href="{{ activeSrc }}"', 'href="#" data-lb="open"')
body = body.replace('src="{{ activeSrc }}"', 'data-lb="frame"')
# the iframe also had title="{{ activeTitle }}" — clear it (JS sets nothing critical)
body = body.replace('title="{{ activeTitle }}"', 'title="deck preview"')

# --- assemble generated CSS --------------------------------------------------
gen_css = ["/* generated pseudo-class rules (from the design container's hover and focus attributes) */"]
for idx, css in hover_rules:
    gen_css.append(f'[data-hv="{idx}"]:hover{{{_important(css)}}}')
for idx, css in focus_rules:
    gen_css.append(f'[data-fc="{idx}"]:focus{{{_important(css)}}}')
gen_css.append("""
/* toggle chips (contact form) */
.kai-chip{font-family:'Manrope';font-size:13.5px;font-weight:600;padding:9px 14px;border-radius:999px;cursor:pointer;transition:.15s;background:transparent;color:#9db0a8;border:1px solid #2a3f38}
.kai-chip.is-active{background:#0f6d54;color:#fff;border-color:#0f6d54}
.kai-chip:hover{border-color:#3f8f76}
""")

# --- responsive / mobile (this page is authored with inline styles, so the
# breakpoints below use attribute-substring selectors + !important to override
# those inline rules without needing a class on every element; they are emitted
# AFTER the design CSS so they win the cascade) ------------------------------
gen_css.append("""
/* responsive (mobile + tablet) */
/* never scroll sideways; media never exceeds its column */
html,body{max-width:100%;overflow-x:hidden}
img,svg,iframe{max-width:100%}
/* Reserve the deck-preview images' box before they lazy-load, so the page
   doesn't grow underneath an in-page anchor jump (clicking "Get merge-ready
   PRs" was landing at a stale position because these loaded after the scroll).
   Ratio matches the 2000x1280 screenshots. */
img[src^="docs/decks/previews/"]{aspect-ratio:1000/640;height:auto}
/* deck lightbox iframe is a flex child that otherwise collapses to its intrinsic
   150px height (the modal was mostly blank on every screen); height:100% + a
   zeroed min-height let it fill the modal */
[data-lb="frame"]{height:100% !important;min-height:0 !important}
/* tablets: 3-up card grids become 2-up */
@media (max-width:1000px){
  [style*="grid-template-columns:repeat(3,1fr)"]{grid-template-columns:repeat(2,1fr) !important}
}
/* phones: every multi-column grid stacks to one column */
@media (max-width:760px){
  [style*="grid-template-columns"]{grid-template-columns:1fr !important}
  [style*="gap:56px"]{gap:28px !important}
  /* header: let the nav wrap instead of overflowing, and drop the section anchors
     (still reachable by scrolling) so the logo + Discord + CTA stay tidy */
  nav[style*="flex-wrap:nowrap"]{flex-wrap:wrap !important;gap:14px 18px !important}
  nav a[href="#product"],nav a[href="#how"],nav a[href="#features"]{display:none !important}
  /* trim the desktop vertical rhythm so a phone isn't a mile of whitespace */
  section[style*="padding:88px 24px 40px"]{padding:52px 20px 28px !important}
  section[style*="padding:64px 24px"]{padding:44px 20px !important}
  [style*="padding:100px 24px"]{padding:64px 20px !important}
  header [style*="padding:14px 24px"]{padding:12px 18px !important}
}
""")
gen_css_str = "\n".join(gen_css)

# --- the runtime replacement (vanilla, dependency-free) ----------------------
runtime = r"""
<script>
(function () {
  "use strict";

  /* ---- scroll reveal (replaces data-reveal handling in the dc runtime) ---- */
  var reveals = Array.prototype.slice.call(document.querySelectorAll('[data-reveal]'));
  var vh = window.innerHeight || 800;
  reveals.forEach(function (el) {
    if (el.getBoundingClientRect().top > vh * 0.85) {
      el.style.opacity = '0';
      el.style.transform = 'translateY(22px)';
      el.style.transition = 'opacity .7s cubic-bezier(.2,.7,.2,1), transform .7s cubic-bezier(.2,.7,.2,1)';
    }
  });
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.style.opacity = '1';
          e.target.style.transform = 'none';
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.12 });
    reveals.forEach(function (el) { io.observe(el); });
  }

  /* ---- deck lightbox ---- */
  var DECKS = {
    prd:    { src: "docs/decks/PRD-011-live-html-roadmap-view.html",              type: "Product Requirements",   title: "PRD-011 · Live HTML Roadmap View" },
    design: { src: "docs/decks/DD-021-cwd-pin-git-operations.html",               type: "Design Document",        title: "DD-021 · CWD-Pin Git Operations" },
    adr:    { src: "docs/decks/ADR-078-lifecycle-deck-generation-as-skill-pair.html", type: "Architecture Decision", title: "ADR-078 · Deck Generation as a Skill Pair" }
  };
  var lb        = document.querySelector('[data-if="lightbox"]');
  var lbType    = lb && lb.querySelector('[data-lb="type"]');
  var lbTitle   = lb && lb.querySelector('[data-lb="title"]');
  var lbOpen    = lb && lb.querySelector('[data-lb="open"]');
  var lbFrame   = lb && lb.querySelector('[data-lb="frame"]');

  function openDeck(key) {
    var d = DECKS[key];
    if (!d || !lb) return;
    if (lbType)  lbType.textContent  = d.type;
    if (lbTitle) lbTitle.textContent = d.title;
    if (lbOpen)  lbOpen.setAttribute('href', d.src);
    if (lbFrame) lbFrame.setAttribute('src', d.src);
    lb.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }
  function closeDeck() {
    if (!lb) return;
    lb.style.display = 'none';
    if (lbFrame) lbFrame.removeAttribute('src');   // stop the iframe
    document.body.style.overflow = '';
  }

  /* On phones the embedded iframe is a poor scroll-deck experience (and touch
     scrolling inside an iframe is unreliable), so a tap opens the deck full-screen
     in a new tab, where its own responsive layout works natively. Desktop keeps
     the in-page lightbox. */
  function activateDeck(key) {
    var d = DECKS[key];
    if (!d) return;
    if (window.matchMedia('(max-width: 760px)').matches) {
      window.open(d.src, '_blank', 'noopener');
      return;
    }
    openDeck(key);
  }

  Array.prototype.slice.call(document.querySelectorAll('[data-deck]')).forEach(function (card) {
    var key = card.getAttribute('data-deck');
    card.addEventListener('click', function () { activateDeck(key); });
    card.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); activateDeck(key); }
    });
  });
  if (lb) {
    var backdrop = lb.querySelector('[data-close]');   // outermost overlay
    if (backdrop) {
      backdrop.addEventListener('click', function (ev) {
        if (ev.target === backdrop) closeDeck();        // only bare-backdrop clicks
      });
    }
    var closeBtn = lb.querySelector('button[aria-label="Close"]');
    if (closeBtn) closeBtn.addEventListener('click', closeDeck);
  }
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') closeDeck();
  });

  /* ---- toggle chips ---- */
  Array.prototype.slice.call(document.querySelectorAll('.kai-chip')).forEach(function (chip) {
    chip.addEventListener('click', function () { chip.classList.toggle('is-active'); });
  });

  /* ---- lead form: capture the lead, then open the booking calendar ---- */
  var BOOKING_URL = "https://calendar.app.google/nma5u7ioDyXh6R426";
  // Google Apps Script web-app /exec URL — logs every submission to a Google Sheet.
  // Requires the web-app deployment's "Who has access" set to "Anyone".
  // Empty = booking still works, nothing is logged.
  var LEAD_ENDPOINT = "https://script.google.com/macros/s/AKfycbxJe7nH8efe2k00_080afCmGONcGFE8O5c4giAfmCg50Kq2u0swK35S5gk9eiPkkJxKtg/exec";
  var form = document.querySelector('[data-lead-form]');
  if (form) {
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var data = new FormData(form);
      // 1) open the booking page first, while still inside the click gesture
      window.open(BOOKING_URL, '_blank', 'noopener');
      // 2) best-effort lead capture to a Google Sheet (never blocks the booking)
      if (LEAD_ENDPOINT) {
        var chips = Array.prototype.slice.call(document.querySelectorAll('.kai-chip.is-active'))
          .map(function (c) { return c.textContent.trim(); }).join(', ');
        var payload = new URLSearchParams();
        ['name', 'email', 'company', 'message'].forEach(function (k) {
          payload.append(k, (data.get(k) || '').toString());
        });
        payload.append('interests', chips);
        payload.append('page', 'kaichi-landing');
        fetch(LEAD_ENDPOINT, { method: 'POST', mode: 'no-cors', body: payload }).catch(function () {});
      }
      // 3) swap the form for the confirmation state
      var name = (data.get('name') || '').toString().trim();
      var first = name ? ' ' + name.split(/\s+/)[0] : '';
      var fn = document.querySelector('[data-firstname]');
      if (fn) fn.textContent = first;
      var done = document.querySelector('[data-if="submitted"]');
      var pending = document.querySelector('[data-if="notSubmitted"]');
      if (done) done.style.display = '';
      if (pending) pending.style.display = 'none';
    });
  }
})();
</script>
"""

# --- write out ---------------------------------------------------------------
og_image = BASE_URL + "og.png"
social = f"""<meta name="description" content="{PAGE_DESC}">
<link rel="canonical" href="{BASE_URL}">
<meta property="og:title" content="{PAGE_TITLE}">
<meta property="og:description" content="{PAGE_DESC}">
<meta property="og:type" content="website">
<meta property="og:url" content="{BASE_URL}">
<meta property="og:image" content="{og_image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{PAGE_TITLE}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{PAGE_TITLE}">
<meta name="twitter:description" content="{PAGE_DESC}">
<meta name="twitter:image" content="{og_image}">"""

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{PAGE_TITLE}</title>
{social}
{helmet}
<style>
{gen_css_str}
</style>
</head>
<body>
{body.strip()}
{runtime}
{ANALYTICS}
</body>
</html>
"""

OUT.write_text(html, encoding="utf-8")

# --- self-check: no unresolved authoring constructs should remain ------------
leftovers = []
for pat in (r"\{\{", r"</?sc-if", r"style-hover", r"style-focus", r'onClick="\{\{', r'onSubmit="\{\{', r"<x-dc", r"<helmet"):
    hits = len(re.findall(pat, html))
    if hits:
        leftovers.append(f"{pat}: {hits}")
print(f"wrote {OUT} ({len(html)} bytes)")
print(f"hover rules: {len(hover_rules)}, focus rules: {len(focus_rules)}")
if leftovers:
    print("WARNING unresolved constructs:", "; ".join(leftovers))
    sys.exit(1)
print("clean: no unresolved dc constructs remain")
