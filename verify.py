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


    # ---- UNSGNMW1 step 6: macOS/Windows nightlies + the unsigned label -------
    NIGHTLY = "https://github.com/muunkky/kaichi-releases/releases/download/nightly/"

    # 6. every asset the nightly release publishes is offered here, exactly once
    for asset in ("kaichi-linux-x86_64", "kaichi-linux-arm64",
                  "kaichi-macos-arm64", "kaichi-windows-x86_64.exe", "SHA256SUMS"):
        link = pg.locator(f'a[href="{NIGHTLY}{asset}"]')
        assert link.count() == 1, f"expected 1 nightly link for {asset}, got {link.count()}"
        assert link.first.is_visible(), f"nightly link for {asset} is not visible"
    print("nightly links (linux x2, macos, windows, checksums): OK")

    # 7. the signing state is stated AT the download, not in a footnote, and it
    #    names the concrete thing each OS actually does.
    warn = pg.locator("[data-signing-warning]")
    assert warn.count() == 1, f"expected 1 signing warning, got {warn.count()}"
    assert warn.first.is_visible(), "signing warning is not visible"
    wt = warn.first.inner_text()
    for needle in ("unsigned", "xattr -d com.apple.quarantine", "Privacy & Security",
                   "SmartScreen", "More info", "Run anyway"):
        assert needle.lower() in wt.lower(), f"signing warning missing {needle!r} in {wt!r}"
    # Control-click -> Open was REMOVED in macOS 15 (Sequoia); telling a visitor to
    # do it reads as the download being broken. It must not come back.
    assert "control-click" not in wt.lower() and "right-click" not in wt.lower(), \
        f"signing warning reinstates the removed Control-click override: {wt!r}"
    # readable BEFORE the click: at or above both links it warns about
    wy = warn.first.bounding_box()["y"]
    for asset in ("kaichi-macos-arm64", "kaichi-windows-x86_64.exe"):
        ly = pg.locator(f'a[href="{NIGHTLY}{asset}"]').first.bounding_box()["y"]
        assert wy <= ly, f"signing warning (y={wy}) sits below the {asset} link (y={ly})"
    print("unsigned warning sits above the downloads it describes: OK")

    # 8. macOS/Windows must not inherit the Linux nightly's freshness promise:
    #    they are built on manual dispatch only, never on the cron.
    ondemand = pg.locator("[data-ondemand-note]")
    assert ondemand.count() == 1, "missing the on-demand (not-nightly) note for macOS/Windows"
    assert ondemand.first.is_visible(), "on-demand note is not visible"

    # 9. the page no longer promises these builds are coming
    page_text = pg.inner_text("body")
    assert "coming soon" not in page_text.lower(), "'coming soon' copy is still on the page"

    # 10. the primary buttons still resolve `releases/latest`, which EXCLUDES
    #     prereleases -- a macOS/Windows link there would be a 404.
    latest = pg.eval_on_selector_all(
        'a[href*="/releases/latest/download/"]',
        "els => els.map(e => e.getAttribute('href'))",
    )
    assert sorted(latest) == sorted([
        "https://github.com/muunkky/kaichi-releases/releases/latest/download/kaichi-linux-x86_64",
        "https://github.com/muunkky/kaichi-releases/releases/latest/download/kaichi-linux-arm64",
    ]), f"primary download buttons are no longer Linux-only: {latest}"
    print("primary buttons still Linux-only (releases/latest excludes prereleases): OK")

    # 11. the platform table states macOS and Windows honestly
    plat = pg.locator("[data-platform-table]")
    assert plat.count() == 1, "platform support table not found"
    pt = plat.first.inner_text()
    for needle in ("macOS", "Windows", "nightly", "unsigned"):
        assert needle.lower() in pt.lower(), f"platform table missing {needle!r} in {pt!r}"
    print("platform support table covers macOS + Windows: OK")

    b.close()

if errors:
    print("\nJS CONSOLE ISSUES:")
    for e in errors:
        print(" -", e)
else:
    print("\nno JS errors/warnings")
print("\nALL CHECKS PASSED")
