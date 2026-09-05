"""
量化交易系统 - FastAPI 应用入口

一站式 Web 平台：登录、策略管理、下单交易、实时监控、历史分析。
"""
import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .api.router import router as api_router
from .api.ws import ws_router
from .api.ws_agent import ws_agent_router
from .api.agent_api import agent_api_router
from .api.memory_api import memory_api_router
from .api.cron_api import cron_router
from .api.feedback_api import feedback_router
from .api.auth_api import router as auth_api_router
from .api.api_tokens_api import router as api_tokens_router
from .api.confirm_api import router as confirm_router
from .api.ws_notify import ws_notify_router
from .api.settings_api import router as settings_router
from .api.profile_api import router as profile_router
from .api.message_api import router as message_router
from .api.settings_groups_api import router as settings_groups_router
from .api.admin_api import router as admin_router
from .api.knowledge_router import router as knowledge_router
from .config import settings
from .logging_config import setup_logging
from .dependencies import (
    strategy_manager, market_data, repository,
    get_sim_executor, get_real_executor, get_monitor_engine, get_kline_1m,
)
from .store.loader import restore_strategies, restore_unfinished_orders
from .market.fetcher import run_tick_loop
from .logutils.correlation import generate_request_id, set_request_id, set_api_token_id
from .logutils.audit import log_system_event
from .logutils.health import health_monitor_loop
from .monitor.api import monitor_router, monitor_ws_router
from .watchlist.api import watchlist_router
from .auth.security import decode_token, is_api_token, is_agent_session_token, hash_api_token, resolve_api_token

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    setup_logging(settings.log_level)
    logger.info("量化交易系统 v2.0 启动中...")
    log_system_event("SYSTEM_START", detail="系统启动")

    # 0a. 注入 xtquant SDK（必须在 worker 进程内执行，reload=True 时父进程注入无效）
    try:
        import xtquant.xtdata as xtdata
        from .market.fetcher import init_xtdata
        init_xtdata(xtdata)
        logger.info("xtquant SDK 已加载")
    except ImportError:
        logger.warning("xtquant SDK 未安装，行情/实盘功能不可用")

    # 0b. 确保数据库表结构存在
    try:
        from .store.models import Base
        from .models.memory import UserProfile, UserMemory  # noqa: F401 — 注册到 Base.metadata
        Base.metadata.create_all(bind=repository.engine)
        logger.info("数据库表结构已初始化")
    except Exception:
        logger.exception("数据库表结构创建失败，将继续尝试启动")
        log_system_event("INIT", detail="数据库表结构创建失败", success=False)

    # 0c. 自动迁移：检测 users 表缺失列并补充（create_all 不会给已有表加列）
    try:
        from sqlalchemy import inspect, text
        from .auth.models import User as _UserModel
        insp = inspect(repository.engine)
        existing_cols = {c["name"] for c in insp.get_columns("users")}
        _col_name_re = re.compile(r"^[a-z_][a-z0-9_]*$")
        for col in _UserModel.__table__.columns:
            if col.name not in existing_cols:
                # 安全校验：列名必须匹配合法标识符模式，防止 SQL 注入
                if not _col_name_re.match(col.name):
                    logger.warning("数据库迁移跳过非法列名: %r", col.name)
                    continue
                col_type = col.type.compile(repository.engine.dialect)
                nullable = "NULL" if col.nullable else "NOT NULL"
                comment_sql = f" COMMENT '{col.comment}'" if col.comment else ""
                default_sql = ""
                if col.default and hasattr(col.default, "arg"):
                    default_sql = f" DEFAULT {col.default.arg!r}" if isinstance(col.default.arg, (int, float)) else ""
                sql = text(f"ALTER TABLE users ADD COLUMN {col.name} {col_type} {nullable}{default_sql}{comment_sql}")
                with repository.engine.connect() as conn:
                    conn.execute(sql)
                    conn.commit()
                logger.info("数据库迁移: users 新增列 %s (%s)", col.name, col_type)
    except Exception:
        logger.exception("数据库迁移失败（users 表），部分新功能可能不可用")

    # 0d. 通用迁移：为已有表补齐缺失列（api_tokens 等）
    try:
        from sqlalchemy import inspect as sa_inspect, text as sa_text
        from .auth.models import ApiToken as _ApiTokenModel
        _migration_models = [_ApiTokenModel]
        insp = sa_inspect(repository.engine)
        _col_name_re = re.compile(r"^[a-z_][a-z0-9_]*$")
        for model in _migration_models:
            table_name = model.__tablename__
            try:
                existing_cols = {c["name"] for c in insp.get_columns(table_name)}
            except Exception:
                continue  # 表不存在，create_all 会处理
            for col in model.__table__.columns:
                if col.name not in existing_cols:
                    if not _col_name_re.match(col.name):
                        logger.warning("数据库迁移跳过非法列名: %s.%s", table_name, col.name)
                        continue
                    col_type = col.type.compile(repository.engine.dialect)
                    nullable = "NULL" if col.nullable else "NOT NULL"
                    comment_sql = f" COMMENT '{col.comment}'" if col.comment else ""
                    default_sql = ""
                    if col.default and hasattr(col.default, "arg"):
                        default_sql = f" DEFAULT {col.default.arg!r}" if isinstance(col.default.arg, (int, float)) else ""
                    sql = sa_text(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type} {nullable}{default_sql}{comment_sql}")
                    with repository.engine.connect() as conn:
                        conn.execute(sql)
                        conn.commit()
                    logger.info("数据库迁移: %s 新增列 %s (%s)", table_name, col.name, col_type)
    except Exception:
        logger.exception("数据库迁移失败（通用），部分新功能可能不可用")

    # 1. 恢复策略状态
    try:
        loaded = restore_strategies(repository)
        strategy_manager.clear()
        strategy_manager.update(loaded)
        logger.info("策略恢复完成: %d 个策略", len(loaded))
    except Exception:
        logger.exception("策略恢复失败")
        log_system_event("RESTORE", detail="策略恢复失败", success=False)

    # 2. 恢复未完成订单
    sim_exec = get_sim_executor()
    real_exec = get_real_executor()

    # 2a. 初始化实盘交易桥接
    broker_bridge = None
    try:
        from .engine.broker_bridge import BrokerBridge
        broker_bridge = BrokerBridge(real_exec)
        ok = broker_bridge.start()
        if ok:
            logger.info("实盘交易桥接已启动")
        else:
            logger.warning("实盘交易桥接启动失败（SDK 未装或配置缺失），仅模拟可用")
    except Exception:
        logger.exception("实盘交易桥接初始化异常，仅模拟可用")

    try:
        sim_orders = restore_unfinished_orders(repository, strategy_manager, real_only=False)
        real_orders = restore_unfinished_orders(repository, strategy_manager, real_only=True)
        sim_exec.restore_orders(sim_orders)
        real_exec.restore_orders(real_orders)
        logger.info("订单恢复完成: 模拟=%d, 实盘=%d", len(sim_orders), len(real_orders))
    except Exception:
        logger.exception("订单恢复失败")
        log_system_event("RESTORE", detail="订单恢复失败", success=False)

    # 3. 后台任务
    sim_exec._running = True
    real_exec._running = True
    tasks = []
    tasks.append(asyncio.create_task(sim_exec._loop()))
    tasks.append(asyncio.create_task(real_exec._process_callbacks()))

    all_codes: set[str] = set()
    for s in strategy_manager.values():
        all_codes.update(s.positions.keys())
    tasks.append(asyncio.create_task(run_tick_loop(market_data, all_codes)))

    tasks.append(asyncio.create_task(_broadcast_loop()))
    tasks.append(asyncio.create_task(_store_loop(sim_exec, real_exec)))
    tasks.append(asyncio.create_task(_confirm_expiry_loop()))

    # 4. 健康监控
    tasks.append(asyncio.create_task(health_monitor_loop(
        interval=60.0,
        strategy_manager=strategy_manager,
        sim_executor=sim_exec,
        real_executor=real_exec,
        repository=repository,
        market_data=market_data,
    )))

    # 5. 监控引擎
    monitor_engine = get_monitor_engine()
    await monitor_engine.start()
    tasks.append(monitor_engine._task)

    # 5.5 实时 1m K 线聚合器
    kline_1m = get_kline_1m()
    await kline_1m.start()
    tasks.append(kline_1m._task)

    # 6. Agent 目录初始化 + 定时任务调度器
    from .agent.config import ensure_dirs as _ensure_agent_dirs
    _ensure_agent_dirs()

    from .agent.cron.scheduler import start_scheduler, stop_scheduler as _stop_cron
    cron_scheduler = await start_scheduler()
    if cron_scheduler._task:
        tasks.append(cron_scheduler._task)

    logger.info("系统启动完成，%d 个策略已加载", len(strategy_manager))
    log_system_event("SYSTEM_START", detail=f"启动完成，{len(strategy_manager)} 个策略已加载")
    yield

    # 关闭
    logger.info("系统关闭中...")
    await _stop_cron()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    sim_exec._running = False
    real_exec._running = False
    if broker_bridge is not None:
        broker_bridge.stop()
    try:
        await monitor_engine.stop()
    except Exception:
        logger.exception("监控引擎关闭失败")
    try:
        await kline_1m.stop()
    except Exception:
        logger.exception("K线聚合器关闭失败")
    try:
        repository.store(
            strategy_manager,
            sim_exec.orders_over + sim_exec.orders_running, sim_exec.trades_done,
            list(real_exec.orders_running.values()) + real_exec.orders_over, real_exec.trades_done,
        )
        log_system_event("SYSTEM_STOP", detail="最终持久化完成")
    except Exception:
        logger.exception("关闭时持久化失败")
        log_system_event("SYSTEM_STOP", detail="最终持久化失败", success=False)
    logger.info("系统已关闭")


async def _broadcast_loop() -> None:
    from .market.trading_hours import is_continuous_auction
    while True:
        try:
            if is_continuous_auction():
                await market_data.broadcast()
        except Exception:
            logger.exception("广播循环异常")
        await asyncio.sleep(0.5)


async def _store_loop(sim_exec, real_exec) -> None:
    from .market.trading_hours import is_continuous_auction
    while True:
        await asyncio.sleep(settings.store_interval)
        if not is_continuous_auction():
            continue
        try:
            repository.store(
                strategy_manager,
                sim_exec.orders_over + sim_exec.orders_running, sim_exec.trades_done,
                list(real_exec.orders_running.values()) + real_exec.orders_over, real_exec.trades_done,
            )
        except Exception:
            logger.exception("自动持久化失败")
            logger.critical("持久化失败，数据可能丢失！请检查数据库连接")
            log_system_event("PERSISTENCE", detail="自动持久化失败", success=False)


async def _confirm_expiry_loop() -> None:
    """定期清理过期的下单确认记录。"""
    from datetime import datetime, timezone
    from .auth.models import OrderConfirmation
    while True:
        await asyncio.sleep(30)
        try:
            session = repository.SessionLocal()
            try:
                now = datetime.now(timezone.utc)
                expired = session.query(OrderConfirmation).filter(
                    OrderConfirmation.status == "pending",
                    OrderConfirmation.expires_at < now,
                ).all()
                for conf in expired:
                    conf.status = "expired"
                    conf.decided_at = now
                if expired:
                    session.commit()
                    logger.info("过期确认记录清理: %d 条", len(expired))
            finally:
                session.close()
        except Exception:
            logger.exception("确认过期清理失败")


# ── API Token 限速（内存级令牌桶）──────────────────────
_token_buckets: dict[int, list[float]] = {}  # api_token_id → [请求时间戳]


def _check_token_rate_limit(token_id: int, limit: int) -> bool:
    """检查 API Token 是否超限。返回 True=通过, False=超限。"""
    import time
    now = time.time()
    timestamps = _token_buckets.get(token_id, [])
    timestamps = [t for t in timestamps if now - t < 60]  # 清理 1 分钟外的
    if len(timestamps) >= limit:
        return False
    timestamps.append(now)
    _token_buckets[token_id] = timestamps
    return True


def create_app() -> FastAPI:
    app = FastAPI(title="量化交易系统", version="2.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Token"],
        allow_credentials=True,
    )

    # 请求关联中间件：为每个请求生成 request_id
    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        request_id = generate_request_id()
        set_request_id(request_id)
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ── 全局认证中间件 ──
    # 所有请求必须先通过 JWT 验证，公开路径除外。
    # 认证失败返回 401，前端拦截后自动退出登录。
    # 代码在 correlation_middleware 之后注册 → LIFO 执行顺序：先关联ID，再认证。

    _PUBLIC_PATHS = {
        "/api/auth/login",
        "/api/auth/register",
        "/api/health",
    }

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path

        # 1. WebSocket 连接跳过（ws.py / ws_agent.py 内部自行鉴权）
        if path.startswith("/ws"):
            return await call_next(request)

        # 2. 公开路径白名单
        if path in _PUBLIC_PATHS:
            return await call_next(request)

        # 3. 提取 Token（Authorization header 或 ?token= 查询参数）
        auth_header = request.headers.get("Authorization", "")
        token: str | None = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            # X-API-Token header（API Token 专用）
            token = request.headers.get("X-API-Token")
            if not token:
                # fallback：从查询参数读取（用于 <img src="...?token=xxx"> 等场景）
                token = request.query_params.get("token")

        if not token:
            logger.warning("认证拦截: 缺少 token (path=%s)", path)
            return JSONResponse(status_code=401, content={"detail": "Missing token"})

        # 4. 判断 token 类型并验证
        if is_api_token(token):
            # ── API Token 路径 ──
            token_hash = hash_api_token(token)
            token_info = resolve_api_token(token_hash)
            if token_info is None:
                logger.warning("认证拦截: API Token 无效/已过期/已禁用 (path=%s)", path)
                return JSONResponse(status_code=401, content={"detail": "Invalid API token"})

            # 限速检查
            rate_limit = token_info.get("token_rate_limit", 0)
            if rate_limit > 0:
                if not _check_token_rate_limit(token_info["api_token_id"], rate_limit):
                    logger.warning(
                        "API Token 限速: token_id=%d user=%s (path=%s)",
                        token_info["api_token_id"], token_info["sub"], path,
                    )
                    return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

            request.state.user = token_info
            # 设置审计上下文的 api_token_id
            set_api_token_id(token_info["api_token_id"])
        elif is_agent_session_token(token):
            # ── Agent Session Token 路径 ──
            # ag_ 前缀 → agent session_id，查 AgentSessions 表反查 user_id
            from .services.agent_manager import agent_manager
            from .store.models import AgentSessions
            from .auth.models import User

            user_id = agent_manager._session_users.get(token)
            if not user_id:
                # 内存中无映射，尝试从 DB 恢复
                try:
                    db_session = repository.SessionLocal()
                    try:
                        row = db_session.query(AgentSessions.user_id).filter(
                            AgentSessions.id == token
                        ).first()
                        user_id = row[0] if row else None
                    finally:
                        db_session.close()
                except Exception:
                    user_id = None

                if user_id:
                    # 恢复到内存缓存
                    agent_manager._session_users[token] = user_id

            if not user_id:
                logger.warning("认证拦截: Agent Session Token 无效 (path=%s)", path)
                return JSONResponse(status_code=401, content={"detail": "Invalid agent session token"})

            # 查询用户信息构造 user payload
            try:
                db_session = repository.SessionLocal()
                try:
                    user = db_session.query(User).filter_by(id=user_id).first()
                    if user is None:
                        logger.warning("认证拦截: Agent Session 对应用户不存在 user_id=%d (path=%s)", user_id, path)
                        return JSONResponse(status_code=401, content={"detail": "Invalid agent session token"})
                    payload = {
                        "sub": user.username,
                        "user_id": user.id,
                        "role": user.role,
                    }
                finally:
                    db_session.close()
            except Exception:
                logger.exception("认证拦截: Agent Session 查询用户异常 (path=%s)", path)
                return JSONResponse(status_code=401, content={"detail": "Invalid agent session token"})

            request.state.user = payload
        else:
            # ── JWT 路径（原有逻辑）──
            payload = decode_token(token)
            if payload is None:
                logger.warning("认证拦截: token 无效或已过期 (path=%s)", path)
                return JSONResponse(status_code=401, content={"detail": "Invalid token"})
            request.state.user = payload

        return await call_next(request)

    # ── 安全响应头中间件 ──
    # 为所有响应添加安全头，防止常见 Web 攻击。
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # 移除 Server 头，避免暴露服务器信息
        if "server" in response.headers:
            del response.headers["server"]
        return response

    # ── 请求体大小限制中间件 ──
    # 拒绝超过 2MB 的请求体，防止内存耗尽攻击。
    _MAX_REQUEST_BODY_SIZE = 2 * 1024 * 1024  # 2 MB

    @app.middleware("http")
    async def request_size_limit_middleware(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > _MAX_REQUEST_BODY_SIZE:
                    logger.warning(
                        "请求体过大: content_length=%s path=%s",
                        content_length, request.url.path,
                    )
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "请求体过大，上限 2MB"},
                    )
            except ValueError:
                pass
        return await call_next(request)

    # Routers
    app.include_router(auth_api_router)  # /api/auth/... (JSON token, for SPA)
    app.include_router(api_tokens_router)  # /api/api-tokens (API Token 管理)
    app.include_router(confirm_router)     # /api/order-confirmations (下单确认)
    app.include_router(profile_router)   # /api/profile/... (个人中心)
    app.include_router(api_router)       # /api/... (JSON API)
    app.include_router(settings_router)  # /api/settings/... (Admin only)
    app.include_router(agent_api_router) # /api/agent/... (Agent API)
    app.include_router(memory_api_router) # /api/memory/... (记忆系统)
    app.include_router(monitor_router)   # /api/monitors (Monitor REST)
    app.include_router(watchlist_router) # /api/watchlist (自选股)
    app.include_router(ws_router)        # /ws/... (WebSocket)
    app.include_router(ws_notify_router) # /ws/notifications (通知推送)
    app.include_router(ws_agent_router)  # /ws/agent (Agent WebSocket)
    app.include_router(monitor_ws_router)  # /ws/monitor (Alert WebSocket)
    app.include_router(cron_router)       # /api/cron/... (Cron Jobs)
    app.include_router(feedback_router)   # /api/feedback (用户反馈)
    app.include_router(message_router)    # /api/messages/... (站内信)
    app.include_router(settings_groups_router)  # /api/settings/... (用户组管理)
    app.include_router(admin_router)      # /api/admin/... (Admin statistics)
    app.include_router(knowledge_router)  # /api/knowledge/... (知识图谱)

    return app


app = create_app()


