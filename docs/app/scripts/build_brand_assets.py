"""Rebuild the XYG data hero and social card from source, without remote assets."""

import os
from base64 import b64encode
from pathlib import Path

from branding import XYG_WORDMARK_PATHS
from playwright.sync_api import sync_playwright
from xyg_examples import DEFAULT_PALETTE, build_sdf_plots

import xyg

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parents[1]


def main() -> None:
    """Render the deterministic probability-field chart and vector social card."""
    source = build_sdf_plots().bins_scatter
    chart = xyg.chart(
        *source.children,
        xyg.theme(
            background=DEFAULT_PALETTE.dark_background,
            plot_background=DEFAULT_PALETTE.dark_background,
        ),
        width=source.width,
        height=source.height,
        padding=(0, 0, 0, 0),
        hover=False,
        select=False,
        brush=False,
        crosshair=False,
    )
    with sync_playwright() as playwright:
        os.environ.setdefault("XYG_BROWSER", playwright.chromium.executable_path)
    chart.to_png(
        str(REPO_ROOT / "spec/assets/xyg-sdf-binned-scatter.png"),
        scale=1,
        engine=xyg.Engine.chromium,
    )

    paths = "".join(
        f'<path d="{path}" stroke="{color or "#FCFCFD"}"/>' for path, color in XYG_WORDMARK_PATHS
    )
    # The card is a vector layout and typography, not a benchmark figure.
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630"
        viewBox="0 0 1200 630" role="img" aria-labelledby="title desc">
      <title id="title">XYG — Graphs and charts. Your design.</title>
      <desc id="desc">Graph visualization and charting for Python, Node.js, and WebAssembly.
        Forked for GraphForge's billion-scale graph visualization goal. Alpha.</desc>
      <rect width="1200" height="630" fill="#090A0B"/>
      <path d="M0 588H1200" stroke="#6E56CF" stroke-width="6"/>
      <g transform="translate(78 70) scale(2)" fill="none" stroke-width="4"
          stroke-linecap="square">{paths}</g>
      <g fill="#FCFCFD" font-family="Instrument Sans, sans-serif">
        <text x="78" y="245" font-size="76" font-weight="650">Graphs and charts.</text>
        <text x="78" y="337" font-size="76" font-weight="650" fill="#A594E8">Your design.</text>
        <text x="78" y="415" font-size="27" fill="#D4D4D8">Python · Node.js · WebAssembly</text>
        <text x="78" y="469" font-size="27" fill="#D4D4D8">Built for GraphForge. Open to your data.</text>
        <text x="78" y="550" font-size="21" fill="#A1A1AA">CurateLabs / XYG</text>
        <text x="1115" y="550" text-anchor="end" font-size="21" fill="#A594E8">ALPHA</text>
      </g>
    </svg>"""
    (APP_ROOT / "assets/xyg-social-card.svg").write_text(svg + "\n", encoding="utf-8")

    font_url = "data:font/ttf;base64," + b64encode(
        (APP_ROOT / "assets/fonts/InstrumentSans-wdth-wght.ttf").read_bytes()
    ).decode("ascii")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
            page.goto((APP_ROOT / "assets/xyg-social-card.svg").as_uri())
            page.evaluate(
                """css => {
                    const style = document.createElementNS('http://www.w3.org/2000/svg', 'style');
                    style.textContent = css;
                    document.documentElement.appendChild(style);
                }""",
                f'@font-face {{font-family: "Instrument Sans"; src: url("{font_url}");}}',
            )
            page.evaluate("document.fonts.load('650 76px \"Instrument Sans\"')")
            page.evaluate("document.fonts.ready")
            page.screenshot(path=str(APP_ROOT / "assets/xyg-social-card.png"))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
