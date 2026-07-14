# 2X ETF 波段訊號監控

以 MA5（週線）/ MA20（月線）/ MA60（季線）為進出場依據、每月固定入金、**資本池動態分批投入** 的波段訊號監控，支援多檔 2x 槓桿 ETF 標的物。每個交易日收盤後由 GitHub Actions 自動抓資料、計算訊號、更新網頁。**純顯示用途，非投資建議、不自動下單。**

這個 repo 取代了原本一檔標的一個 repo（`00631L-monitor`、`00685L-monitor`）的做法：所有標的共用同一套策略邏輯、同一套前端、同一個每日排程，差別只在 `targets.json` 裡的幾個欄位。新增標的物不需要開新 repo，見下方「如何新增標的物」。

## 線上資源

- 網站（選標的物入口）：<https://ping-hsun-chiang.github.io/2X-ETF-monitor/>
- 各標的物頁面：`/{標的代號}/`（例：`/00631L/`），每個標的都有：
  - `index.html` — 今日訊號監控（策略 I / III 雙軌）
  - `annual.html` — 主策略年度回測投報率
  - `comparison.html` — 五策略回測對照 (I~V)
  - `dca.html` — 持續投入 · 大盤比較
- JSON 端點：每個標的物在 `docs/{id}/` 下各有一份 `latest.json`、`history.json`、`live_trades.json`、`annual_backtest.json` 等（欄位與舊版單標的 repo 相同）
- Actions 記錄：<https://github.com/Ping-Hsun-Chiang/2X-ETF-monitor/actions>

## 資金模型

- **月度入金**：每月第一個交易日，資本池自動 +20,000（模擬發薪投入）
- **資本池**：可自由累積。沒觸發訊號的月份錢會攢在池裡，觸發時一次投出（例：3 個月沒訊號後池子 60,000，觸發時第一批投 30,000、第二批把剩 30,000 投出）
- **獲利複利**：出場後全部持股 × 出場價回到資本池，下輪進場基數變大
- 沒有月度上限

## 策略邏輯（策略 I，各標的通用）

| 目前部位 | 觸發條件 | 動作 |
|---|---|---|
| 空手 | 收盤 < MA5 且 資本池 > 0 | 第一批買進：投入 **資本池 × 0.5** → 半倉 |
| 半倉 | 收盤 < MA20 且 資本池 > 0 | 第二批加碼：投入 **剩餘資本池全部** → 滿倉 |
| 半倉 / 滿倉 | 收盤 < MA60（本輪首次） | MA60 警戒訊號（純提示，不自動加碼） |
| 半倉 / 滿倉 | 累積損益 ≥ +7.5% | 全數獲利出場、回到空手 |

策略 III（單日跌 1%/3% 觸發、+3% 出場）與策略 II/IV/V（五策略對照頁用）邏輯見 `src/strategy_iii.py` / `src/strategies_5.py`。

**行為細節：**
- 同一天可以連鎖觸發（例：當日已跌破 MA5 又跌破 MA20 → 同日先第一批再第二批）
- 進場當日不允許同日出場，至少留隔一交易日
- MA60 警戒：只在**有部位 & 本輪首次跌破**時觸發，之後同輪內不再重報，是否手動加碼由使用者自行判斷
- 損益率 = (當前收盤 / 持股均價) - 1；達 +7.5% 全數 sell

## 專案結構

```
targets.json               # 唯一設定來源：每個標的物一筆（id、中文名、掛牌日、分割日/比例）

src/
  targets.py                Target dataclass + load_targets()/get_target()，算出每個標的的路徑
  fetch_data.py              FinMind 抓歷史收盤價（任一標的皆可，stock_id 為參數）
  split_adjust.py            股票分割還原（無分割標的傳 split_date=None）
  strategy.py / strategy_b.py / strategy_iii.py   策略邏輯、狀態機、常數（各標的共用）
  backtest.py                資本池模型、月度入金、trades/rounds/deposits
  state.py                   從 backtest 結果建 LatestState
  annual_report.py           按年切分、產出年度統計
  comparison_report.py       策略 A/B 年度對照
  strategies_5.py            五策略 (I~V) 年度對照
  dca_report.py              DCA 對照（0050 大盤 vs 本標的 buy-and-hold vs 策略 I/III）
  plot_backtest.py           回測結果作圖
  main_p1.py                 P1：--ticker 抓資料 → 分割還原 → CSV
  main_p2.py                 P2：--ticker 分割前/後兩段回測
  main_p3.py                 P3：--ticker 每日訊號更新，run_pipeline() 可被外部注入已抓好的 0050 基準
  daily_update.py            每日排程用：0050 只抓一次，迴圈跑過 targets.json 全部標的

scripts/
  add_target.py              新增標的物：寫 targets.json + 從 docs/_shared 建立前端頁面

data/
  _shared/0050_raw.csv        大盤基準（所有標的共用，DCA 對照用）
  {id}/raw/{id}_raw.csv        未還原原始收盤價
  {id}/adjusted/{id}.csv       分割還原後收盤價（策略計算用這份）

reports/{id}/                 P2 回測產出（backtest_*.png、trades/rounds_*.csv）
notebooks/{id}/                探索用 notebook（原封不動搬自舊 repo，未參數化）

docs/
  index.html + landing.js     進站選標的物頁，讀 targets.json 列卡片
  targets.json                 公開版設定（daily_update.py 每次跑都會從根目錄 targets.json 同步）
  style.css / nav.js / meta.js / app.js / annual.js / comparison.js / dca.js
                                共用前端資源（純資料驅動，不含任何標的專屬文字）
  _shared/*.html               每個標的頁面的模板（含 window.TARGET_ID 佔位字串）
  {id}/*.html                  由 _shared 複製、代入該標的 id 的實際頁面
  {id}/*.json                  main_p3 產出的該標的資料

.github/workflows/daily-signal.yml   單一排程，跑過 targets.json 全部標的
```

## 每日自動更新流程

- Cron：`0 6 * * 1-5`（週一至週五 UTC 06:00 = 台北 14:00）
- 流程：`python -m src.daily_update` → 0050 基準只抓一次 → 逐一標的抓資料、算訊號、產出 JSON
- 任一標的 FinMind 抓取失敗只會跳過該標的（保留舊資料），不影響其他標的
- 若所有標的的 `data/` + `docs/` 都無變化（非交易日）→ 跳過 commit
- 有變化 → 以 `github-actions[bot]` 身份 commit + push；GitHub Pages 隨後自動 rebuild

## 常用手動指令

Windows PowerShell 建議先 `$env:PYTHONIOENCODING="utf-8"`。

```bash
pip install -r requirements.txt

python -m src.main_p1 --ticker 00631L   # 重新抓歷史、分割還原、產出兩份 CSV
python -m src.main_p2 --ticker 00631L   # 分割前 / 分割後兩段回測（產出 reports/00631L/）
python -m src.main_p3 --ticker 00631L   # 單一標的每日訊號更新（產出 docs/00631L/ 底下的 JSON）
python -m src.daily_update               # 所有標的一次跑完（0050 只抓一次）

gh workflow run daily-signal.yml --ref main
gh run list --workflow=daily-signal.yml --limit=3
```

## 如何新增標的物

不需要開新 repo。步驟：

```bash
python scripts/add_target.py <代號> "<中文全名>" <掛牌日 YYYY-MM-DD> \
  [--split-date YYYY-MM-DD --split-ratio N]   # 沒有分割紀錄就省略這兩個參數

# 例：新增一檔沒分割過的標的
python scripts/add_target.py 00670L "富邦台灣加權正2" 2019-04-01

python -m src.main_p1 --ticker 00670L   # 補歷史資料
python -m src.main_p2 --ticker 00670L   # 補回測 reports/
python -m src.main_p3 --ticker 00670L   # 產出第一份 JSON

git add -A && git commit -m "[Add] onboard 00670L"
git push
```

之後每日排程會自動抓這個新標的，不用再改任何 workflow 或前端程式碼。

## 如何調參數

| 想改的東西 | 檔案 | 常數 |
|---|---|---|
| 週線 / 月線 / 季線期別 | `src/strategy.py` | `MA_SHORT` / `MA_LONG` / `MA_QUARTER` |
| 每月入金金額 | `src/strategy.py` | `MONTHLY_DEPOSIT` |
| 出場獲利門檻 | `src/strategy.py` | `PROFIT_EXIT_THRESHOLD` |
| 實盤模擬起始日 | `src/strategy.py` | `LIVE_START_DATE` |
| 標的清單 / 掛牌日 / 分割日期比例 | `targets.json` | 見上方「如何新增標的物」 |
| 排程時間 | `.github/workflows/daily-signal.yml` | `schedule.cron`（UTC） |
| DCA 對照用大盤基準 | `targets.json` | `benchmark`（目前固定 `0050`） |

## 錯誤處理慣例

- FinMind API 失敗 → 該標的拋例外 → `daily_update.py` 捕捉、印出錯誤、繼續處理下一個標的；該標的的 CSV/JSON 不會被覆寫、不會 commit 壞資料
- 觸發速率限制時可考慮在 workflow 加 `FINMIND_TOKEN` 環境變數並改 `fetch_daily_close(token=...)`

## 已知限制

- 策略無停損：MA60 警戒為訊號、不強制出場；沒達 +7.5% 就一直留倉
- 熊市（如 2015、2018、2022）可能整年卡倉、未實現損益為負
- 網頁顯示的分割前價位為原始未還原值；策略內部仍用還原後計算，兩者一致
- `docs/_shared/*.html` 是模板，改了之後要記得同步套用到既有的 `docs/{id}/*.html`（`scripts/add_target.py` 只在新增標的時複製一次，不會回頭同步既有標的）

## 免責聲明

本工具為個人策略回測與訊號監控用途，不構成投資建議。實際交易的風險由使用者自行承擔。
