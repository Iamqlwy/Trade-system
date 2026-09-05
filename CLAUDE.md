# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A quantitative trading platform for Chinese A-share markets with multi-strategy management, dual execution modes (simulated + real via xtquant SDK), real-time tick data streaming, and AI agent integration. Backend built with FastAPI, SQLAlchemy, MySQL. Frontend is a Vue 3 SPA with Element Plus, ECharts, Pinia, and TypeScript (monorepo in `frontend/`).

## Commands

### Running the Application
```bash
# Backend: Start the development server (uvicorn with hot reload)
python main.py
# Server starts on http://localhost:8000

# Frontend: Development mode (with hot reload, proxies /api and /ws to backend)
cd frontend && npm run dev
# Frontend dev server on http://localhost:5173

# Frontend: Production build
cd frontend && npm run build
# Output to frontend/dist/ — automatically served by backend at /
```

### Database & Test Data
```bash
# Seed test data into MySQL (requires running MySQL instance)
python scripts/seed_and_test.py
```

### No Formal Test/Lint Setup (Backend)
There is no test framework, linter, or formatter configured for the Python backend. No `pyproject.toml`, `setup.cfg`, or CI/CD pipeline exists. The frontend has ESLint + Prettier configured via `npm run lint` / `npm run format`.

## Architecture

### Core Request Flow
```
Vue 3 SPA (frontend/) → FastAPI (REST API + WebSocket) → StrategyManager → Executor (Sim/Real)
       ↓                                                          ↓
  ECharts/Element Plus                                     MarketData (xtquant callbacks)
                                                                   ↓
                                                             MySQL ← Repository (SQLAlchemy)
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `app/engine/strategy.py` | Virtual account per strategy — cash, positions, FIFO lots, settlements, order lifecycle |
| `app/engine/sim_executor.py` | Simulated order matching using real-time ticks |
| `app/engine/real_executor.py` | Live trading via xtquant SDK |
| `app/market/data.py` | Thread-safe tick storage + WebSocket broadcast (lock required: xtquant callbacks are non-asyncio) |
| `app/market/fetcher.py` | xtquant integration for market data pulls |
| `app/store/repository.py` | SQLAlchemy persistence for all strategy state |
| `app/store/loader.py` | Startup restoration of strategies/positions/orders from DB |
| `app/api/router.py` | REST endpoints for strategies, orders, positions |
| `app/api/auth_api.py` | JSON auth endpoints for SPA (login/register/me with JWT token response) |
| `app/api/ws.py` | WebSocket endpoint for live tick streaming |
| `app/web/` | Legacy server-rendered Jinja2 pages (kept for backward compatibility) |
| `app/auth/` | JWT auth with bcrypt password hashing |
| `app/agent/` | LLM-powered trading assistant with file/web tools |
| `app/logutils/` | Request correlation IDs, audit logging (JSON to `logs/audit.log`), health monitoring |
| `app/dependencies.py` | Singleton factory with thread-safe double-checked locking for global state |

### Frontend (frontend/)

| Directory | Purpose |
|-----------|---------|
| `frontend/src/api/` | Axios service layer with typed API calls + Bearer token interceptor |
| `frontend/src/stores/` | Pinia stores: auth, strategies, market (real-time ticks) |
| `frontend/src/composables/` | Vue composables: useWebSocket, useTickStream, useAgentChat, useCsvExport |
| `frontend/src/router/` | Vue Router with auth guards (requiresAuth, requiresAdmin, guest) |
| `frontend/src/components/` | Reusable components: layout (sidebar/header), common (charts/cards/badges), strategy (order form/tables), agent (chat/tool cards) |
| `frontend/src/views/` | Page components: Dashboard, Strategies, Orders, Trades, Agent, Settings, + 7 analysis pages |
| `frontend/src/types/` | TypeScript interfaces matching backend Pydantic models |

### Architecture Patterns

- **Virtual Account Pattern** — Each `Strategy` is an isolated account with its own cash, positions, orders, and settlement history. Multiple strategies run concurrently without interference.
- **FIFO Cost Basis** — Heap-based lot tracking per position for tax-compliant realized P&L calculation.
- **Event-Driven** — Background async tasks handle order matching loops, callback processing, tick broadcasting, and periodic DB persistence.
- **Singleton State** — `MarketData`, `StrategyManager`, and executors are global singletons initialized via `dependencies.py`.
- **Decimal Precision** — All monetary values use `Decimal` with `ROUND_HALF_UP` to 2 decimal places.
- **SPA + API Separation** — Frontend communicates via REST API (Bearer JWT) and WebSocket (token query param). Backend serves SPA static files in production (catch-all route to `index.html`). Legacy Jinja2 routes remain for backward compatibility.
- **Composable Pattern** — Vue composables encapsulate WebSocket connections, CSV export, and agent chat logic for reuse across views.

### Database Schema (MySQL)

Key tables: `strategys`, `positions`, `lots`, `orders`, `trades`, `settlements`, `daily_account_snapshot`, `day_t_records`, `commission_configs`, `users`, `strategy_users`.

### Configuration

- `.env` — Database credentials, API keys, LLM config (loaded by Pydantic Settings in `app/config.py`)
- `app/constants.py` — xtquant protocol enums (OrderType 23=buy, 24=sell — do not modify these values)

### Graceful Degradation

System runs in simulation-only mode when xtquant SDK is not installed; real trading features log warnings and no-op.

## Tech Stack

### Backend
- **Python 3.13+**, **FastAPI**, **Uvicorn** (ASGI with hot reload)
- **SQLAlchemy 2.0+** with **PyMySQL** driver
- **Pydantic v2** for settings and request/response models
- **xtquant SDK** for real market data and order execution
- **python-jose** + **bcrypt** for JWT auth
- **Jinja2** (legacy, kept for backward compatibility)
- **Plotly** (legacy, analysis API still uses it; frontend now uses ECharts)

### Frontend
- **Vue 3** with Composition API + **TypeScript**
- **Element Plus** UI component library (Chinese locale)
- **ECharts** for data visualization (replacing Plotly)
- **Pinia** for state management
- **Vue Router** with auth guards
- **Axios** for HTTP (Bearer token interceptor, 401 auto-logout)
- **Vite** for build tooling (dev proxy to backend at port 8000)
- Monorepo structure: `frontend/` directory, built output at `frontend/dist/`
- A-share color convention: red (#e74c3c) = up/profit, green (#27ae60) = down/loss
