"""Small helpers for locating the bronze/silver/gold data layers."""

from __future__ import annotations

from pathlib import Path

from data_foundry.config import Settings, settings


def raw_dir(cfg: Settings = settings) -> Path:
    return cfg.raw_dir


def staging_dir(cfg: Settings = settings) -> Path:
    return cfg.staging_dir


def curated_dir(cfg: Settings = settings) -> Path:
    return cfg.curated_dir


def runs_dir(cfg: Settings = settings) -> Path:
    return cfg.curated_dir / "runs"


def run_dir(run_id: str, cfg: Settings = settings) -> Path:
    return runs_dir(cfg) / run_id


def latest_pointer(cfg: Settings = settings) -> Path:
    return cfg.curated_dir / "latest"


def ensure_layer_dirs(cfg: Settings = settings) -> None:
    for layer_dir in (cfg.raw_dir, cfg.staging_dir, cfg.curated_dir):
        layer_dir.mkdir(parents=True, exist_ok=True)
