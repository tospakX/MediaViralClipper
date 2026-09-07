"""Headless browser smoke test; run directly through scripts/with_server.py."""

import os
import tempfile
from pathlib import Path

from playwright.sync_api import ConsoleMessage, sync_playwright


def main() -> None:
    console_errors: list[str] = []

    def capture_console(message: ConsoleMessage) -> None:
        if message.type == "error":
            console_errors.append(message.text)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", capture_console)
        page.goto("http://127.0.0.1:8765", wait_until="networkidle")

        skip_link = page.locator(".skip-link")
        assert skip_link.evaluate("node => getComputedStyle(node).opacity") == "0"
        page.keyboard.press("Tab")
        assert skip_link.evaluate("node => getComputedStyle(node).opacity") == "1"
        page.keyboard.press("Enter")
        assert page.url.endswith("#job-form")
        assert page.get_by_role("heading", name="Episodes in. Vertical clips out.").is_visible()
        assert page.locator("#system-label").text_content() in {
            "Ollama ready",
            "Ready · fallback judge",
        }
        assert page.get_by_label("Best clips").count() == 0
        assert page.get_by_role("button", name="Choose a folder").is_visible()
        assert page.get_by_role("button", name="Choose one video").is_visible()
        page.get_by_role("button", name="Choose a folder").click()
        assert page.get_by_role("dialog", name="Choose a folder").is_visible()
        page.locator("#browser-list .browser-entry").first.wait_for(timeout=5_000)
        assert page.get_by_role("button", name="Queue this folder").is_visible()
        page.get_by_role("button", name="Close file browser").click()

        page.get_by_text("Settings", exact=True).click()
        assert page.get_by_label("Captions", exact=True).is_visible()
        assert page.get_by_label("Speech model").is_visible()
        assert page.locator("#previous-cuts").count() == 0
        assert page.locator("#preview-empty").is_visible()
        assert page.locator("#preview-content").is_hidden()
        page.screenshot(path="/tmp/media-viral-clipper-desktop.png", full_page=True)
        page.get_by_text("Paste a path instead", exact=True).click()

        sample = os.environ.get("CLIPPER_SAMPLE")
        if sample and Path(sample).is_file():
            output = Path(tempfile.mkdtemp(prefix="clipper-browser-"))
            inputs = output / "episodes"
            inputs.mkdir()
            (inputs / "episode.mkv").symlink_to(Path(sample).resolve())
            page.get_by_label("Episode or folder path").fill(str(inputs))
            page.get_by_label("Episode or folder path").dispatch_event("change")
            page.locator("#source-note").get_by_text("1 video ready to queue").wait_for()
            page.get_by_label("Output folder").fill(str(output / "cuts"))
            page.get_by_label("Minimum duration in seconds").fill("4")
            page.get_by_label("Maximum duration in seconds").fill("9")
            page.get_by_text("Analyze only", exact=True).click()
            page.get_by_role("button", name="Queue 1 video").click()
            page.locator(".episode-row").wait_for(timeout=20_000)
            page.locator(".episode-action").wait_for(timeout=20_000)
            page.locator(".episode-action").click()
            assert page.locator("#clip-strip .clip-tab").count() >= 1
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto("http://127.0.0.1:8765", wait_until="networkidle")
        assert page.locator("body").evaluate("node => node.scrollWidth <= window.innerWidth")
        assert page.get_by_role("button", name="Choose a folder").is_visible()
        page.screenshot(path="/tmp/media-viral-clipper-mobile.png", full_page=True)

        assert console_errors == [], console_errors
        browser.close()


if __name__ == "__main__":
    main()
