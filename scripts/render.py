# scripts/render.py — partial (assets helper only; full file in Task 6)
import re
from pathlib import Path


def load_assets(source_html: str = "cortex-catalyst/26.6.1.html") -> dict:
    """Extract base64 image data URIs from an existing release page."""
    content = Path(source_html).read_text()
    favicon_match = re.search(r'href="(data:image/png;base64,[^"]+)"', content)
    logo_match = re.search(r'<img src="(data:image/png;base64,[^"]+)"', content)
    bg_match = re.search(
        r"background-image:\s*url\('(data:image/png;base64,[^']+)'\)", content
    )
    if not (favicon_match and logo_match and bg_match):
        raise RuntimeError(f"Could not extract base64 assets from {source_html}")
    return {
        "favicon": favicon_match.group(1),
        "logo": logo_match.group(1),
        "bg": bg_match.group(1),
    }
