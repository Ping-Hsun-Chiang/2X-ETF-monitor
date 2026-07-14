"""Plot backtest: price + MAs + trade markers (fixed-tranche strategy)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from .backtest import Trade
from .strategy import Action

matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft JhengHei",
    "Microsoft YaHei",
    "SimHei",
    "Arial",
]
matplotlib.rcParams["axes.unicode_minus"] = False


def _scatter(ax, points: list[tuple[pd.Timestamp, float]], **kwargs) -> None:
    if not points:
        return
    d, p = zip(*points)
    ax.scatter(list(d), list(p), zorder=5, **kwargs)


def plot_backtest(
    df: pd.DataFrame,
    trades: list[Trade],
    output_path: Path,
    title: str = "MA5/MA20/MA60 固定分批策略回測",
    start_date: "Optional[pd.Timestamp]" = None,
) -> None:
    if start_date is not None:
        df = df[df["date"] >= start_date]
        trades = [t for t in trades if t.date >= start_date]

    fig, ax1 = plt.subplots(figsize=(14, 6))

    ax1.plot(df["date"], df["close"], label="收盤價（分割還原後）", color="black", linewidth=1)
    ax1.plot(df["date"], df["ma5"], label="週線 MA5", color="tab:orange", linewidth=0.8)
    ax1.plot(df["date"], df["ma20"], label="月線 MA20", color="tab:blue", linewidth=0.8)
    ax1.plot(df["date"], df["ma60"], label="季線 MA60", color="tab:purple", linewidth=0.8)

    _scatter(ax1,
             [(t.date, t.price) for t in trades if t.action is Action.BUY_TRANCHE_1],
             marker="^", color="green", s=45, label="第一批（破週線）")
    _scatter(ax1,
             [(t.date, t.price) for t in trades if t.action is Action.BUY_TRANCHE_2],
             marker="^", color="darkgreen", s=70, label="第二批（破月線）")
    _scatter(ax1,
             [(t.date, t.price) for t in trades if t.action is Action.ALERT_MA60],
             marker="x", color="orange", s=55, label="MA60 警戒")
    _scatter(ax1,
             [(t.date, t.price) for t in trades if t.action is Action.SELL_ALL],
             marker="v", color="red", s=60, label="出場（獲利 +7.5%）")

    ax1.set_title(title)
    ax1.set_ylabel("價格 (TWD)")
    ax1.set_xlabel("日期")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.3)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=110)
    plt.close(fig)
