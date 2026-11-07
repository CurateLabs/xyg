"""Reproduce optional resource absence with the actual chart rendering proof."""

import importlib
import sys
from pathlib import Path


def main() -> None:
    sys.modules["resource"] = None
    sys.path.insert(0, str(Path.cwd()))
    proof = importlib.import_module("scripts.chunked_chart_evidence")
    report = proof.run(Path(sys.argv[1]), sys.argv[2])
    assert report["host_peak_rss_kib"] is None
    assert report["rss_available"] is False
    assert len(report["requests"]) == 4
    assert all(request["exact_pixel_match"] for request in report["requests"])
    print("Four full-image comparisons pass with resource unavailable; RSS explicitly null")


if __name__ == "__main__":
    main()
