"""P1 entry point: fetch a target's history, split-adjust, save both CSVs, verify."""
from __future__ import annotations

import argparse
from typing import Optional

import pandas as pd

from .fetch_data import fetch_daily_close
from .split_adjust import adjust_for_split
from .targets import Target, get_target


def save_csv(df: pd.DataFrame, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    out.to_csv(path, index=False)


def build_split_window(
    raw: pd.DataFrame, adjusted: pd.DataFrame, split_date: pd.Timestamp, days: int = 5
) -> pd.DataFrame:
    """Return raw vs adjusted close for `days` trading days around split_date."""
    combined = raw.rename(columns={"close": "close_raw"}).merge(
        adjusted.rename(columns={"close": "close_adj"}), on="date"
    )
    idx = int(combined["date"].searchsorted(split_date))
    lo = max(idx - days, 0)
    hi = min(idx + days, len(combined))
    window = combined.iloc[lo:hi].copy()
    window["date"] = window["date"].dt.strftime("%Y-%m-%d")
    return window


def summarize(raw: pd.DataFrame, adjusted: pd.DataFrame, split_date: Optional[pd.Timestamp]) -> None:
    print(
        f"共取得 {len(raw)} 筆交易日資料，"
        f"範圍 {raw['date'].min().date()} ~ {raw['date'].max().date()}"
    )
    if split_date is None:
        print("\n（此標的無股票分割紀錄，無需檢查跳空）")
        return

    print(f"\n=== 分割日 {split_date.date()} 前後 5 個交易日（未還原 vs 還原後） ===")
    window = build_split_window(raw, adjusted, split_date, days=5)
    print(window.to_string(index=False))

    # 計算分割日與前一交易日之間的跳空幅度，還原後應趨近於 0
    combined = raw.rename(columns={"close": "close_raw"}).merge(
        adjusted.rename(columns={"close": "close_adj"}), on="date"
    )
    idx = int(combined["date"].searchsorted(split_date))
    if 0 < idx < len(combined):
        prev = combined.iloc[idx - 1]
        curr = combined.iloc[idx]
        raw_gap = (curr["close_raw"] - prev["close_raw"]) / prev["close_raw"] * 100
        adj_gap = (curr["close_adj"] - prev["close_adj"]) / prev["close_adj"] * 100
        print(
            f"\n分割日相對前一日跳空：未還原 {raw_gap:+.2f}% / 還原後 {adj_gap:+.2f}%"
        )


def run(target: Target) -> None:
    print(f"抓取 {target.id} 收盤價（來源：FinMind）...")
    raw = fetch_daily_close(stock_id=target.id, start_date=target.listing_date)

    save_csv(raw, target.raw_csv)
    print(f"原始未還原資料：{target.raw_csv}")

    adjusted = adjust_for_split(raw, split_date=target.split_date_ts, ratio=target.split_ratio)
    save_csv(adjusted, target.adjusted_csv)
    print(f"分割還原後資料：{target.adjusted_csv}")

    summarize(raw, adjusted, target.split_date_ts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Target id as defined in targets.json")
    args = parser.parse_args()
    run(get_target(args.ticker))


if __name__ == "__main__":
    main()
