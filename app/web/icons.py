from functools import lru_cache
from pathlib import Path

from markupsafe import Markup

_ICONS_DIR = Path(__file__).parent / "icons"

# Maps a workflow step key (or any custom key a user invents) to the closest
# Lucide icon, mirroring the lifecycle iconography from docs/inspirations.
STEP_ICONS = {
    "draft": "square-pen",
    "negotiate": "messages-square",
    "sign": "signature",
    "store": "folder-open",
    "renew": "rotate-cw",
    "amend": "pen-line",
    "terminate": "hand",
    "archive": "archive",
    "destruct": "shredder",
}
DEFAULT_STEP_ICON = "circle"


@lru_cache(maxsize=None)
def _load(name: str) -> str:
    svg = (_ICONS_DIR / f"{name}.svg").read_text()
    return svg.split("-->", 1)[-1].strip()


def icon(name: str, css_class: str = "") -> Markup:
    svg = _load(name)
    if css_class:
        svg = svg.replace('class="lucide', f'class="{css_class} lucide', 1)
    return Markup(svg)


def step_icon_name(step_key: str) -> str:
    return STEP_ICONS.get(step_key, DEFAULT_STEP_ICON)
