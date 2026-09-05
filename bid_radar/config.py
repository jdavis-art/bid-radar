"""Configuration: config.yaml (public defaults) + config.local.yaml (private overlay) + env."""
from __future__ import annotations

import copy
import os
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


def load_config(root: Path | None = None) -> dict:
    root = Path(root) if root else project_root()
    with open(root / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    local = root / "config.local.yaml"
    if local.exists():
        with open(local, encoding="utf-8") as fh:
            cfg = _deep_merge(cfg, yaml.safe_load(fh) or {})
    if os.environ.get(ENV_OUTPUT_DIR):
        cfg["output_dir"] = os.environ[ENV_OUTPUT_DIR]
    if os.environ.get(ENV_SAM_KEY):
        cfg.setdefault("sources", {}).setdefault("samgov", {})["api_key"] = os.environ[ENV_SAM_KEY]
    cfg["_root"] = str(root)
    return cfg


def resolve_path(cfg: dict, key: str) -> Path:
    """Resolve output_dir / data_dir / log_dir relative to the project root, expanding ~."""
    raw = Path(os.path.expanduser(cfg[key]))
    return raw if raw.is_absolute() else Path(cfg["_root"]) / raw
