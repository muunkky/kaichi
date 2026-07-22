import pathlib
from playwright.sync_api import sync_playwright

root = pathlib.Path(__file__).parent
url = (root / "index.html").as_uri()
errors = []

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.goto(url, wait_until="networkidle")

    # 1. hero renders
    h1 = pg.inner_text("h1")
    assert "ship" in h1.lower(), f"hero missing: {h1!r}"
    print("hero:", h1.replace("\n", " "))

    # full-page screenshot
    pg.screenshot(path=str(root / "_verify_full.png"), full_page=True)

    # 2. deck lightbox opens
    pg.eval_on_selector('[data-deck="prd"]', "el => el.scrollIntoView()")
    pg.click('[data-deck="prd"]')
    pg.wait_for_timeout(300)
    lb = pg.query_selector('[data-if="lightbox"]')
    disp = lb.evaluate("el => getComputedStyle(el).display")
    assert disp != "none", "lightbox did not open"
    ttype = pg.inner_text('[data-lb="type"]')
    ttitle = pg.inner_text('[data-lb="title"]')
    frame_src = pg.get_attribute('[data-lb="frame"]', "src")
    print("lightbox:", ttype, "|", ttitle, "| src=", frame_src)
    assert "REQUIREMENTS" in ttype.upper() and "PRD-011" in ttitle and "PRD-011" in (frame_src or "")
    pg.screenshot(path=str(root / "_verify_lightbox.png"))

    # 3. Escape closes
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(200)
    disp = lb.evaluate("el => getComputedStyle(el).display")
    assert disp == "none", "lightbox did not close on Escape"
    print("lightbox closes on Escape: OK")

    # 4. chip toggles
    chip = pg.query_selector('[data-chip="proto"]')
    chip.scroll_into_view_if_needed()
    before = chip.evaluate("el => el.classList.contains('is-active')")
    chip.click()
    after = chip.evaluate("el => el.classList.contains('is-active')")
    assert before is False and after is True, f"chip toggle failed {before}->{after}"
    print("chip toggle: OK")

    # 5. lead form submit -> thank-you
    pg.fill('input[name="name"]', "Ada Lovelace")
    pg.fill('input[name="email"]', "ada@example.com")
    pg.click('button[type="submit"]')
    pg.wait_for_timeout(200)
    done = pg.query_selector('[data-if="submitted"]')
    ddisp = done.evaluate("el => getComputedStyle(el).display")
    assert ddisp != "none", "thank-you not shown"
    thanks = pg.inner_text('[data-if="submitted"]')
    assert "Ada" in thanks, f"firstName not filled: {thanks!r}"
    print("form submit -> thank-you, firstName:", "Ada" in thanks)

    b.close()

if errors:
    print("\nJS CONSOLE ISSUES:")
    for e in errors:
        print(" -", e)
else:
    print("\nno JS errors/warnings")
print("\nALL CHECKS PASSED")
