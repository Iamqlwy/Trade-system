---
name: stock-monitor
description: >
  生成 A 股自定义监控脚本。当用户描述监控条件（涨跌幅、成交量异动、价格突破、
  多股联动、均线交叉、板块联动等）时，在工作区创建 Python 监控脚本，然后通过上传接口注册到系统。
  系统自动调度执行，触发时推送通知。
category: trading
---

# A 股监控脚本生成指南

## 处理原则

1. **条件模糊时必须澄清**：如果用户描述的监控条件不够明确（例如"帮我监控一下这个股票"而没有说明具体条件），使用 AskUserQuestion 工具向用户确认，**禁止揣测用户意图**。
2. **元数据不要事事问用户**：执行间隔（interval）、冷却时间（cooldown）、具体股票代码等元数据，用户可以在平台 UI 上随时调整。脚本中不需要硬编码这些参数。你可以给出合理的默认建议，但不必反复确认。多股票模式不要问具体监控什么股票。
3. **先读取 market-data 技能**：编写脚本前，必须先通过 SkillView 工具加载 `market-data` 技能，了解数据文件的完整格式定义。
4. **写完后必须编译验证**：脚本写好后，用 Shell 工具执行 `python -m py_compile check.py` 验证语法正确性。
5. **编译通过后必须上传**：使用 HTTP 请求上传脚本到系统，由系统调度执行。
6. **使用 argparse 解析参数**：脚本使用 `argparse` 定义参数，不用 `sys.argv[1:]`。`--stock` 是系统保留参数（仅在 `has_stock_param=true` 时传入），其他参数在 metadata 中声明，用户可在 UI 调整。
7. **每次执行处理一个场景**：每次调用只处理一只股票或一个条件，输出单个 JSON object。

### 使用TODO工具记录待办事项

---

## 执行模型

### 两种脚本模式

| 模式 | `has_stock_param` | 调用方式 | 适用场景 |
|------|-------------------|---------|---------|
| **多股票模式** | `true` | `python check.py --stock 600519.SH --param_name value` | 涨跌幅、新高、均线交叉等单股条件 |
| **固定条件模式** | `false` | `python check.py --param_name value`  | 多股关联、板块联动等复杂固定条件 |

- **多股票模式**：引擎逐只股票执行一次 `docker exec`，每次传入 `--stock CODE` 和用户配置的参数
- **固定条件模式**：条件完全写死在脚本中（股票代码、逻辑都硬编码），引擎直接执行，无外部参数

### 脚本调用方式

```bash
# has_stock_param=true（参数可调，逐只股票）
python check.py --stock 600519.SH --lookback_days 30

# has_stock_param=false（条件写死，无stock参数）
python check.py --ma 20
```

- 使用 `argparse` 解析参数，**不要用 `sys.argv[1:]`**
- `--stock` 是系统保留参数名，只在 `has_stock_param=true` 时传入
- 其他自定义参数在 `script_metadata.parameters` 中声明，用户可在平台 UI 调整
- 脚本在持久 Docker 容器中执行（`--read-only`, `--network=none`）
- 行情数据目录挂载到 `/data/klines/`（只读）
- 内存限制 256MB，CPU 限制 0.5 核
- 超时 30 秒

### 输入输出契约

**输入：**
- `--stock CODE`：股票代码（仅 `has_stock_param=true` 时）
- `--param_name value`：用户配置的参数（由 metadata 定义）

**输出（stdout）：**
- stdout 中必须包含**一个 JSON 对象**（允许有其他 debug 行，后端从中解析出第一个 JSON dict）

```json
{
  "triggered": true,
  "message": "600519.SH 创30日新高，当前价1888.50",
  "data": {"high": 1888.50, "prev_high_30d": 1850.00}
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `triggered` | bool | ✅ | 是否触发告警 |
| `message` | str | ✅ | 触发原因描述（显示在通知中） |
| `data` | dict | ❌ | 附加数据（可选，记录在日志中） |

**错误格式：**
```json
{"error": "错误描述"}
```

- 如果没有触发：`{"triggered": false, "message": ""}`
- 如果发生错误：`{"error": "错误描述"}`，引擎会记录错误；连续 5 次错误会自动禁用监控

### 后端如何解析脚本输出

1. **检测 Python 异常堆栈**：先检查 stderr 是否含 `Traceback (most recent call last)`，若含则直接判定为脚本错误
2. **从 stdout 提取 JSON**：从前往后扫描 stdout 各行，找到第一个可被 `json.loads` 解析为 dict 的行即采用
3. **回退到 stderr**：若 stdout 中无 JSON，检查 stderr 是否含异常堆栈或 JSON 错误消息
4. **格式校验**：检查 `"error"` 字段 → 报错；检查 `"triggered"` 字段存在
5. **触发处理**：对有 `triggered=true` 的结果按 (monitor, stock_code) 冷却并推送告警

---

> 数据格式和获取函数（编码、字段定义、`get_latest_price`、`get_continuous_1m`、`get_daily` 等）全部由 `market-data` 技能负责，编写脚本前必须先加载该技能。

---

---

## 脚本模板

### 多股票模式（has_stock_param=true）

> 数据获取函数（`get_continuous_1m`、`get_daily`、`get_latest_price`）定义在 `market-data` 技能中，脚本中直接调用即可，无需重复定义。

```python
import argparse
import json


def check(stock_code: str, params: dict) -> dict:
    """
    单只股票的监控逻辑。
    params 包含用户在 UI 上配置的参数值。
    返回: {"triggered": bool, "message": str, "data": dict}
    """
    # ========== 在此编写你的监控逻辑 ==========

    # 示例：涨跌幅超过 3%
    from market_data import get_continuous_1m  # 见 market-data 技能
    bars = get_continuous_1m(stock_code, n_bars=5)
    if bars.empty or len(bars) < 2:
        return {"triggered": False, "message": "数据不足"}

    current_price = bars.iloc[-1]["close"]
    open_price = bars.iloc[0]["open"]
    if open_price == 0:
        return {"triggered": False, "message": ""}
    pct_change = (current_price - open_price) / open_price * 100

    if abs(pct_change) >= 3.0:
        direction = "上涨" if pct_change > 0 else "下跌"
        return {
            "triggered": True,
            "message": f"{stock_code} {direction} {abs(pct_change):.2f}%",
            "data": {"price": current_price, "pct_change": round(pct_change, 2)},
        }

    return {"triggered": False, "message": ""}


# ── 入口：argparse 解析参数 ──
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="涨跌幅监控")
    parser.add_argument("--stock", type=str, required=True, help="股票代码")
    parser.add_argument("--lookback_days", type=int, default=30, help="回溯天数")
    args = parser.parse_args()

    try:
        params = {"lookback_days": args.lookback_days}
        result = check(stock_code=args.stock, params=params)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
```

> **注意**：每次调用只处理一只股票，输出一个 JSON object。引擎逐只股票执行并聚合结果。

### 固定条件模式（has_stock_param=false）

```python
import json
import pandas as pd
from datetime import datetime

# 条件写死：检测两只特定股票是否同时涨停
STOCK_A = "300866.SZ"  # 中际旭创
STOCK_B = "600584.SH"  # 长电科技

def check():
    """
    复杂固定条件逻辑。
    返回: {"triggered": bool, "message": str, "data": dict}
    """
    # 读取两只股票的实时数据
    # ... (读取逻辑同 get_continuous_1m)

    # 判断是否同时涨停
    # ...

    return {"triggered": True, "message": "中际旭创与长电科技同时涨停", "data": {}}

if __name__ == "__main__":
    try:
        result = check()
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
```

> **注意**：固定条件模式无外部参数，条件完全硬编码在脚本中。

---

## 常见监控模式示例

> 数据获取函数（`get_continuous_1m`、`get_daily`、`get_latest_price`）来自 `market-data` 技能，以下示例直接调用。

### 1. 涨跌幅监控

```python
from market_data import get_continuous_1m, get_daily


def check(stock_code: str) -> dict:
    bars = get_continuous_1m(stock_code, n_bars=5)
    if bars.empty or len(bars) < 2:
        return {"triggered": False, "message": "数据不足"}

    current = bars.iloc[-1]["close"]
    # 用日线昨收计算涨跌幅
    try:
        daily = pd.read_csv(f"/data/klines/daily/{stock_code}.csv", encoding="utf-8")
        if not daily.empty:
            pre_close = daily.iloc[-1]["close"]
            pct = (current - pre_close) / pre_close * 100
            if abs(pct) >= 5.0:
                d = "涨停" if pct > 0 else "大跌"
                return {"triggered": True, "message": f"{stock_code} {d} {abs(pct):.2f}%", "data": {"pct": round(pct, 2)}}
    except Exception:
        pass
    return {"triggered": False, "message": ""}
```

### 2. 成交量异动

```python
from market_data import get_continuous_1m


def check(stock_code: str) -> dict:
    bars = get_continuous_1m(stock_code, n_bars=30)
    if bars.empty or len(bars) < 10:
        return {"triggered": False, "message": "数据不足"}

    # 最近 1 分钟成交量 vs 过去 20 分钟平均
    recent_vol = bars.iloc[-1]["volume"]
    avg_vol = bars.iloc[-21:-1]["volume"].mean()

    if avg_vol > 0 and recent_vol / avg_vol >= 3.0:
        return {
            "triggered": True,
            "message": f"{stock_code} 成交量异动：当前 {recent_vol} 股，是近20分钟均量的 {recent_vol/avg_vol:.1f} 倍",
            "data": {"ratio": round(recent_vol / avg_vol, 2)},
        }
    return {"triggered": False, "message": ""}
```

### 3. 价格突破（N 日新高/新低）

```python
from market_data import get_daily


def check(stock_code: str) -> dict:
    daily = get_daily(stock_code, n_days=30)
    if daily.empty or len(daily) < 20:
        return {"triggered": False, "message": "日线数据不足"}

    current_high = daily.iloc[-1]["high"]
    high_20d = daily.iloc[-21:-1]["high"].max()

    if current_high > high_20d:
        return {
            "triggered": True,
            "message": f"{stock_code} 突破20日新高 {current_high:.2f}",
            "data": {"price": current_high, "prev_high": round(high_20d, 2)},
        }
    return {"triggered": False, "message": ""}
```

### 4. 均线交叉（金叉/死叉）

```python
from market_data import get_continuous_1m


def check(stock_code: str) -> dict:
    bars = get_continuous_1m(stock_code, n_bars=60)
    if bars.empty or len(bars) < 30:
        return {"triggered": False, "message": "数据不足"}

    close = bars["close"]
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()

    # 判断金叉：MA5 从下方穿越 MA20
    if len(ma5) >= 2 and len(ma20) >= 2:
        prev_diff = ma5.iloc[-2] - ma20.iloc[-2]
        curr_diff = ma5.iloc[-1] - ma20.iloc[-1]
        if prev_diff <= 0 and curr_diff > 0:
            return {"triggered": True, "message": f"{stock_code} MA5/MA20 金叉", "data": {}}
        elif prev_diff >= 0 and curr_diff < 0:
            return {"triggered": True, "message": f"{stock_code} MA5/MA20 死叉", "data": {}}

    return {"triggered": False, "message": ""}
```

### 5. 多股联动（关联股票价差偏离）

```python
from market_data import get_continuous_1m


def check(stock_code: str) -> dict:
    # 示例：监控 600519.SH（贵州茅台）与 000858.SZ（五粮液）的比价
    pair = {"600519.SH": "000858.SZ"}
    other_code = pair.get(stock_code)
    if not other_code:
        return {"triggered": False, "message": "非目标股票"}

    bars_a = get_continuous_1m(stock_code, n_bars=5)
    bars_b = get_continuous_1m(other_code, n_bars=5)
    if bars_a.empty or bars_b.empty:
        return {"triggered": False, "message": "数据不足"}

    price_a = bars_a.iloc[-1]["close"]
    price_b = bars_b.iloc[-1]["close"]
    ratio = price_a / price_b if price_b > 0 else 0

    if ratio > 2.5:
        return {
            "triggered": True,
            "message": f"{stock_code}/{other_code} 比价 {ratio:.2f} 超过阈值",
            "data": {"ratio": round(ratio, 4)},
        }
    return {"triggered": False, "message": ""}
```

---

## 错误处理

### 脚本层面的错误处理

1. **文件不存在**：数据文件可能尚未生成（如开盘前），用 `try/except FileNotFoundError` 处理
2. **数据为空**：`len(bars) < N` 时返回 `{"triggered": False, "message": "数据不足"}`，不要抛异常
3. **除零保护**：计算百分比、比值时检查分母是否为零
4. **统一异常捕获**：最外层 `try/except` 捕获所有异常，输出 `{"error": "描述"}`

### 引擎层面的错误处理

引擎按以下优先级判定脚本执行结果：

1. **检查 Docker exec 返回码**：非 0 时，先扫描 stderr 是否含 Python 异常堆栈（`Traceback (most recent call last)`）。若含堆栈，提取最后行作为错误信息；否则取 stderr 前 500 字符作为错误信息。
2. **从 stdout 提取 JSON**：从前往后扫描 stdout 各行，找到第一个可被 `json.loads` 解析为 dict 的行即采用（允许其他行是 debug 输出）。
3. **stdout 无 JSON 时扫描 stderr**：先检查 stderr 是否含 Python 异常堆栈。若含堆栈直接报错。否则在 stderr 中寻找 JSON 错误消息。
4. **格式校验**：检查 `"error"` 字段 → 报错；检查 `"triggered"` 字段存在。
5. **触发处理**：对有 `triggered=true` 的结果按 (monitor, stock_code) 冷却并推送告警。

其他机制：
- 检测到 `{"error": "..."}` 时，引擎记录错误日志
- **连续 5 次执行错误**，引擎自动禁用该监控
- 超时 30 秒未返回结果，视为执行失败
- 冷却机制（cooldown_seconds）防止同一监控+同一股票重复触发

> **关键**：stdout 中只允许有一个 JSON 对象（后端取第一个）。脚本可以 print 调试信息，但如果调试信息恰好也是合法 JSON object，会干扰结果解析。建议调试用文件写入（如 `open("/tmp/debug.log", "a").write(...)`）。

---

## 上传流程

### 步骤 1：编写脚本到工作区

使用 WriteFile 工具将脚本保存到工作区的 `check.py`：

```
WriteFile(file_path="check.py", content="...")
```

### 步骤 2：编译验证

使用 Shell 工具执行语法检查：

```
Shell(command="python -m py_compile check.py")
```

- 编译成功：无输出，退出码 0
- 编译失败：输出错误信息，**必须修复后重新编译**

### 步骤 3：上传到系统

使用 Shell 工具发送 HTTP 请求上传：

```bash
curl -X POST $BACKEND_URL/api/monitors/upload \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <session_id>" \
  -d '{
    "monitor_name": "N日新高监控",
    "description": "检测股票是否创出N日新高",
    "stock_codes": ["600519.SH"],
    "interval": "30s",
    "cooldown_seconds": 300,
    "script_path": "check.py",
    "script_metadata": {
      "name": "N日新高监控",
      "description": "检测股票是否创出N日新高",
      "version": "1.0.0",
      "has_stock_param": true,
      "parameters": [
        {
          "name": "lookback_days",
          "label": "回溯天数",
          "type": "int",
          "default": 30,
          "description": "计算新高的回溯天数",
          "min": 5,
          "max": 250
        }
      ]
    },
    "params": {
      "lookback_days": 30
    }
  }'
```

**参数说明：**

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `monitor_name` | str | ✅ | — | 监控名称（显示在 UI 中） |
| `description` | str | ❌ | `""` | 监控描述 |
| `stock_codes` | list[str] | ❌ | `[]` | 股票代码列表（用户可在 UI 调整） |
| `strategy_ids` | list[str] | ❌ | `[]` | 策略 ID 列表（动态获取持仓股票） |
| `interval` | str | ❌ | `"30s"` | 执行间隔，可选值：`10s`, `30s`, `1m`, `5m`, `10m`, `15m`, `30m`, `1h` |
| `trigger_mode` | str | ❌ | `"periodic"` | 触发模式：`periodic`（定时）/ `manual`（手动） |
| `cooldown_seconds` | int | ❌ | `300` | 冷却时间（秒），防止重复触发 |
| `script_metadata` | dict | ✅ | `{}` | **脚本元数据**，定义参数列表和类型 |
| `params` | dict | ❌ | `{}` | 参数默认值 |
| `script_path` | str | ❌ | `"check.py"` | 工作区内脚本的相对路径 |

**script_metadata 结构：**

```json
{
  "name": "脚本名称",
  "description": "脚本描述",
  "version": "1.0.0",
  "has_stock_param": true,
  "parameters": [
    {
      "name": "参数名（对应 argparse 的 --name）",
      "label": "显示名称",
      "type": "int|float|string|bool|choice",
      "default": "默认值",
      "description": "参数描述",
      "min": 0, "max": 100,
      "choices": [{"value": "a", "label": "选项A"}]
    }
  ]
}
```

- `has_stock_param: true` → 脚本接受 `--stock CODE`，引擎逐只股票执行
- `has_stock_param: false` → 固定条件，无参数，引擎单次执行

**认证成功返回：**
```json
{"monitor_id": "m_a3f2k9", "status": "created"}
```

**认证方式：** `Authorization: Bearer <session_id>`，session_id 是当前 Agent 会话的 ID。

### 步骤 4：告知用户

上传成功后告知用户：
- 监控已创建，给出 monitor_id 和名称
- 提示用户可以在「监控中心」页面查看、编辑（调整股票、间隔、冷却时间等）
- 提示用户可以手动执行测试（UI 上的「执行」按钮）
- 触发告警会实时推送通知

---

## 完整工作流示例

用户说："帮我监控茅台，如果 5 分钟内涨了超过 2% 就提醒我"

**Step 1**：确认意图清晰（茅台=600519.SH，条件明确=5分钟涨幅>2%），无需追问。

**Step 2**：使用 SkillView 工具加载 `market-data`，确认数据格式。

**Step 3**：编写 `check.py` 到工作区（使用 argparse）：

> 数据获取函数（`get_continuous_1m`）来自 `market-data` 技能，直接 复制 到脚本中即可。

```python
import argparse
import json
from market_data import get_continuous_1m


def check(stock_code, params):
    minutes = params.get("minutes", 5)
    threshold = params.get("threshold", 2.0)

    bars = get_continuous_1m(stock_code, n_bars=minutes + 5)
    if bars.empty or len(bars) < minutes + 1:
        return {"triggered": False, "message": "数据不足"}
    price_now = bars.iloc[-1]["close"]
    price_ago = bars.iloc[-(minutes + 1)]["close"]
    if price_ago == 0:
        return {"triggered": False, "message": "价格异常"}
    pct = (price_now - price_ago) / price_ago * 100
    if pct >= threshold:
        return {
            "triggered": True,
            "message": f"{stock_code} {minutes}分钟涨 {pct:.2f}%，当前价 {price_now:.2f}",
            "data": {"pct": round(pct, 2), "price": price_now},
        }
    return {"triggered": False, "message": ""}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="分钟涨幅监控")
    parser.add_argument("--stock", type=str, required=True, help="股票代码")
    parser.add_argument("--minutes", type=int, default=5, help="回溯分钟数")
    parser.add_argument("--threshold", type=float, default=2.0, help="涨幅阈值(%)")
    args = parser.parse_args()

    try:
        params = {"minutes": args.minutes, "threshold": args.threshold}
        result = check(stock_code=args.stock, params=params)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
```

**Step 4**：编译验证 `python -m py_compile check.py`

**Step 5**：上传到系统（含 script_metadata）：
```json
{
  "monitor_name": "茅台5分钟涨幅监控",
  "description": "5分钟涨幅超过2%告警",
  "stock_codes": ["600519.SH"],
  "interval": "30s",
  "cooldown_seconds": 300,
  "script_path": "check.py",
  "script_metadata": {
    "name": "分钟涨幅监控",
    "description": "检测股票N分钟内涨幅超过阈值",
    "version": "1.0.0",
    "has_stock_param": true,
    "parameters": [
      {
        "name": "minutes",
        "label": "回溯分钟数",
        "type": "int",
        "default": 5,
        "description": "计算涨幅的回溯分钟数",
        "min": 1,
        "max": 60
      },
      {
        "name": "threshold",
        "label": "涨幅阈值(%)",
        "type": "float",
        "default": 2.0,
        "description": "触发告警的涨幅阈值",
        "min": 0.5,
        "max": 20.0
      }
    ]
  },
  "params": {
    "minutes": 5,
    "threshold": 2.0
  }
}
```

**Step 6**：告知用户监控已创建，可在监控中心查看和调整参数（回溯分钟数、涨幅阈值等）。
