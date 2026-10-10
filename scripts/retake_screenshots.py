#!/usr/bin/env python3
"""One-command README screenshot retake pipeline for Verdant.

1. Seeds a synthetic demo garden into a temp dir (scripts/seed_demo.py).
2. Starts uvicorn against that data.
3. Screenshots every README page with Playwright + Chrome for Testing.
4. Writes PNGs into docs/screenshots/ (same filenames, in place).

Usage:
    python scripts/retake_screenshots.py [--only costs,invoices] [--list]

Sandbox notes: the browser launches with proxy env vars stripped (the
egress proxy breaks localhost), and cdn.tailwindcss.com is served from the
local copy at ~/tailwindcdn.js.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHOTS_DIR = REPO / "docs" / "screenshots"
CHROME = Path.home() / "pw-chrome" / "chrome-linux64" / "chrome"
TAILWIND = Path.home() / "tailwindcdn.js"
PORT = 4123
BASE = f"http://127.0.0.1:{PORT}"

DESKTOP = {"width": 1280, "height": 900}
WIDE = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844, "dsf": 2}


def api(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def set_settings(**fields):
    api("PUT", "/api/settings", fields)


# --------------------------------------------------------------------------- #
# shot definitions
# --------------------------------------------------------------------------- #
# Each shot: name, url, viewport, and optional:
#   element   - CSS selector to screenshot instead of the viewport
#   scroll_to - CSS selector to scroll into view first
#   clicks    - list of CSS selectors to click in order (waits between)
#   fill      - {selector: text} to type into inputs
#   evaluate  - JS string to run after load
#   wait_ms   - extra settle time
#   setup     - python callable run before the shot (for settings toggles)
SHOTS: list[dict] = [
    # -- home / today --
    {"name": "today.png", "url": "/", "viewport": WIDE},
    {"name": "weather-ribbon.png", "url": "/", "viewport": WIDE,
     "element": "#weather-ribbon"},
    {"name": "noaa-alerts.png", "url": "/", "viewport": DESKTOP,
     "scroll_to": "#today-alerts"},
    # -- plants --
    {"name": "plants.png", "url": "/plants"},
    {"name": "plants-year.png", "url": "/plants"},
    {"name": "calendar.png", "url": "/calendar"},
    {"name": "plant-photos.png", "url": "/plants",
     "clicks": ["[data-open-plant]"], "scroll_to": "#plant-modal"},
    {"name": "plant-identify.png", "url": "/plants",
     "setup": "plantnet_key", "clicks": ["#plant-identify"]},
    {"name": "crop-lookup.png", "url": "/plants",
     "clicks": ["#plant-add-toggle", "#crop-lookup-btn"]},
    {"name": "crop-community.png", "url": "/plants",
     "clicks": ["#plant-add-toggle", "#crop-lookup-btn"],
     "fill": {"#crop-q": "tomato"}, "clicks_after": ["#crop-results button"]},
    {"name": "crop-openplantdb.png", "url": "/plants",
     "clicks": ["#plant-add-toggle", "#crop-lookup-btn"],
     "fill": {"#crop-q": "tomato"}, "clicks_after": ["#crop-results button"],
     "scroll_to": "#crop-detail"},
    # -- logs / photos --
    {"name": "observations.png", "url": "/observations",
     "scroll_to": "#obs-form"},
    {"name": "photos.png", "url": "/photos"},
    {"name": "match.png", "url": "/match"},
    {"name": "slideshow.png", "url": "/slideshow",
     "evaluate": "select_slideshow_album", "wait_ms": 1500},
    # -- seeds --
    {"name": "seeds.png", "url": "/seeds"},
    {"name": "seed-stash.png", "url": "/seeds",
     "clicks": ["#seed-tabbtn-catalog"]},
    {"name": "packet-flip.png", "url": "/seeds",
     "clicks": ["#seed-tabbtn-catalog"]},
    {"name": "packet-library-picker.png", "url": "/seeds",
     "clicks": ["#seed-tabbtn-catalog", "#catalog-add", "#packet-library-front"]},
    {"name": "order-assistant.png", "url": "/seeds",
     "clicks": ["#seed-tabbtn-assistant"]},
    # -- review / blog --
    {"name": "blog.png", "url": "/blog"},
    {"name": "review.png", "url": "/review"},
    {"name": "scorecard.png", "url": "/scorecard"},
    {"name": "review-yearbook.png", "url": "/review",
     "scroll_to": "#review-yearbook"},
    {"name": "true-cost.png", "url": "/review",
     "scroll_to": "#truecost-summary"},
    {"name": "caretaker-sheet.png", "url": "/api/caretaker-sheet"},
    # -- planner --
    {"name": "planner.png", "url": "/planner"},
    {"name": "planner-3d.png", "url": "/planner", "clicks": ["#view-3d"]},
    {"name": "planner-heatmap.png", "url": "/planner",
     "clicks": ["#heatmap-toggle"]},
    {"name": "succession.png", "url": "/planner",
     "scroll_to": "#succession-panel"},
    # -- misc pages --
    {"name": "tags.png", "url": "/tags"},
    {"name": "fertilizers.png", "url": "/fertilizers"},
    {"name": "seedlings.png", "url": "/seedlings"},
    {"name": "pantry.png", "url": "/pantry"},
    {"name": "pests.png", "url": "/pests"},
    {"name": "pest-guide.png", "url": "/pests",
     "fill": {"#guide-q": "aphid"}, "clicks": ["#guide-go"],
     "scroll_to": "#guide-results"},
    {"name": "import.png", "url": "/import"},
    {"name": "backup.png", "url": "/backup"},
    # -- quick log --
    {"name": "quick.png", "url": "/quick"},
    {"name": "quick-undo.png", "url": "/quick",
     "clicks": ['button[data-act="water"]'], "wait_ms": 1200},
    {"name": "quick-voice.png", "url": "/quick",
     "scroll_to": "#voice-log-card"},
    {"name": "voice-quicklog.png", "url": "/quick",
     "element": "#voice-log-card"},
    {"name": "ai-log.png", "url": "/quick", "evaluate": "inject_ai_drafts",
     "scroll_to": "#ai-log-card"},
    # -- agent --
    {"name": "agent-tab.png", "url": "/agent", "viewport": WIDE,
     "setup": "agent_on"},
    # -- costs (Hermes features front and center) --
    {"name": "costs.png", "url": "/costs"},
    {"name": "invoices.png", "url": "/costs",
     "scroll_to": "#invoices-rows"},
    {"name": "receipt-scan.png", "url": "/costs",
     "evaluate": "inject_scan_review", "element": "#scan-review"},
    # -- vendors directory (default seeds tab) --
    {"name": "vendors.png", "url": "/seeds"},
    # -- settings --
    {"name": "settings.png", "url": "/settings"},
    {"name": "ai-openrouter.png", "url": "/settings",
     "setup": "openrouter_nokey", "scroll_to": "#set-ai-provider"},
    {"name": "ai-openrouter-models.png", "url": "/settings",
     "setup": "openrouter_key", "scroll_to": "#set-ai-provider"},
    {"name": "settings-tabs.png", "url": "/settings",
     "scroll_to": "#mobile-tab-chips"},
    {"name": "zone-detect.png", "url": "/settings",
     "scroll_to": "#zone-detect"},
    # -- mobile --
    {"name": "nav-mobile.png", "url": "/plants", "viewport": MOBILE,
     "mobile": True},
    {"name": "nav-mobile-more.png", "url": "/plants", "viewport": MOBILE,
     "mobile": True, "clicks": ["#mobile-nav-more"]},
    # -- nav details --
    {"name": "nav-fern.png", "url": "/", "viewport": WIDE,
     "element": "#desktop-nav"},
    {"name": "nav-groups.png", "url": "/", "viewport": WIDE,
     "element": "#desktop-nav"},
]


# --------------------------------------------------------------------------- #
# setup helpers (run before a shot)
# --------------------------------------------------------------------------- #
def setup_plantnet_key():
    set_settings(plantnet_api_key="demo-key-for-screenshots")


def setup_openrouter_nokey():
    set_settings(ai_provider="openrouter", openrouter_api_key="")


def setup_openrouter_key():
    set_settings(ai_provider="openrouter", openrouter_api_key="sk-or-demo-key",
                 openrouter_model="meta-llama/llama-3.1-8b-instruct:free")


def setup_agent_on():
    # show the chat UI (with seeded threads) instead of the "assistant is off" card
    set_settings(local_ai_enabled=True, ai_provider="openrouter",
                 openrouter_api_key="sk-or-demo-key",
                 openrouter_model="openai/gpt-4o-mini", ai_chat_enabled=True)


SETUPS = {
    "plantnet_key": setup_plantnet_key,
    "openrouter_nokey": setup_openrouter_nokey,
    "openrouter_key": setup_openrouter_key,
    "agent_on": setup_agent_on,
}


# --------------------------------------------------------------------------- #
# evaluate snippets (run in page after load)
# --------------------------------------------------------------------------- #
INJECT_AI_DRAFTS = """
() => {
  const card0 = document.querySelector('#ai-log-card');
  if (card0) card0.classList.remove('hidden');
  const ta = document.querySelector('#ai-log-text');
  if (ta) ta.value = 'watered the tomatoes and harvested 3 basil for pesto, fed the sungolds';
  const host = document.querySelector('#ai-log-drafts');
  if (!host) return 'no drafts host';
  const card = (icon, label, plant, extra) => `
    <div class="rounded-xl bg-beige-100 px-3 py-2 ring-1 ring-beige-300 space-y-2">
      <div class="flex items-center justify-between gap-2">
        <span class="font-semibold text-navy-800">${icon} ${label}</span>
      </div>
      <label class="block"><span class="lbl">Plant</span>
        <input class="inp text-sm" value="${plant}" readonly /></label>
      ${extra}
      <label class="block"><span class="lbl">Notes</span>
        <input class="inp text-sm" value="" /></label>
    </div>`;
  host.innerHTML =
    card('💧', 'Water', 'Cherokee Purple',
         `<label class="block"><span class="lbl">Detail</span><input class="inp text-sm" value="deep watering at the base" /></label>`) +
    card('🧺', 'Harvest', 'Genovese Basil',
         `<label class="block"><span class="lbl">Quantity</span><input class="inp text-sm" value="3" /></label>
          <label class="block"><span class="lbl">Notes</span><input class="inp text-sm" value="for tonight's pesto" /></label>`) +
    card('🧪', 'Feed', 'Sungold',
         `<label class="block"><span class="lbl">Product</span><input class="inp text-sm" value="fish emulsion" /></label>`);
  const actions = document.querySelector('#ai-log-actions');
  if (actions) { actions.classList.remove('hidden'); actions.classList.add('flex'); }
  return 'drafts injected';
}
"""

INJECT_SCAN_REVIEW = """
() => {
  const host = document.querySelector('#scan-review');
  if (!host) return 'no scan-review host';
  host.classList.remove('hidden');
  host.innerHTML = `
    <div class="rounded-xl bg-beige-50 p-4 ring-1 ring-beige-200">
      <p class="font-semibold text-navy-800">📷 Scanned receipt</p>
      <dl class="mt-2 space-y-1 text-sm text-navy-600">
        <div><dt class="inline text-navy-400">Vendor: </dt>
          <dd class="inline font-semibold text-navy-800">Territorial Seed</dd></div>
        <div><dt class="inline text-navy-400">Date: </dt>
          <dd class="inline font-semibold text-navy-800">2026-10-08</dd></div>
        <div><dt class="inline text-navy-400">Order #: </dt>
          <dd class="inline font-semibold text-navy-800">WW1149159</dd></div>
        <div><dt class="inline text-navy-400">Total: </dt>
          <dd class="inline font-semibold text-navy-800">$56.53</dd></div>
        <div><dt class="inline text-navy-400">Items: </dt>
          <dd class="inline font-semibold text-navy-800">Fall Garlic Festival x1, Costoluto Fiorentino Tomato</dd></div>
      </dl>
      <div class="mt-3 flex gap-2">
        <button type="button" class="btn-primary text-sm">Use these values</button>
        <button type="button" class="btn-ghost text-sm">Dismiss</button>
      </div>
    </div>`;
  return 'scan review injected';
}
"""

SELECT_SLIDESHOW_ALBUM = """
() => {
  const sel = document.querySelector('#fs-album');
  if (!sel || sel.options.length < 2) return 'no albums';
  sel.selectedIndex = 1;
  sel.dispatchEvent(new Event('change', {bubbles: true}));
  return 'album selected: ' + sel.value;
}
"""

EVALUATES = {"inject_ai_drafts": INJECT_AI_DRAFTS,
             "inject_scan_review": INJECT_SCAN_REVIEW,
             "select_slideshow_album": SELECT_SLIDESHOW_ALBUM}


# --------------------------------------------------------------------------- #
# runner
# --------------------------------------------------------------------------- #
def wait_for_server():
    import urllib.error
    for _ in range(60):
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=5) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(1)
    sys.exit("server did not come up")


def run_playwright(only: set[str] | None):
    from playwright.sync_api import sync_playwright

    # strip proxy vars: the egress proxy breaks localhost in Chromium
    env = {k: v for k, v in os.environ.items()
           if "proxy" not in k.lower()}
    tailwind_js = TAILWIND.read_text()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=str(CHROME),
            env=env,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(ignore_https_errors=True)
        # Tailwind CDN is blocked in the sandbox; serve the local copy.
        context.route(
            "**/cdn.tailwindcss.com**",
            lambda route: route.fulfill(
                body=tailwind_js, content_type="application/javascript"),
        )
        page = context.new_page()

        for shot in SHOTS:
            if only and shot["name"] not in only:
                continue
            name = shot["name"]
            vp = shot.get("viewport", DESKTOP)
            is_mobile = shot.get("mobile", False)
            if "dsf" in vp:
                # device scale factor needs CDP emulation (sync API)
                cdp = page.context.new_cdp_session(page)
                cdp.send("Emulation.setDeviceMetricsOverride", {
                    "width": vp["width"], "height": vp["height"],
                    "deviceScaleFactor": vp["dsf"], "mobile": is_mobile})
            else:
                page.set_viewport_size(vp)

            if shot.get("setup"):
                SETUPS[shot["setup"]]()

            print(f"shooting {name} ...", flush=True)
            page.goto(BASE + shot["url"], wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(1200)

            for sel in shot.get("clicks", []):
                try:
                    page.click(sel, timeout=10000)
                    page.wait_for_timeout(900)
                except Exception as e:
                    print(f"  !! click failed {sel}: {e}")

            for sel, text in shot.get("fill", {}).items():
                try:
                    page.fill(sel, text, timeout=10000)
                    page.wait_for_timeout(1200)  # debounce search
                except Exception as e:
                    print(f"  !! fill failed {sel}: {e}")

            for sel in shot.get("clicks_after", []):
                try:
                    page.click(sel, timeout=10000)
                    page.wait_for_timeout(900)
                except Exception as e:
                    print(f"  !! click_after failed {sel}: {e}")

            if shot.get("evaluate"):
                try:
                    print("  eval:", page.evaluate(EVALUATES[shot["evaluate"]]))
                except Exception as e:
                    print(f"  !! evaluate failed: {e}")
                page.wait_for_timeout(600)

            if shot.get("scroll_to"):
                try:
                    page.locator(shot["scroll_to"]).first.scroll_into_view_if_needed(
                        timeout=10000)
                    page.wait_for_timeout(700)
                except Exception as e:
                    print(f"  !! scroll failed {shot['scroll_to']}: {e}")

            page.wait_for_timeout(shot.get("wait_ms", 400))

            out = SHOTS_DIR / name
            if shot.get("element"):
                try:
                    page.locator(shot["element"]).first.screenshot(path=str(out))
                except Exception as e:
                    print(f"  !! element shot failed, falling back to viewport: {e}")
                    page.screenshot(path=str(out))
            else:
                page.screenshot(path=str(out))
            print(f"  wrote {out}")

        browser.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="",
                    help="comma-separated screenshot filenames to (re)take")
    ap.add_argument("--list", action="store_true",
                    help="list all shot names and exit")
    ap.add_argument("--data-dir", default="",
                    help="reuse an existing seeded data dir instead of reseeding")
    args = ap.parse_args()

    if args.list:
        for s in SHOTS:
            print(s["name"], "->", s["url"])
        return

    only = set(x.strip() for x in args.only.split(",") if x.strip()) or None

    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = Path(tempfile.mkdtemp(prefix="verdant-shots-"))
        print(f"seeding demo data into {data_dir} ...")
        env = dict(os.environ, GARDEN_DATA_DIR=str(data_dir),
                   GARDEN_UPLOAD_DIR=str(data_dir / "uploads"))
        subprocess.run([sys.executable, str(REPO / "scripts" / "seed_demo.py")],
                       env=env, check=True, cwd=str(REPO))

    server_env = dict(os.environ, GARDEN_DATA_DIR=str(data_dir),
                      GARDEN_UPLOAD_DIR=str(data_dir / "uploads"))
    # keep proxy vars for the server so NOAA/OpenRouter calls can go out
    print(f"starting server on :{PORT} ...")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        env=server_env, cwd=str(REPO),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server()
        run_playwright(only)
    finally:
        server.terminate()
        server.wait(timeout=15)
    print("done.")


if __name__ == "__main__":
    main()
