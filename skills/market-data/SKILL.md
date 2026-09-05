---
name: market-data
description: >
  行情数据存储与访问指南。描述 /data/klines/ 目录下所有行情数据（日K线、分钟K线、指数、
  基本面指标、概念板块、涨停板等）的目录结构、文件格式、字段定义、编码格式和
  单位差异。当需要读取行情数据、编写数据访问代码、或理解数据含义时使用。
category: data
---

# Market Data Storage Guide

This skill documents the structure and format of all market data stored under `/data/klines/`, the central data repository for the quant trading platform.

## Directory Overview

| Directory/File | Description |
|---|---|
| `daily/` | Individual stock daily K-line (CSV, named by ts_code) |
| `1m/` | Individual stock minute-level K-line (CSV, named by ts_code; shared for historical + real-time) |
| `index_daily/` | Index daily K-line (CSV, named by index name e.g. 上证指数.csv) |
| `index_1m/` | Index minute-level K-line (CSV, date and time in separate columns) |
| `indicator/` | Individual stock fundamental indicators (CSV, named by ts_code) |
| `companys/` | Company detailed information (JSON, {ts_code}_{name}.json) |
| `concepts/` | Concept/sector/industry plate data |
| `extra/` | Aggregated daily data (full market daily, sector daily, limit-up boards, etc.) |
| `cache/` | Pickle cache files |
| `stock_basic.csv` | All A-share basic information |
| `hot.csv` | Sector popularity ranking |
| `fina_mainbz_all.csv` | Main business composition |

---

## Daily K-Line (`daily/`)

**File Path:** `/data/klines/daily/{ts_code}.csv` (e.g., `600519.SH.csv`)  
**Encoding:** UTF-8  
**Headers (English):** `ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount`

### Field Definitions

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| ts_code | str | — | Stock code (e.g., `600519.SH`) |
| trade_date | int | yyyyMMdd | Trading date in integer format (e.g., `20250102`) |
| open | float | 元 | Opening price |
| high | float | 元 | Highest price |
| low | float | 元 | Lowest price |
| close | float | 元 | Closing price |
| pre_close | float | 元 | Previous closing price |
| change | float | 元 | Price change (涨跌额) |
| pct_chg | float | % | Percentage change (2.55 = +2.55%) |
| vol | float | **手** | Volume in lots (1 lot = 100 shares) ⚠️ **Critical unit difference** |
| amount | float | 元 | Turnover amount |

### Example Row

```csv
600519.SH,20250102,1678.50,1695.00,1670.20,1688.30,1675.00,13.30,0.79,125680.50,2123456789.50
```

---

## Minute K-Line (`1m/`)

**File Path:** `/data/klines/1m/{ts_code}.csv`  
**Encoding:** **GBK (with BOM)** ⚠️ **Special encoding requirement**  
**Headers (Chinese):** `日期,开盘,最高,最低,收盘,成交量(股),成交额(元)`

> ⚠️ **Note:** The CSV header line also includes `涨跌(元),涨跌幅(%),换手率(%),流通股本(股),总股本(股)` for backward compatibility, but these trailing columns have been **empty since 2026-05-26** when the real-time aggregator took over writes. Only the **first 7 columns** contain data. Expect trailing commas for the empty columns: `10.69,10.69,10.69,10.69,15080,16120520.0,,,,,`.

### Field Definitions

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| 日期 | str | YYYY-MM-DD HH:MM:SS | Date and time string |
| 开盘 | float | 元 | Opening price |
| 最高 | float | 元 | Highest price |
| 最低 | float | 元 | Lowest price |
| 收盘 | float | 元 | Closing price |
| 成交量(股) | int | **股** | Volume in shares ⚠️ **Different from daily!** |
| 成交额(元) | float | 元 | Turnover amount |

### Example Row

```csv
2026-07-14 15:00:00,10.69,10.69,10.69,10.69,15080,16120520.0,,,,,
```

### Real-Time Update Behavior

The real-time aggregator appends to this file every **3 seconds**:
- Same minute → replaces last row
- New minute → appends new row

The aggregator writes only price + volume (7 columns). Trailing commas are preserved for header compatibility but contain no data.

---

## Real-Time 1-Minute K-Line (`temp_1m/`)

**File Path:** `/data/klines/temp_1m/{ts_code}.csv`
**Encoding:** **GBK** (written via `encode("gbk")`, prefixed with UTF-8 BOM `\xef\xbb\xbf` on file creation)
**Headers (Chinese):** `日期,开盘,最高,最低,收盘,成交量(股),成交额(元)`

### Difference from `1m/`

| Aspect | `1m/` | `temp_1m/` |
|--------|-------|------------|
| Purpose | Historical + today's bars (appended by aggregator) | Today's real-time bars only |
| Columns | 12 header columns, but only 7 populated for recent data (same as temp_1m/) | 7 columns (price + volume only) |
| Source | History loaded from disk | Aggregated live from tick data in memory |
| Update | Appended by aggregator (same file as history) | Written independently, incremental flush every 3s |
| Lifetime | Permanent | Cleared daily (cross-date reset) |

### Field Definitions

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| 日期 | str | YYYY-MM-DD HH:MM:SS | Minute timestamp |
| 开盘 | float | 元 | Opening price of the minute |
| 最高 | float | 元 | Highest price of the minute |
| 最低 | float | 元 | Lowest price of the minute |
| 收盘 | float | 元 | Closing price of the minute (last tick) |
| 成交量(股) | int | **股** | Incremental volume in shares within this minute |
| 成交额(元) | float | 元 | Incremental turnover amount within this minute |

### Example Row

```csv
2025-01-02 09:30:00,1678.50,1680.00,1677.00,1679.20,58200,97845600.00
```

### How It Works

The `Kline1mAggregator` runs in the backend and:
1. Samples ticks from `MarketData` every **1 second**
2. Aggregates into in-memory `MinuteBar` structs (open, high, low, close, volume, amount)
3. Flushes to disk every **3 seconds** using incremental writes:
   - **Same minute** → seeks to the last line's byte offset and overwrites it in-place, then truncates
   - **New minute** → appends a new row
4. Resets all in-memory bars and file state on date change

**Volume calculation:** Uses tick-level cumulative volume deltas — `current_tick.volume - previous_tick.volume` — so each bar's volume is the **incremental** volume traded during that specific minute, not the cumulative daily total.

### When to Use Each Source

- **`temp_1m/` alone** — for real-time monitoring scripts that only need today's intraday data
- **`1m/` alone** — for historical analysis (may include partial today data appended by the aggregator)
- **Both merged** — for scripts needing continuous 1m bars spanning across today (see `stock-monitor` skill for merge pattern)

---

## Index Daily K-Line (`index_daily/`)

**File Naming:** `{指数名称}.csv` (named by index name, **not** by code!)  
Examples: `上证指数.csv`, `创业板指.csv`, `沪深300.csv`

### Field Structure

Same structure as `daily/` but with key differences:
- **Price fields** (close/open/high/low/pre_close/change): in **点** (points), not 元
- **vol**: still in **手** (lots)

---

## Index Minute K-Line (`index_1m/`)

**File Path:** `/data/klines/index_1m/{指数代码}.csv`  
**Headers:** `日期,时间,开盘,最高,最低,收盘,成交量,成交额`

### Key Difference

- **日期** and **时间** are **separate columns**
  - 日期: `yyyy-MM-dd` format
  - 时间: `HH:MM` format

### Example Row

```csv
2025-01-02,09:30,3025.50,3028.00,3024.00,3026.80,1250000,3782500000.00
```

---

## Fundamental Indicators (`indicator/`)

**File Path:** `/data/klines/indicator/{ts_code}.csv`

### Field Definitions

| Field | Description | Unit |
|-------|-------------|------|
| ts_code | Stock code | — |
| trade_date | Trading date | yyyyMMdd |
| close | Closing price | 元 |
| turnover_rate | Turnover rate | % |
| turnover_rate_f | Free-float turnover rate | % |
| volume_ratio | Volume ratio | — |
| pe | P/E ratio (static) | — |
| pe_ttm | P/E ratio (TTM) | — |
| pb | P/B ratio | — |
| ps | P/S ratio (static) | — |
| ps_ttm | P/S ratio (TTM) | — |
| dv_ratio | Dividend yield (static) | % |
| dv_ttm | Dividend yield (TTM) | % |
| total_share | Total shares | **万股** |
| float_share | Float shares | **万股** |
| free_share | Free-float shares | **万股** |
| total_mv | Total market value | **万元** |
| circ_mv | Circulating market value | **万元** |

---

## Concept/Sector Plates (`concepts/`)

| File | Description |
|------|-------------|
| `concept.csv` | Concept plate definitions |
| `industry.csv` | Industry plate definitions |
| `industry_children.csv` | Sub-industry mappings |
| `kline/` | Subdirectory containing concept/industry K-line data |

---

## Aggregated Data (`extra/`)

| Subdirectory | Description |
|--------------|-------------|
| `extra/all_daily_basic/` | Daily full-market fundamentals (daily CSVs) |
| `extra/all_sector_daily/` | Daily sector K-line data |
| `extra/all_stocks_daily/` | Daily full-market stock K-line data |
| `extra/zdt/` | Limit-up board (涨停板) data |

---

## Company Information (`companys/`)

**File Format:** JSON  
**Naming:** `{ts_code}_{name}.json` (e.g., `600519_贵州茅台.json`)

### Common Fields

- 经营范围 (Business scope)
- 主营业务 (Main business activities)
- Other company metadata

---

## ⚠️ CRITICAL Unit Differences

**This is the most important section. Misunderstanding these units will cause 100x calculation errors.**

| Data Source | Volume Unit | Price Unit | Header Language | Encoding |
|-------------|-------------|------------|-----------------|----------|
| `/data/klines/daily/` CSV | **手** (×100 = shares) | 元 | English | UTF-8 |
| `/data/klines/1m/` CSV | **股** (shares) | 元 | Chinese | **GBK (BOM)** |
| `/data/klines/temp_1m/` CSV | **股** (shares) | 元 | Chinese | **GBK (BOM)** |
| `/data/klines/indicator/` CSV | 万股 / 万元 | 元 | English | UTF-8 |

### Key Takeaway

- **Daily volume** (`daily/`): measured in **手** (lots), where 1 手 = 100 shares
- **Minute volume** (`1m/`): measured in **股** (shares)
- This is a **100x difference**! Always convert appropriately when comparing or aggregating.

---

## Code Recipes

### Get Latest Price

```python
import pandas as pd

def get_latest_price(stock_code: str) -> float | None:
    """Return the most recent price for a stock.

    Uses temp_1m/ (today's real-time 1m bars) first for freshness.
    Falls back to daily/ close if temp_1m/ is unavailable (e.g. market closed).
    """
    # Try real-time 1m first
    realtime_path = f"/data/klines/temp_1m/{stock_code}.csv"
    try:
        df = pd.read_csv(realtime_path, encoding="gbk")
        if not df.empty:
            return float(df.iloc[-1]["收盘"])
    except (FileNotFoundError, KeyError):
        pass

    # Fallback to daily close
    daily_path = f"/data/klines/daily/{stock_code}.csv"
    try:
        df = pd.read_csv(daily_path, encoding="utf-8")
        if not df.empty:
            return float(df.iloc[-1]["close"])
    except (FileNotFoundError, KeyError):
        return None

    return None
```

### Get Continuous 1m K-Line (Merging `1m/` + `temp_1m/`)

```python
import pandas as pd
from datetime import datetime

def get_continuous_1m(stock_code: str, n_bars: int = 30) -> pd.DataFrame:
    """Read the last N 1-minute bars, merging history and real-time.

    Returns DataFrame with columns: datetime, open, high, low, close, volume, amount.
    volume is in shares (股).
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    cols = ["datetime", "open", "high", "low", "close", "volume", "amount"]

    # 1. Historical 1m (GBK encoding)
    hist_path = f"/data/klines/1m/{stock_code}.csv"
    try:
        hist = pd.read_csv(hist_path, encoding="gbk")
        hist.columns = cols
        if len(hist) > n_bars * 2:
            hist = hist.tail(n_bars * 2)
    except FileNotFoundError:
        hist = pd.DataFrame(columns=cols)

    # 2. Today's real-time 1m (GBK encoding)
    realtime_path = f"/data/klines/temp_1m/{stock_code}.csv"
    try:
        realtime = pd.read_csv(realtime_path, encoding="gbk")
        realtime.columns = cols
        realtime["datetime"] = pd.to_datetime(realtime["datetime"])
        realtime = realtime[realtime["datetime"].dt.date == pd.Timestamp(today_str).date()]
    except FileNotFoundError:
        realtime = pd.DataFrame(columns=cols)

    # 3. Merge and deduplicate by datetime
    if not hist.empty:
        hist["datetime"] = pd.to_datetime(hist["datetime"])
        hist = hist[hist["datetime"].dt.date != pd.Timestamp(today_str).date()]

    merged = pd.concat([hist, realtime], ignore_index=True)
    if merged.empty:
        return merged

    # 4. Tail N bars
    merged = merged.sort_values("datetime").tail(n_bars).reset_index(drop=True)

    for c in ["open", "high", "low", "close", "amount"]:
        merged[c] = pd.to_numeric(merged[c], errors="coerce")
    merged["volume"] = pd.to_numeric(merged["volume"], errors="coerce").astype("int64")

    return merged
```

### Get Continuous Daily K-Line

```python
import pandas as pd
from datetime import datetime

def get_daily(stock_code: str, n_days: int = 30) -> pd.DataFrame:
    """Read the last N daily bars, merging today's 1m bars into a synthetic daily bar.

    Loads historical daily bars from daily/, then aggregates today's 1m bars from
    temp_1m/ into a single synthetic daily bar (open=first 1m open, high=max, low=min,
    close=last 1m close, volume=sum, amount=sum). If temp_1m/ is unavailable
    (e.g. market closed or pre-open), only historical bars are returned.

    Returns DataFrame with columns: trade_date, open, high, low, close, vol, amount.
    vol is in 股 (shares).
    """
    today_str = datetime.now().strftime("%Y%m%d")

    # 1. Historical daily (UTF-8), exclude today (may be stale)
    path = f"/data/klines/daily/{stock_code}.csv"
    try:
        hist = pd.read_csv(path, encoding="utf-8")
        hist = hist[hist["trade_date"].astype(str) < today_str]
        if not hist.empty:
            hist["vol"] = hist["vol"] * 100  # convert 手 → 股
    except FileNotFoundError:
        hist = pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "vol", "amount"])

    # 2. Aggregate today's 1m bars from temp_1m/ into a synthetic daily bar
    realtime_path = f"/data/klines/temp_1m/{stock_code}.csv"
    today_bar = None
    try:
        rt = pd.read_csv(realtime_path, encoding="gbk")
        if not rt.empty:
            today_bar = {
                "trade_date": int(today_str),
                "open": float(rt.iloc[0]["开盘"]),
                "high": float(rt["最高"].max()),
                "low": float(rt["最低"].min()),
                "close": float(rt.iloc[-1]["收盘"]),
                "vol": int(rt["成交量(股)"].sum()),
                "amount": float(rt["成交额(元)"].sum()),
            }
    except FileNotFoundError:
        pass

    # 3. Combine
    if today_bar is not None:
        today_df = pd.DataFrame([today_bar])
        result = pd.concat([hist, today_df], ignore_index=True)
    else:
        result = hist

    if result.empty:
        return pd.DataFrame()

    result = result.sort_values("trade_date").tail(n_days).reset_index(drop=True)
    return result
```

### Get Daily Closes for Multiple Stocks

```python
import pandas as pd

def get_daily_closes(stock_codes: list[str], n_days: int = 30) -> pd.DataFrame:
    """Read close prices for multiple stocks into a wide DataFrame.

    Returns DataFrame indexed by trade_date, each column a stock code.
    """
    result = None
    for code in stock_codes:
        try:
            df = pd.read_csv(f"/data/klines/daily/{code}.csv", encoding="utf-8")
            df = df[["trade_date", "close"]].rename(columns={"close": code})
            df["trade_date"] = df["trade_date"].astype(str)
            df = df.tail(n_days)
            if result is None:
                result = df
            else:
                result = result.merge(df, on="trade_date", how="outer")
        except FileNotFoundError:
            continue
    if result is not None:
        result = result.sort_values("trade_date").reset_index(drop=True)
    return result if result is not None else pd.DataFrame()
```

### Read Indicator Data

```python
import pandas as pd

def get_indicator(stock_code: str) -> pd.DataFrame:
    """Read fundamental indicators for a stock."""
    path = f"/data/klines/indicator/{stock_code}.csv"
    try:
        return pd.read_csv(path, encoding="utf-8")
    except FileNotFoundError:
        return pd.DataFrame()
```

### Encoding Reference

| Data Source | Encoding | Volume Unit | Header Language |
|-------------|----------|-------------|-----------------|
| `daily/` | UTF-8 | **手** (×100 = shares) | English |
| `1m/` | **GBK (BOM)** | **股** (shares) | Chinese |
| `temp_1m/` | **GBK (BOM)** | **股** (shares) | Chinese |
| `indicator/` | UTF-8 | 万股 / 万元 | English |

### Important Notes

1. **All data is unadjusted (不复权)** — no forward/backward adjustment for splits or dividends
2. **Date formats differ**:
   - `trade_date` in daily: integer (`20250102`)
   - `日期` in 1m/temp_1m: string (`"2025-01-02 09:30:00"`)
3. **Always specify encoding** when reading 1m/temp_1m files to avoid garbled characters
4. **Convert volume units** when comparing daily (手) with minute (股) data — multiply by 100
5. **temp_1m/ is the authoritative source for today's data**; `1m/` may also contain today's bars but with trailing empty columns

---

## `stock_basic.csv` Field Definitions

**File Path:** `/data/klines/stock_basic.csv`

| Field | Description |
|-------|-------------|
| ts_code | Stock code (e.g., `600519.SH`) |
| symbol | Symbol |
| name | Stock name |
| area | Geographic area |
| industry | Industry classification |
| fullname | Full company name |
| enname | English name |
| cnspell | Chinese pinyin abbreviation |
| market | Market type |
| exchange | Exchange |
| curr_type | Currency type |
| list_status | Listing status |
| list_date | Listing date |
| is_hs | Hong Kong Stock Connect flag |
| act_name | Actual controller name |
| act_ent_type | Actual controller entity type |

---

## Other Files

### `hot.csv`

Sector popularity ranking data.

### `fina_mainbz_all.csv`

Main business composition (主营业务构成) for all companies.
