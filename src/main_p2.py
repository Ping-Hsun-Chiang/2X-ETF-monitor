"""P2 entry point: run backtest split into pre-split / post-split segments (capital-pool model)."""
from __future__ import annotations

import argparse
from typing import Optional

import pandas as pd

from .backtest import BacktestResult, Round, Trade, run_backtest
from .plot_backtest import plot_backtest
from .targets import Target, get_target


def load_adjusted(target: Target) -> pd.DataFrame:
    return pd.read_csv(target.adjusted_csv, parse_dates=["date"])


def build_segments(target: Target) -> list[dict]:
    """One segment for the whole history if the target never split; otherwise
    a pre-split and a post-split segment (moving averages must not span the
    discontinuous split boundary)."""
    split_date = target.split_date_ts
    if split_date is None:
        return [{
            "key": "full",
            "label": f"{target.listing_date} 起",
            "end_date": None,
            "start_date": None,
        }]
    return [
        {
            "key": "pre_split",
            "label": f"分割前（{target.listing_date} ~ {(split_date - pd.Timedelta(days=1)).date()}，未還原前價格區間）",
            "end_date": split_date,
            "start_date": None,
        },
        {
            "key": "post_split",
            "label": f"分割後（{split_date.date()} 起）",
            "end_date": None,
            "start_date": split_date,
        },
    ]


def trades_to_df(trades: list[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=[
            "date", "action", "price",
            "capital_before", "capital_after", "invested_amount",
            "shares_before", "shares_after",
            "avg_cost_before", "avg_cost_after",
        ])
    return pd.DataFrame([
        {
            "date": t.date.strftime("%Y-%m-%d"),
            "action": t.action.value,
            "price": round(t.price, 4),
            "capital_before": round(t.capital_before, 2),
            "capital_after": round(t.capital_after, 2),
            "invested_amount": round(t.invested_amount, 2),
            "shares_before": round(t.shares_before, 4),
            "shares_after": round(t.shares_after, 4),
            "avg_cost_before": round(t.avg_cost_before, 4),
            "avg_cost_after": round(t.avg_cost_after, 4),
        }
        for t in trades
    ])


def rounds_to_df(rounds: list[Round]) -> pd.DataFrame:
    if not rounds:
        return pd.DataFrame(columns=[
            "entry_date", "exit_date", "days_held",
            "initial_capital", "entry_avg_price", "exit_price", "position_taken",
            "total_invested", "total_proceeds", "pnl", "pnl_pct",
            "capital_after", "ma60_alerted",
        ])
    return pd.DataFrame([
        {
            "entry_date": r.entry_date.strftime("%Y-%m-%d"),
            "exit_date": r.exit_date.strftime("%Y-%m-%d"),
            "days_held": r.days_held,
            "initial_capital": round(r.initial_capital, 2),
            "entry_avg_price": round(r.entry_avg_price, 4),
            "exit_price": round(r.exit_price, 4),
            "position_taken": r.position_taken.value,
            "total_invested": round(r.total_invested, 2),
            "total_proceeds": round(r.total_proceeds, 2),
            "pnl": round(r.pnl, 2),
            "pnl_pct": round(r.pnl_pct * 100, 2),
            "capital_after": round(r.capital_after, 2),
            "ma60_alerted": r.ma60_alerted,
        }
        for r in rounds
    ])


def print_stats(label: str, result: BacktestResult, df: pd.DataFrame,
                start: Optional[pd.Timestamp], end: Optional[pd.Timestamp]) -> None:
    view = df
    if start is not None:
        view = view[view["date"] >= start]
    if end is not None:
        view = view[view["date"] < end]
    if len(view) == 0:
        print(f"\n=== {label} ===\n(此段區間內無資料)")
        return
    stats = result.stats
    total_deposits = sum(d.amount for d in result.deposits)
    print(f"\n=== 回測統計｜{label} ===")
    print(f"實際回測期間    : {view['date'].iloc[0].date()} ~ {view['date'].iloc[-1].date()}（{len(view)} 個交易日）")
    print(f"總入金          : {total_deposits:,.0f} TWD（每月 20K × {len(result.deposits)} 個月）")
    print(f"總輪次          : {stats['num_rounds']}")
    print(f"總進場次數      : {stats['num_entries']}")
    print(f"MA60 警戒輪數   : {stats['num_alerts']}")
    print(f"平均持有天數    : {stats['avg_days_held']:.1f} 天")
    print(f"平均每輪報酬率  : {stats['avg_pnl_pct']:+.2f}%")
    print(f"勝率            : {stats['win_rate_pct']:.1f}%")
    print(f"累積實現損益    : {stats['total_pnl']:+,.0f} TWD")
    print(f"期末資本池      : {result.final_capital_pool:,.0f} TWD")


def run_segment(df: pd.DataFrame, seg: dict) -> BacktestResult:
    if seg["end_date"] is not None:
        df_seg = df[df["date"] < seg["end_date"]].reset_index(drop=True)
        return run_backtest(df_seg, start_date=seg["start_date"])
    return run_backtest(df, start_date=seg["start_date"])


def run(target: Target) -> None:
    df = load_adjusted(target)
    target.reports_dir.mkdir(parents=True, exist_ok=True)

    for seg in build_segments(target):
        result = run_segment(df, seg)
        print_stats(seg["label"], result, result.df, seg["start_date"], seg["end_date"])

        trades_df = trades_to_df(result.trades)
        rounds_df = rounds_to_df(result.rounds)
        trades_path = target.reports_dir / f"trades_{seg['key']}.csv"
        rounds_path = target.reports_dir / f"rounds_{seg['key']}.csv"
        trades_df.to_csv(trades_path, index=False)
        rounds_df.to_csv(rounds_path, index=False)

        plot_path = target.reports_dir / f"backtest_{seg['key']}.png"
        plot_backtest(
            result.df,
            result.trades,
            plot_path,
            title=f"{target.id} 資本池策略回測｜{seg['label']}",
            start_date=seg["start_date"],
        )

        print(f"  → {trades_path}（{len(trades_df)} 筆）")
        print(f"  → {rounds_path}（{len(rounds_df)} 輪）")
        print(f"  → {plot_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Target id as defined in targets.json")
    args = parser.parse_args()
    run(get_target(args.ticker))


if __name__ == "__main__":
    main()
