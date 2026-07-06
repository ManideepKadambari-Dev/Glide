"""Configuration: a dataclass of tunables, loadable from a TOML file and
overridable on the command line.

Precedence (lowest to highest):  built-in defaults  <  config file  <  CLI.
"""

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

# The hand model lives at the repo root (next to this package) and is
# auto-downloaded on first run if missing.
DEFAULT_MODEL = str(Path(__file__).resolve().parents[1] / "hand_landmarker.task")


@dataclass
class Config:
    # --- camera ---
    camera: int = 0
    width: int = 640
    height: int = 480
    flip: bool = True                # mirror the preview (natural movement)

    # --- cursor ---
    margin: float = 0.12             # dead border of the frame
    min_cutoff: float = 1.0          # One Euro: lower = steadier
    beta: float = 0.5                # One Euro: higher = less lag

    # --- clicks / drag ---
    pinch: float = 0.5               # thumb->finger distance to count as a pinch
    grab: float = 1.2                # openness below this = fist (grab/drag)
    click_cooldown: float = 0.12     # min seconds between clicks

    # --- scroll ---
    scroll_speed: float = 1500.0
    natural_scroll: bool = False

    # --- model ---
    model: str = DEFAULT_MODEL

    # Derived thresholds (hysteresis bands) used by the controller and HUD.
    @property
    def pinch_on(self):
        return self.pinch

    @property
    def pinch_off(self):
        return self.pinch + 0.20

    @property
    def fist_on(self):
        return self.grab

    @property
    def fist_off(self):
        return self.grab + 0.25


# TOML table.key  ->  Config field.
_TOML_MAP = {
    ("camera", "index"): "camera",
    ("camera", "width"): "width",
    ("camera", "height"): "height",
    ("camera", "flip"): "flip",
    ("cursor", "margin"): "margin",
    ("cursor", "min_cutoff"): "min_cutoff",
    ("cursor", "beta"): "beta",
    ("clicks", "pinch"): "pinch",
    ("clicks", "grab"): "grab",
    ("clicks", "click_cooldown"): "click_cooldown",
    ("scroll", "speed"): "scroll_speed",
    ("scroll", "natural"): "natural_scroll",
    ("model", "path"): "model",
}


def _load_toml(path):
    if tomllib is None:
        raise RuntimeError("Reading a TOML config needs Python 3.11+")
    with open(path, "rb") as f:
        data = tomllib.load(f)
    flat = {}
    for (table, key), field in _TOML_MAP.items():
        section = data.get(table, {})
        if key in section:
            flat[field] = section[key]
    return flat


# CLI arg name -> Config field. Only used to apply non-None overrides.
_CLI_FIELDS = (
    "camera", "width", "height", "flip", "margin", "min_cutoff", "beta",
    "pinch", "grab", "click_cooldown", "scroll_speed", "natural_scroll", "model",
)


def build_config(args):
    """Merge defaults, an optional TOML file, and CLI overrides into a Config.

    Returns (config, config_path_or_None).
    """
    path = None
    if getattr(args, "config", None):
        path = Path(args.config)
        if not path.exists():
            raise FileNotFoundError(f"config file not found: {path}")
    else:
        candidate = Path.cwd() / "glide.toml"
        if candidate.exists():
            path = candidate

    cfg = Config()
    if path is not None:
        for field, value in _load_toml(path).items():
            setattr(cfg, field, value)
    for field in _CLI_FIELDS:
        value = getattr(args, field, None)
        if value is not None:
            setattr(cfg, field, value)
    return cfg, path


def to_toml(cfg):
    """Serialise a Config to TOML text (for --print-config)."""
    b = lambda v: "true" if v else "false"
    return (
        "# Glide configuration. Save as glide.toml in the working directory,\n"
        "# or point at it with:  py -m glide --config path/to/file.toml\n\n"
        "[camera]\n"
        f"index = {cfg.camera}\n"
        f"width = {cfg.width}\n"
        f"height = {cfg.height}\n"
        f"flip = {b(cfg.flip)}\n\n"
        "[cursor]\n"
        f"margin = {cfg.margin}\n"
        f"min_cutoff = {cfg.min_cutoff}     # lower = steadier cursor\n"
        f"beta = {cfg.beta}            # higher = less lag when moving fast\n\n"
        "[clicks]\n"
        f"pinch = {cfg.pinch}           # thumb-to-finger distance to click; higher = easier\n"
        f"grab = {cfg.grab}            # hand openness below this grabs (drag)\n"
        f"click_cooldown = {cfg.click_cooldown}\n\n"
        "[scroll]\n"
        f"speed = {cfg.scroll_speed}\n"
        f"natural = {b(cfg.natural_scroll)}\n"
    )
