"""Target registry: load targets.json and resolve per-target paths.

This is the single source of truth for "which ETFs does this repo monitor".
Adding a new target means adding an entry here (via scripts/add_target.py or
by hand) -- no new folders, repos, or frontend code required.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGETS_JSON = PROJECT_ROOT / "targets.json"

BENCHMARK_RAW_CSV = PROJECT_ROOT / "data" / "_shared" / "0050_raw.csv"


@dataclass(frozen=True)
class Target:
    id: str
    name: str
    listing_date: str
    split_date: Optional[str] = None
    split_ratio: float = 1.0

    @property
    def split_date_ts(self) -> Optional[pd.Timestamp]:
        return pd.Timestamp(self.split_date) if self.split_date else None

    @property
    def raw_csv(self) -> Path:
        return PROJECT_ROOT / "data" / self.id / "raw" / f"{self.id}_raw.csv"

    @property
    def adjusted_csv(self) -> Path:
        return PROJECT_ROOT / "data" / self.id / "adjusted" / f"{self.id}.csv"

    @property
    def reports_dir(self) -> Path:
        return PROJECT_ROOT / "reports" / self.id

    @property
    def docs_dir(self) -> Path:
        return PROJECT_ROOT / "docs" / self.id


def _load_config() -> dict:
    with TARGETS_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def benchmark_id() -> str:
    return _load_config()["benchmark"]


def load_targets() -> list[Target]:
    return [Target(**t) for t in _load_config()["targets"]]


def get_target(ticker: str) -> Target:
    for t in load_targets():
        if t.id == ticker:
            return t
    raise ValueError(f"Unknown target '{ticker}'. Check targets.json.")
