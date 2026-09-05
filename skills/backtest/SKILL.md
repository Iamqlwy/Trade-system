---
name: backtest
description: >
  A股策略回测指南。聚焦回测特有的交易规则（T+1、涨跌停、费用）、
  常见陷阱（未来函数、幸存者偏差、单位混淆）以及结果可视化。
  数据读取和格式定义由 market-data 技能负责。
category: trading
---

# A股策略回测指南

## 处理原则

1. 编写回测脚本前，必须先加载 `market-data` 技能了解数据格式。
2. 数据获取函数直接使用 `market-data` 技能的示范，不要在回测脚本中重复定义。
3. 回测结束后**必须**生成净值曲线 + 回撤曲线的 PNG 图表，展示给用户。
4. 策略逻辑用户说不清楚就追问，**不能揣测**。
5. 使用 TODO 工具记录待办事项。

---

## 回测流程（7 步）

```
Step 1 → 确认回测参数
Step 2 → 加载数据
Step 3 → 计算策略信号（⚠️ 避免未来函数）
Step 4 → 运行回测循环（T+1 / 涨跌停 / 费用 / 撮合）
Step 5 → 计算绩效指标
Step 6 → 生成可视化图表
Step 7 → 输出结果
```

---

## Step 1：确认回测参数

用户没说清楚的必须追问确认。

| 参数 | 要点 |
|------|------|
| 股票代码 | 单只或多只 |
| 回测区间 | yyyyMMdd 格式 |
| 初始资金 | 默认 100 万 |
| 策略逻辑 | 买入条件 + 卖出条件 |
| 策略参数 | 如 MA 周期、阈值等 |

---

## Step 2：加载数据

必须使用SKILLVIEW加载 **market-data** 技能。

- daily 的 `vol` 是**手**（×100 = 股），1m 的 `成交量(股)` 是**股** — 差 100 倍
- 1m 文件是 **GBK** 编码，不是 UTF-8
- 数据**不复权**，分红送股会带来价格跳空
- 停牌日数据缺失，需要 `reindex` 填充，否则回测循环日期不连续

---

## Step 3：计算策略信号（⚠️ 未来函数）

**原则：任何依赖 bar 内统计量（收盘价、均线、最高最低）的决策，延迟至少 1 根 bar。**

- 用 `shift(1)` 拿到上一天的信号，当天用**开盘价**执行
- 金叉/死叉信号需要 `shift(2)` 才能确认 — 因为金叉当天的收盘价/均线值盘中不可知
- 涨停板封死 → 信号不会过，跌停板封死 → 信号不会过（都应在每日循环中检查）

---

## Step 4：回测循环

每根 bar 按以下顺序处理：

```
检查涨跌停 → 获取信号（来自 Step 3，已 shift）→ 执行交易 → 扣除费用 → 结算净值
```

### T+1

用 `total_shares` 和 `today_bought` 两个变量区分即可：买入时两边都加，卖出时只从 `total - today_bought` 卖出，每日收盘后 `today_bought = 0`。

### 涨跌停

涨停（`close ≈ pre_close × 1.1`）跳过买入，跌停（`close ≈ pre_close × 0.9`）跳过卖出。创业板/科创板 20%，ST 5%。检查时用 `abs(close - limit) < 0.005` 的容差。

### 费用

- 佣金：双向，万 2.5，单笔最低 5 元
- 印花税：**仅卖出**，千分之 0.5（2023 年 8 月后）
- 小额交易时最低佣金不可忽略

### 撮合价

用**开盘价** `open` 撮合，不要用收盘价 — 开盘价在交易开始时立即可知，不会引入未来函数。保守做法也可以用 `min(open, close)` 买入 / `max(open, close)` 卖出。

---

## Step 5：绩效指标

核心指标：总收益、年化收益（252 个交易日）、最大回撤、夏普比率（无风险利率默认 2.5%）、卡尔玛比率、交易次数。

---

## Step 6：可视化

生成**双面板**图表（净值曲线在上、回撤曲线在下），`plt.savefig` 到 `/workspace/backtest_{STOCK}_{START}_{END}.png`。

- 净值曲线用 A 股红（`#e74c3c`），正收益区域浅红填充，负收益区域浅绿填充
- 回撤曲线用绿色（`#27ae60`）面积图
- 标题包含股票代码、策略名、区间、收益率和最大回撤
- 横轴标签稀疏化（每 1/10 标一个），避免重叠
- 用 `matplotlib.use("Agg")` + 英文标签

---

## Step 7：输出结果

两个部分缺一不可：

1. **绩效表格** — markdown 表格，列出关键指标数值
2. **图表 PNG** — 用 Read 工具读取图片文件，嵌入 markdown 展示

```
## Backtest Result: {STOCK} ({START} → {END})

| Metric | Value |
|--------|-------|
| Total Return | +23.45% |
| Annual Return | +18.22% |
| Max Drawdown | -12.37% |
| Sharpe Ratio | 1.45 |
| Trades | 12 |

![Chart](/workspace/backtest_{STOCK}_{START}_{END}.png)
```

---

## 完整示例参考

以下是最精简的双均线回测脚本结构（省略数据加载和绘图细节，仅展示关键骨架）：

```python
import pandas as pd
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ── 参数 ──
STOCK = "000001.SZ"
START, END = 20240101, 20241231
CASH = 1_000_000
FAST, SLOW = 5, 20

# ── 加载 ──
df = pd.read_csv(f"/data/klines/daily/{STOCK}.csv", encoding="utf-8")
df = df[(df["trade_date"] >= START) & (df["trade_date"] <= END)].sort_values("trade_date").reset_index(drop=True)

# ── 信号（shift=1 避免未来函数）──
df["ma_f"] = df["close"].rolling(FAST).mean()
df["ma_s"] = df["close"].rolling(SLOW).mean()
df["sig"] = (df["ma_f"].shift(1) > df["ma_s"].shift(1)).astype(int)

# ── 回测 ──
cash, shares, today = CASH, 0, 0
recs = []
for i in range(1, len(df)):
    r = df.iloc[i]
    prev = df.iloc[i - 1]
    op, cl, pc = r["open"], r["close"], prev["close"]

    # 涨跌停
    up = abs(op - pc * 1.1) < 0.005
    dn = abs(op - pc * 0.9) < 0.005

    # 买入
    if prev["sig"] == 0 and r["sig"] == 1 and shares == 0 and not up:
        n = int(cash / (op * 100)) * 100
        if n >= 100:
            cost = n * op
            cash -= cost + max(cost * 0.00025, 5)  # 佣金含最低5
            shares += n; today += n

    # 卖出
    elif prev["sig"] == 1 and r["sig"] == 0 and shares > 0 and not dn:
        rev = shares * op
        cash += rev - max(rev * 0.00025, 5) - rev * 0.0005  # 佣金+印花税
        shares = 0

    recs.append({"date": str(r["trade_date"]), "nav": cash + shares * cl})
    today = 0  # T+1 解禁

res = pd.DataFrame(recs)
nav = res["nav"]
total_ret = nav.iloc[-1] / CASH - 1
max_dd = (1 - nav / nav.cummax()).max()
print(f"Return: {total_ret*100:+.2f}%  MaxDD: {max_dd*100:.2f}%")

# ── 图表 ──
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
dates = res["date"]
ax1.plot(range(len(dates)), nav / nav.iloc[0], color="#e74c3c", linewidth=1.2)
ax1.axhline(y=1, color="gray", linestyle="--", alpha=0.5)
ax1.set_title(f"{STOCK} MA{FAST}/{SLOW}  {START}-{END}  |  {total_ret*100:+.2f}%  MaxDD {max_dd*100:.2f}%")
ax2.fill_between(range(len(dates)), 0, (1 - nav / nav.cummax()) * 100, color="#27ae60", alpha=0.6)
step = max(1, len(dates) // 10)
ax2.set_xticks(range(0, len(dates), step))
ax2.set_xticklabels([dates[i] for i in range(0, len(dates), step)], rotation=45, fontsize=8)
plt.tight_layout()
plt.savefig(f"/workspace/backtest_{STOCK}_{START}_{END}.png", dpi=150, bbox_inches="tight")
plt.close()
```

---

## 常见陷阱速查

| 陷阱 | 现象 | 解决办法 |
|------|------|---------|
| 未来函数 | 收益远超实盘 | 信号 `shift(1)`，用开盘价撮合 |
| 单位混淆 | 收益差 100 倍 | daily vol 是手，1m vol 是股 |
| 忽略涨跌停 | 虚构涨停买入、跌停卖出 | 每笔交易前检查涨跌停 |
| 忽略 T+1 | 当日买卖套利 | `today_bought` 追踪，收盘解禁 |
| 忽略最低佣金 | 小额交易收益虚高 | `max(amount * rate, 5)` |
| 不复权跳空 | 分红日"暴跌" | 注意复权，标注数据来源 |
| 过拟合 | 样本外失效 | 参数 ±10% 收益波动 >20% 即过拟合 |
| 幸存者偏差 | 只看现存股票 | 使用回测起始日已上市股票 |
