"""Daily orchestrator: run the P3 pipeline for every target in targets.json.

The 0050 benchmark is fetched once and reused across all targets (each
target's DCA comparison needs it, but there's no reason to hit FinMind once
per target for the same data). A failure on one target is logged and does
not block the others -- this mirrors main_p3's existing "keep last good
data" behavior for a single target, extended across the whole target list.
"""
from __future__ import annotations

from .main_p3 import fetch_benchmark_standalone, run_pipeline
from .targets import load_targets


def main() -> None:
    raw_benchmark, div_events = fetch_benchmark_standalone()

    targets = load_targets()
    failures: list[str] = []
    for target in targets:
        print(f"\n=== {target.id} ===")
        try:
            run_pipeline(target, raw_benchmark, div_events)
        except Exception as e:
            failures.append(target.id)
            print(f"  ✗ {target.id} 更新失敗（保留舊資料）：{e}")

    print(f"\n更新完成：{len(targets) - len(failures)}/{len(targets)} 個標的成功。")
    if failures:
        print(f"以下標的更新失敗，已保留舊資料：{failures}")


if __name__ == "__main__":
    main()
