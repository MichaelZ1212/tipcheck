"""Take every screenshot the report needs, automatically, from the running app (makes ~4 real checks, about $0.01).

One-time setup:   pip install playwright
                  (uses the Edge or Chrome already on your computer; only if neither works:
                   python -m playwright install chromium)
Then, with the app running in another terminal (python run.py):
                  python scripts/screenshots.py
Saves PNGs into docs/screenshots/.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)


def run_example(page, example, budget="0.05", running_shot=None):
    page.goto(URL)
    page.wait_for_timeout(800)
    page.click(f"[data-example={example}]")
    page.fill("#budget", budget)
    page.click("#go")
    if running_shot:
        page.wait_for_selector("#ag-bull.running, #ag-bull.done", timeout=90_000)
        page.wait_for_timeout(4000)
        page.locator("#live").screenshot(path=str(OUT / running_shot))
    page.wait_for_selector(".verdict, .error-card", timeout=240_000)
    page.wait_for_timeout(800)


def launch(p):
    """Use a browser that is already installed (Edge ships with Windows), so nothing big has to be downloaded."""
    for channel in ("msedge", "chrome", None):
        try:
            return p.chromium.launch(channel=channel) if channel else p.chromium.launch()
        except Exception as exc:
            last = exc
    raise SystemExit(f"No browser found for screenshots: {last}")


with sync_playwright() as p:
    browser = launch(p)
    page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2)

    page.goto(URL)
    page.wait_for_timeout(800)
    page.screenshot(path=str(OUT / "home.png"))
    print("home.png")

    run_example(page, "friend", running_shot="running.png")
    print("running.png")
    top = page.locator(".verdict").bounding_box()["y"] + page.evaluate("window.scrollY")
    claims = page.locator("text=The tip's claims, checked").locator("xpath=..").bounding_box()
    page.screenshot(path=str(OUT / "result.png"), full_page=True,
                    clip={"x": 0, "y": top - 10, "width": 1280, "height": claims["y"] + page.evaluate("window.scrollY") + claims["height"] - top + 20})
    print("result.png")
    case = page.locator(".case.bull").bounding_box()
    lists = page.locator(".lists").bounding_box()
    sy = page.evaluate("window.scrollY")
    page.screenshot(path=str(OUT / "cases.png"), full_page=True,
                    clip={"x": 0, "y": case["y"] + sy - 10, "width": 1280, "height": lists["y"] + lists["height"] - case["y"] + 20})
    print("cases.png")
    page.locator(".ev-list details").first.click()
    page.locator(".ev-list").screenshot(path=str(OUT / "evidence.png"))
    print("evidence.png")

    run_example(page, "attack")
    v = page.locator(".verdict").bounding_box()
    sy = page.evaluate("window.scrollY")
    page.screenshot(path=str(OUT / "attack.png"), full_page=True,
                    clip={"x": 0, "y": v["y"] + sy - 10, "width": 1280, "height": 520})
    page.locator("text=🛡️ Safety checks").locator("xpath=..").screenshot(path=str(OUT / "attack_safety.png"))
    print("attack.png, attack_safety.png")

    run_example(page, "reddit", budget="0.0005")
    page.locator("#live").screenshot(path=str(OUT / "budget.png"))
    print("budget.png")

    page.click("[data-view=history]")
    page.wait_for_timeout(1000)
    page.locator("#view-history").screenshot(path=str(OUT / "history.png"))
    print("history.png")
    browser.close()
print(f"Saved to {OUT}")
