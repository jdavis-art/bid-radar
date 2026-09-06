"""Configuration: config.yaml (public defaults) + config.local.yaml (private overlay) + env.
Environment overrides come from the real environment first, then from a gitignored .env at the root."""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path

import yaml

ENV_OUTPUT_DIR = "BID_RADAR_OUTPUT_DIR"
ENV_SAM_KEY = "SAM_API_KEY"


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


_DOTENV_LINE = re.compile(r"""^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$""")


def load_dotenv(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines (quotes, `export`, comments tolerated). Never logs values."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _DOTENV_LINE.match(line)
        if not m:
            continue
        value = m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[m.group(1)] = value
    return out


def load_config(root: Path | None = None) -> dict:
    root = Path(root) if root else project_root()
    with open(root / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    local = root / "config.local.yaml"
    if local.exists():
        with open(local, encoding="utf-8") as fh:
            cfg = _deep_merge(cfg, yaml.safe_load(fh) or {})
    dotenv = load_dotenv(root / ".env")
    env = lambda name: os.environ.get(name) or dotenv.get(name)  # noqa: E731
    if env(ENV_OUTPUT_DIR):
        cfg["output_dir"] = env(ENV_OUTPUT_DIR)
    if env(ENV_SAM_KEY):
        cfg.setdefault("sources", {}).setdefault("samgov", {})["api_key"] = env(ENV_SAM_KEY)
    cfg["_root"] = str(root)
    return cfg


def resolve_path(cfg: dict, key: str) -> Path:
    """Resolve output_dir / data_dir / log_dir relative to the project root, expanding ~."""
    raw = Path(os.path.expanduser(cfg[key]))
    return raw if raw.is_absolute() else Path(cfg["_root"]) / raw
