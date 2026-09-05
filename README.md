# Trade-system · A 股量化交易平台

基于 **FastAPI + Vue 3** 的 A 股量化交易平台：多策略虚拟账户管理、仿真/实盘双执行引擎（xtquant）、实时行情推送、内置 LLM 交易助手，前后端分离单体仓库。

本平台是「**量化投研闭环**」的**应用/交易层**：读取 [kbquant](https://github.com/Iamqlwy/kbquant) 沉淀的数据与 ES 知识，消费 [workflow](https://github.com/Iamqlwy/workflow) 产出的分析，完成可视化与交易决策。

> ⚠️ **免责声明**：本项目仅用于学习、研究和模拟交易。实盘交易有风险，请自行评估并谨慎使用，作者不对任何交易损失承担责任。

## ✨ 功能特性

- **多策略管理** — 每个策略一个虚拟账户：独立资金、持仓、委托、按 FIFO 批次计算已实现盈亏，互不干扰
- **双执行模式** — 仿真撮合（真实行情逐笔成交）+ xtquant 实盘下单，未安装 SDK 时优雅降级为纯仿真
- **实时行情** — xtquant 回调驱动的 tick 存储与 WebSocket 推送，1 分钟 K 线聚合
- **AI 交易助手** — LLM Agent：文件/网页检索、Docker 沙箱执行 Python、定时任务（Cron）、子代理、用户记忆，全链路工具调用与确认
- **风控与审计** — 下单确认机制、JSON 审计日志、请求关联 ID、健康监控
- **分析报表** — 每日结算、资产曲线、回撤/风险指标、对比分析、打板（T 板）统计等 7 大分析页
- **权限体系** — 管理员 / 策略成员 / API Token 三级权限，站内信与通知推送
- **自选股监控** — 行情告警 + 实时推送

## 🔗 系统定位：量化投研闭环（一体系统）

本仓库与 [kbquant](https://github.com/Iamqlwy/kbquant)、[workflow](https://github.com/Iamqlwy/workflow) 同属「**量化投研闭环**」，本仓库是终端交易层：

| 仓库 | 角色 | 关系 |
| --- | --- | --- |
| [kbquant](https://github.com/Iamqlwy/kbquant) | 知识库后端（数据/知识层） | 本仓库经 `KB_DB_*` / `ES_URL` 只读账号读取其 PG 与 ES |
| [workflow](https://github.com/Iamqlwy/workflow) | 多 Agent 分析流水线 | 产出 Analysis/Trading/Feedback 落库到 kbquant |
| Trade-system（本仓库） | A 股交易平台（应用/交易层） | 可视化与消费知识，驱动交易决策 |

```text
                        ┌──────────────────────────────────────────────┐
                        │          量化投研闭环（一体系统）              │
                        └──────────────────────────────────────────────┘

   资讯源                   数据/知识层                  AI 分析层               应用/交易层
 (新闻/研报/           ┌───────────────────┐ 写回    ┌──────────────────┐ 读取 ┌──────────────────┐
  社交媒体/CSV) ─────▶ │  kbquant          │ ◀───── │  workflow        │ ───▶ │  Trade-system    │
                      │  知识库后端        │ 消费队列│  多 Agent 流水线 │ DB/ES│  A股交易平台      │
                      │  PG(pgvector)+ES  │        │  重要性分级→深度  │      │  FastAPI+Vue3    │
                      │  +PgBouncer       │        │  分析→风控→复盘   │      │  虚拟账户/实盘    │
                      │  WorldNode/分析/  │        │  (SQLite 本地态)  │      │  知识图谱/检索    │
                      │  交易/复盘/混合搜索│        │                  │      │  LLM 交易助手    │
                      └───────────────────┘        └──────────────────┘      └──────────────────┘
                         ▲ 共享大脑/唯一事实源
                         │  (只读账号: kbquant_readonly / kbquant_es_readonly)
                                                                          ◄ 本仓库 = 应用/交易层
```

> **数据流**：资讯流入 → kbquant 入库 → workflow 分析 → 知识沉淀回 kbquant → 本仓库可视化/交易。
>
> **启动顺序**：kbquant → workflow → 本仓库（前两者未就绪时，本平台交易功能正常，知识库检索/图谱/经验视图不生效）。

## 🏗 系统架构

```
Vue 3 SPA (frontend/) → FastAPI (REST API + WebSocket) → StrategyManager → Executor (Sim/Real)
       ↓                                                          ↓
  ECharts/Element Plus                                     MarketData (xtquant callbacks)
                                                                   ↓
                                                             MySQL ← Repository (SQLAlchemy)
```

```
app/
├── agent/       # LLM 交易助手（会话、工具、子代理、定时任务、Docker 沙箱）
├── api/         # REST + WebSocket 接口
├── auth/        # JWT 认证与 bcrypt 密码哈希
├── engine/      # 虚拟账户、仿真/实盘执行器、手续费
├── market/      # 行情数据、tick 广播、K 线、交易时段
├── monitor/     # 自选股监控告警
├── permissions/ # 策略级权限（管理员/成员/只读）
├── services/    # Agent 事件、连接注册表、通知中心等
├── store/       # SQLAlchemy 持久化与启动恢复
└── watchlist/   # 自选股
```

## 🛠 技术栈

| 端 | 技术 |
|----|------|
| 后端 | Python 3.13 · FastAPI · SQLAlchemy 2.0 · MySQL · Pydantic v2 · xtquant SDK · python-jose + bcrypt |
| 前端 | Vue 3 · TypeScript · Vite · Element Plus · ECharts · Pinia · Vue Router · Axios |
| Agent | 通义千问（兼容 OpenAI Chat 协议，可换 Anthropic 模式）· Docker 沙箱 · 阿里云 OSS · PostgreSQL + ES 知识库 |

## 🚀 快速开始

### 1. 环境要求

- Python 3.13+
- Node.js 18+（前端）
- MySQL 8.x
- Docker（可选：Agent Shell 沙箱）
- xtquant 环境（实盘交易，可选）
- PostgreSQL + Elasticsearch（知识库，**核心集成**）：即 [kbquant](https://github.com/Iamqlwy/kbquant) 提供的数据/知识层，通过 `KB_DB_*` / `ES_URL` 只读接入；未配置时 AI 助手退化为纯 web 检索，知识图谱/检索/经验视图不可用

### 2. 后端

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量（复制模板并填写）
cp .env.example .env

# 初始化数据库结构（MySQL）
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS winwin DEFAULT CHARSET utf8mb4;"
mysql -u root -p winwin < sql/schema_backup.sql

# 启动开发服务器（http://localhost:8000，带热重载）
python main.py
```

### 3. 前端

```bash
cd frontend
npm install
npm run dev        # 开发模式 http://localhost:5173，/api 与 /ws 代理到 8000
npm run build      # 生产构建 → frontend/dist/，由后端直接托管
```

### 4. Docker 沙箱（Agent 代码执行）

```bash
docker build -t quant-sandbox:latest -f Dockerfile.sandbox .
```

## ⚙️ 环境变量

完整模板见 [`.env.example`](.env.example)，核心配置：

| 变量 | 说明 |
|------|------|
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | MySQL 连接 |
| `JWT_SECRET` | JWT 签名密钥（生产环境务必替换） |
| `XTACCOUNT` / `XTDATA_PATH` / `XTTRADER_PATH` | xtquant 实盘配置，留空则仅仿真模式 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | AI 助手模型配置 |
| `OSS_*` | 阿里云 OSS（图片上传，可不配置） |
| `KB_DB_*` / `ES_URL` / `EMBEDDING_*` | 知识库检索（指向 [kbquant](https://github.com/Iamqlwy/kbquant) 数据层，核心集成） |

## 🧠 知识库集成（闭环关键）

本平台通过 kbquant 的数据层接入闭环知识。`/api/knowledge` 系列路由（知识图谱、知识搜索、市场认知/经验视图）：
- 只读读取 kbquant 的 PostgreSQL 表 `raw_information` / `analyses` / `feedbacks` / `nodes`（经 `kbquant_readonly` 账号，PgBouncer 6432）
- 检索 kbquant 的 ES 索引 `quant_kb_*`（经 `kbquant_es_readonly`），支持向量检索 + RRF 融合（SiliconFlow embedding）
- AI 助手的 Researcher 支持 `source_type = "web" | "knowledge_base"` 双来源检索

对应前端页面：知识图谱（KnowledgeGraphView）、知识搜索（KnowledgeSearchView）、经验/市场认知（ExperienceView）。

## 📡 主要接口

| 路径 | 说明 |
|------|------|
| `GET /api/health` | 健康检查 |
| `POST /api/auth/register` · `POST /api/auth/login` | 注册 / 登录（返回 JWT） |
| `GET/POST /api/strategies` | 策略列表 / 创建 |
| `POST /api/strategies/{id}/orders` | 下单（需下单确认） |
| `GET /api/strategies/{id}/positions` | 持仓查询 |
| `GET /api/trades` | 成交记录 |
| `WS /ws/market` | 实时行情推送 |
| `WS /ws/agent` | AI 助手会话 |
| `POST /api/agent/...` | Agent 管理接口 |

## 🧪 测试

后端无正式测试框架，`tests/` 下为 pytest 兼容的接口与沙箱测试：

```bash
pytest tests/
```

## 📁 其他

- `sql/schema_backup.sql` — 数据库结构备份（含触发器）
- `scripts/` — 数据库迁移与维护脚本
- `docs/` — xtquant API 参考笔记
- `skills/` — Agent 技能（回测 / 行情数据 / 个股监控）

## 🔗 相关仓库

- [kbquant](https://github.com/Iamqlwy/kbquant) — 知识库后端（本平台的数据/知识层）
- [workflow](https://github.com/Iamqlwy/workflow) — AI 分析流水线（知识的产出方）

## 📄 License

MIT
