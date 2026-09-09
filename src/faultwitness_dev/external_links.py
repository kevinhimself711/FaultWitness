from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from faultwitness_dev.checks import repository_files


def check_external_links(root: Path, output_dir: Path | None = None) -> dict[str, object]:
    """Record non-blocking HTTP link observations using request-level deadlines only."""
    urls: set[str] = set()
    pattern = re.compile(r"https?://[^\s)>]+")
    for path in repository_files(root):
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        urls.update(value.rstrip(".,") for value in pattern.findall(text))
    results: list[dict[str, int | str]] = []
    for url in sorted(urls):
        status: int | str
        try:
            request = urllib.request.Request(
                url,
                method="HEAD",
                headers={"User-Agent": "FaultWitness-link-audit/2.0"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
                status = response.status
        except (urllib.error.URLError, TimeoutError) as error:
            status = type(error).__name__
        results.append({"url": url, "status": status})
    report: dict[str, object] = {
        "blocking": False,
        "checked": len(results),
        "results": results,
    }
    output = output_dir or root / ".audit"
    output.mkdir(parents=True, exist_ok=True)
    (output / "external-links.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report
