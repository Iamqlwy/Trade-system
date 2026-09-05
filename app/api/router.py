"""
量化交易系统 - API 路由

FastAPI APIRouter，提供策略、订单、持仓的全部 HTTP 端点。
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from .. import datatypes as dt
from ..constants import OrderType, OrderStatus, PriceType, SHARES_PER_LOT
from ..engine.strategy import Strategy
from ..models.requests import (
    OrderRequest, UpdateRemarkRequest,
    CreateStrategyRequest, UpdateStrategyRequest,
)
from ..models.responses import (
    HealthResponse, StrategySummary, PositionResponse,
    OrderResponse, PlaceOrderResponse, CancelOrderResponse,
    CreateStrategyResponse, DeleteStrategyResponse,
    TradeResponse, StrategyUserResponse, StrategyOverviewResponse,
)
from ..dependencies import (
    get_strategies, get_strategy, get_sim_executor, get_real_executor,
    repository, get_strategy_lock,
)
from ..store.analytics import get_stock_names
from ..auth.dependencies import require_api_token, get_user_permissions
from ..permissions import (
    require_strategy_access,
    require_strategy_trade,
    require_strategy_modify,
    get_accessible_strategy_ids,
)
from ..permissions.service import associate_creator
from ..config import settings
from ..engine.commission import get_calculator
from ..engine.real_executor import query_real_account_cash
from ..logutils.correlation import (
    generate_request_id, set_request_id, correlate_order, correlate_request,
)
from ..logutils.audit import log_order_placed, log_order_cancelled

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ── 系统 ────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health():
    strategies = get_strategies()
    return HealthResponse(
        status="ok",
        strategies=len(strategies),
    )


# ── 策略 ────────────────────────────────────

@router.get("/strategies", response_model=list[StrategySummary])
async def list_strategies(_user: dict = Depends(require_api_token)):
    strategies = get_strategies()
    # 按权限过滤：admin 看全部，普通用户只看可访问的
    accessible_ids = get_accessible_strategy_ids(_user)
    result = []
    for sid, s in strategies.items():
        if accessible_ids is not None and sid not in accessible_ids:
            continue
        result.append(StrategySummary(
            strategy_id=s.strategy_id,
            name=s.name,
            description=s.description,
            detail=s.detail,
            trade_mode=s.trade_mode,
            initial_cash=s.initial_cash,
            available_cash=s.available_cash,
            frozen_cash=s.frozen_cash,
            position_count=len(s.positions),
            order_count_today=len(s.orders),
            trade_count_today=len(s.trades),
        ))
    return result


@router.get("/strategies/{strategy_id}", response_model=StrategySummary)
async def get_strategy_info(strategy_id: str, _user: dict = Depends(require_strategy_access)):
    s = get_strategy(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略 {strategy_id} 不存在")
    return StrategySummary(
        strategy_id=s.strategy_id,
        name=s.name,
        description=s.description,
        detail=s.detail,
        trade_mode=s.trade_mode,
        initial_cash=s.initial_cash,
        available_cash=s.available_cash,
        frozen_cash=s.frozen_cash,
        position_count=len(s.positions),
        order_count_today=len(s.orders),
        trade_count_today=len(s.trades),
    )


@router.post("/strategies", response_model=CreateStrategyResponse)
async def create_strategy(req: CreateStrategyRequest, _user: dict = Depends(require_api_token)):
    """创建新策略"""
    # ── 权限检查 ──
    perms = get_user_permissions(_user)
    if req.trade_mode == 1 and not perms["can_create_real"]:
        raise HTTPException(403, "无创建实盘策略权限")
    if perms["max_strategies"] != -1:
        from ..auth.models import StrategyUser as _SU
        _sess = repository.SessionLocal()
        try:
            _cnt = _sess.query(_SU).filter_by(user_id=_user["user_id"]).count()
        finally:
            _sess.close()
        if _cnt >= perms["max_strategies"]:
            raise HTTPException(403, f"策略数量已达上限 ({perms['max_strategies']})")

    # 实盘模式：验证券商账户可用资金
    if req.trade_mode == 1:
        success, available_cash, error_msg = query_real_account_cash(
            settings.xtaccount, settings.xttrader_path
        )
        if not success:
            raise HTTPException(400, f"无法验证实盘资金: {error_msg}")
        if Decimal(str(available_cash)) < req.initial_cash:
            raise HTTPException(
                400,
                "实盘账户可用资金不足，请检查券商账户余额",
            )
        logger.info(
            "实盘资金验证通过: 可用=%.2f, 需要=%.2f",
            available_cash, req.initial_cash,
        )

    strategy_id = f"s{uuid.uuid4().hex[:8]}"
    strategies = get_strategies()

    if strategy_id in strategies:
        raise HTTPException(409, f"策略ID {strategy_id} 已存在，请重试")

    strategy = Strategy(
        strategy_id=strategy_id,
        name=req.name,
        description=req.description,
        detail=req.detail,
        trade_mode=req.trade_mode,
        initial_cash=req.initial_cash,
        available_cash=req.initial_cash,
        frozen_cash=Decimal("0"),
    )

    # 写入数据库（记录所有者）
    if not repository.add_strategy(strategy, owner_id=_user["user_id"]):
        raise HTTPException(500, "策略创建失败，数据库写入错误")

    # 加入内存
    strategies[strategy_id] = strategy

    # 关联创建者权限（can_trade=True）
    session = repository.SessionLocal()
    try:
        associate_creator(session, _user["user_id"], strategy_id)
        session.commit()
    except Exception:
        session.rollback()
        logger.warning("关联策略创建者失败: %s → user %s", strategy_id, _user["user_id"])
    finally:
        session.close()

    logger.info("创建策略: %s (%s) by user %s", strategy_id, req.name, _user["sub"])
    return CreateStrategyResponse(
        success=True,
        strategy_id=strategy_id,
        message="策略创建成功",
    )


@router.put("/strategies/{strategy_id}", response_model=StrategySummary)
async def update_strategy(
    strategy_id: str,
    req: UpdateStrategyRequest,
    _user: dict = Depends(require_strategy_modify),
):
    """更新策略名称和描述"""
    s = get_strategy(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略 {strategy_id} 不存在")

    if req.name is not None:
        s.name = req.name
    if req.description is not None:
        s.description = req.description
    if req.detail is not None:
        s.detail = req.detail

    logger.info("更新策略: %s", strategy_id)

    return StrategySummary(
        strategy_id=s.strategy_id,
        name=s.name,
        description=s.description,
        detail=s.detail,
        trade_mode=s.trade_mode,
        initial_cash=s.initial_cash,
        available_cash=s.available_cash,
        frozen_cash=s.frozen_cash,
        position_count=len(s.positions),
        order_count_today=len(s.orders),
        trade_count_today=len(s.trades),
    )


@router.delete("/strategies/{strategy_id}", response_model=DeleteStrategyResponse)
async def delete_strategy(strategy_id: str, _user: dict = Depends(require_strategy_modify)):
    """逻辑删除策略"""
    strategies = get_strategies()
    s = strategies.get(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略 {strategy_id} 不存在")

    # 检查是否有活跃持仓或订单
    if s.positions:
        raise HTTPException(400, "策略仍有持仓，无法删除")
    active_orders = [o for o in s.orders.values() if int(o.order_status) < 3]
    if active_orders:
        raise HTTPException(400, "策略仍有未完成订单，无法删除")

    # 逻辑删除
    if not repository.delete_strategy(strategy_id):
        raise HTTPException(500, "删除失败")

    # 从内存移除
    del strategies[strategy_id]

    logger.info("删除策略: %s (%s)", strategy_id, s.name)
    return DeleteStrategyResponse(
        success=True,
        strategy_id=strategy_id,
        message="策略已删除",
    )


# ── 订单 ────────────────────────────────────


async def _do_place_order(strategy_id: str, req: OrderRequest, user: dict) -> str:
    """
    下单核心逻辑（提取为独立函数，供 confirm_api approve 复用）。

    返回 order_id，失败抛出 HTTPException。
    """
    s = get_strategy(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略 {strategy_id} 不存在")

    if req.order_volume <= 0 or req.order_volume % SHARES_PER_LOT != 0:
        raise HTTPException(400, f"委托数量必须为{SHARES_PER_LOT}的整数倍，当前: {req.order_volume}")

    lock = get_strategy_lock(strategy_id)
    async with lock:
        calc = get_calculator(strategy_id)
        order_id = s.get_order_id()

        order_type = OrderType(req.order_type)
        price_type = PriceType(req.price_type)
        is_buy = order_type in (OrderType.STOCK_BUY, OrderType.CREDIT_BUY)
        estimated_amount = dt.round2(Decimal(req.order_volume) * req.price)
        commission = calc.calculate(estimated_amount, is_buy)

        order = dt.Order(
            order_id=order_id,
            strategy_id=strategy_id,
            stock_code=req.stock_code,
            order_type=order_type,
            price_type=price_type,
            price=req.price,
            order_volume=req.order_volume,
            commission=commission,
            order_status=OrderStatus.ORDER_UNREPORTED,
            order_remark=req.order_remark,
            created_at=datetime.now(),
        )

        if not s.order_stock_by_order(order):
            raise HTTPException(400, "资金不足或持仓不足")

        with correlate_order(order_id, strategy_id):
            try:
                if s.trade_mode == 1:
                    real_exec = get_real_executor()
                    await real_exec.enqueue_order(order)
                else:
                    sim_exec = get_sim_executor()
                    await sim_exec.enqueue_order(order)
            except Exception:
                unfilled = order.order_volume - order.traded_volume
                unfilled_comm = dt.round2(order.commission * Decimal(unfilled) / Decimal(order.order_volume)) \
                    if order.order_volume > 0 else Decimal("0")
                s.cancel_order(order, unfilled, unfilled_comm)
                if order.order_id in s.orders:
                    del s.orders[order.order_id]
                logger.exception("订单提交失败，资金已退回")
                raise HTTPException(500, "订单提交失败，资金已退回")

            logger.info(
                "下单: %s %s %s %s股 @%s",
                strategy_id, order_id, req.stock_code, req.order_volume, req.price,
            )
            log_order_placed(
                strategy_id=strategy_id,
                order_id=order_id,
                stock_code=req.stock_code,
                order_type=order_type.name,
                price_type=price_type.name,
                volume=req.order_volume,
                price=req.price,
                commission=commission,
                trade_mode="REAL" if s.trade_mode == 1 else "SIM",
            )

    return order_id


@router.post("/strategies/{strategy_id}/orders", response_model=PlaceOrderResponse)
async def place_order(strategy_id: str, req: OrderRequest, _user: dict = Depends(require_strategy_trade)):
    s = get_strategy(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略 {strategy_id} 不存在")

    # ── API Token 下单确认检查 ──
    if _user.get("api_token_id"):
        from ..auth.models import ApiToken, OrderConfirmation
        import uuid
        _sess = repository.SessionLocal()
        try:
            _tok = _sess.query(ApiToken).filter_by(id=_user["api_token_id"]).first()
            if _tok and _tok.require_confirm:
                # 创建确认记录
                conf_id = uuid.uuid4().hex
                conf = OrderConfirmation(
                    id=conf_id,
                    user_id=_user["user_id"],
                    api_token_id=_tok.id,
                    api_token_name=_tok.name or "",
                    strategy_id=strategy_id,
                    stock_code=req.stock_code,
                    order_type=req.order_type,
                    price_type=req.price_type,
                    price=req.price,
                    order_volume=req.order_volume,
                    order_remark=req.order_remark or "",
                    status="pending",
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
                )
                _sess.add(conf)
                _sess.commit()

                # WS 通知用户
                from ..services.notification_hub import notification_hub
                from ..store.analytics import get_stock_names
                name_map = get_stock_names([req.stock_code])
                await notification_hub.notify_user(_user["user_id"], {
                    "type": "order_confirm",
                    "data": {
                        "confirmation_id": conf_id,
                        "api_token_name": _tok.name or "",
                        "strategy_id": strategy_id,
                        "strategy_name": s.name,
                        "stock_code": req.stock_code,
                        "stock_name": name_map.get(req.stock_code, ""),
                        "order_type": req.order_type,
                        "price_type": req.price_type,
                        "price": str(req.price),
                        "order_volume": req.order_volume,
                        "order_remark": req.order_remark or "",
                        "expires_at": conf.expires_at.isoformat(),
                    },
                })

                logger.info(
                    "下单待确认: conf=%s token=%s strategy=%s %s %s股 @%s",
                    conf_id, _tok.name, strategy_id, req.stock_code,
                    req.order_volume, req.price,
                )

                return JSONResponse(
                    status_code=202,
                    content={
                        "success": True,
                        "confirmation_id": conf_id,
                        "message": "订单已提交，等待用户确认",
                        "status": "pending",
                    },
                )
        finally:
            _sess.close()

    # ── 常规下单（无需确认或 JWT 用户）──
    order_id = await _do_place_order(strategy_id, req, _user)
    s = get_strategy(strategy_id)
    return PlaceOrderResponse(
        success=True,
        order_id=order_id,
        message="订单已提交",
        available_cash=s.available_cash if s else Decimal("0"),
        frozen_cash=s.frozen_cash if s else Decimal("0"),
    )


@router.delete("/strategies/{strategy_id}/orders/{order_id}", response_model=CancelOrderResponse)
async def cancel_order(strategy_id: str, order_id: str, _user: dict = Depends(require_strategy_trade)):
    s = get_strategy(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略 {strategy_id} 不存在")

    # 策略级锁：防止并发撤单竞态
    lock = get_strategy_lock(strategy_id)
    async with lock:
        order = s.get_order(order_id)
        if order is None:
            raise HTTPException(404, f"订单 {order_id} 不存在")

        if order.order_status in (OrderStatus.ORDER_SUCCEEDED, OrderStatus.ORDER_CANCELED,
                                   OrderStatus.ORDER_PART_CANCEL, OrderStatus.ORDER_JUNK,
                                   OrderStatus.ORDER_PARTSUCC_CANCEL, OrderStatus.ORDER_WAIT_REPORTING):
            raise HTTPException(400, f"订单 {order_id} 已终态或处理中，无法撤单")

        unfilled = order.order_volume - order.traded_volume
        unfilled_comm = dt.round2(order.commission * Decimal(unfilled) / Decimal(order.order_volume)) \
            if order.order_volume > 0 else Decimal("0")

        # 关联订单 ID（后续日志自动携带）
        with correlate_order(order_id, strategy_id):
            # 更新订单状态
            if order.traded_volume > 0:
                order.order_status = OrderStatus.ORDER_PART_CANCEL
            else:
                order.order_status = OrderStatus.ORDER_CANCELED
            order.status_msg = "已撤单"

            # 解冻
            s.cancel_order(order, unfilled, unfilled_comm)

            # 通知执行器
            if s.trade_mode == 1:
                await get_real_executor().cancel_order(order_id)
            else:
                await get_sim_executor().cancel_order(order_id)

            logger.info("撤单: %s %s, 未成交=%d股", strategy_id, order_id, unfilled)
            log_order_cancelled(
                strategy_id=strategy_id,
                order_id=order_id,
                stock_code=order.stock_code,
                unfilled_volume=unfilled,
            )

    return CancelOrderResponse(
        success=True,
        order_id=order_id,
        unfilled_volume=unfilled,
        message="已撤单",
    )


@router.get("/strategies/{strategy_id}/orders", response_model=list[OrderResponse])
async def list_orders(strategy_id: str, status: int | None = None, _user: dict = Depends(require_strategy_access)):
    s = get_strategy(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略 {strategy_id} 不存在")

    orders = list(s.orders.values())
    if status is not None:
        orders = [o for o in orders if int(o.order_status) == status]

    orders.sort(key=lambda o: o.created_at, reverse=True)

    # 批量获取股票名称
    codes = list({o.stock_code for o in orders})
    name_map = get_stock_names(codes)

    return [
        OrderResponse(
            order_id=o.order_id,
            strategy_id=strategy_id,
            stock_code=o.stock_code,
            stock_name=name_map.get(o.stock_code, ""),
            order_type=int(o.order_type),
            price_type=int(o.price_type),
            price=o.price,
            order_volume=o.order_volume,
            traded_volume=o.traded_volume,
            traded_price=o.traded_price,
            commission=o.commission,
            status=int(o.order_status),
            status_msg=o.status_msg,
            created_at=o.created_at,
            order_remark=o.order_remark,
        )
        for o in orders
    ]


# ── 持仓 ────────────────────────────────────

@router.get("/strategies/{strategy_id}/positions", response_model=list[PositionResponse])
async def list_positions(strategy_id: str, _user: dict = Depends(require_strategy_access)):
    s = get_strategy(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略 {strategy_id} 不存在")

    # 收集有持仓的代码，批量获取名称
    active_codes = [code for code, pos in s.positions.items() if pos.total > 0]
    name_map = get_stock_names(active_codes)

    result = []
    for code in active_codes:
        pos = s.positions[code]
        result.append(PositionResponse(
            stock_code=code,
            stock_name=name_map.get(code, ""),
            total=pos.total,
            available=pos.available,
            frozen=pos.frozen,
            unavailable=pos.unavailable,
            avg_price=pos.avg_price,
            remark=pos.remark,
        ))
    return result


@router.put("/strategies/{strategy_id}/positions/{stock_code}/remark")
async def update_position_remark(strategy_id: str, stock_code: str, req: UpdateRemarkRequest, _user: dict = Depends(require_strategy_access)):
    s = get_strategy(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略 {strategy_id} 不存在")

    if not s.update_position_remark(stock_code, req.remark):
        raise HTTPException(404, f"持仓 {stock_code} 不存在")

    return {"success": True, "message": "备注已更新"}


# ── 策略关联用户 ────────────────────────────────────

@router.get("/strategies/{strategy_id}/users", response_model=list[StrategyUserResponse])
async def list_strategy_users(strategy_id: str, _user: dict = Depends(require_strategy_access)):
    """查看策略关联的用户列表（含权限信息）"""
    s = get_strategy(strategy_id)
    if s is None:
        raise HTTPException(404, f"策略 {strategy_id} 不存在")

    from ..auth.models import User, StrategyUser
    from ..store.models import Strategys

    session = repository.SessionLocal()
    try:
        # 查策略所有者
        strategy_row = session.query(Strategys).filter_by(
            strategy_id=strategy_id, is_deleted=0,
        ).first()
        owner_id = strategy_row.owner_id if strategy_row else None

        # 查 strategy_users 关联
        rows = session.query(StrategyUser, User.username, User.role).join(
            User, StrategyUser.user_id == User.id,
        ).filter(StrategyUser.strategy_id == strategy_id).all()

        result = []
        seen_user_ids = set()
        for su, username, role in rows:
            result.append(StrategyUserResponse(
                user_id=su.user_id,
                username=username,
                role=role,
                can_trade=su.can_trade,
                is_owner=(su.user_id == owner_id),
            ))
            seen_user_ids.add(su.user_id)

        # 补充所有者（如果不在 strategy_users 中）
        if owner_id and owner_id not in seen_user_ids:
            owner_row = session.query(User).filter_by(id=owner_id).first()
            if owner_row:
                result.append(StrategyUserResponse(
                    user_id=owner_id,
                    username=owner_row.username,
                    role=owner_row.role,
                    can_trade=True,
                    is_owner=True,
                ))

        return result
    finally:
        session.close()


# ── 综合概览（策略+用户+持仓）────────────────────────

@router.get("/overview/strategies", response_model=list[StrategyOverviewResponse])
async def strategies_overview(_user: dict = Depends(require_api_token)):
    """
    综合概览：每个策略的基本信息、关联用户和当前持仓。
    按权限过滤：admin 看全部，普通用户只看可访问的策略。
    """
    from ..auth.models import User, StrategyUser
    from ..store.models import Strategys

    strategies = get_strategies()
    accessible_ids = get_accessible_strategy_ids(_user)

    session = repository.SessionLocal()
    try:
        # 批量查询所有策略的所有者
        strategy_owners: dict[str, int] = {}
        rows = session.query(Strategys.strategy_id, Strategys.owner_id).filter(
            Strategys.is_deleted == 0,
        ).all()
        for sid, oid in rows:
            if oid is not None:
                strategy_owners[sid] = oid

        # 批量查询所有策略的用户关联
        all_user_ids = set()
        su_rows = session.query(StrategyUser).all()
        su_by_strategy: dict[str, list] = {}
        for su in su_rows:
            su_by_strategy.setdefault(su.strategy_id, []).append(su)
            all_user_ids.add(su.user_id)

        # 批量查询用户名
        user_map: dict[int, tuple[str, str]] = {}  # user_id -> (username, role)
        if all_user_ids or set(strategy_owners.values()):
            user_rows = session.query(User.id, User.username, User.role).filter(
                User.id.in_(all_user_ids | set(strategy_owners.values()))
            ).all()
            for u in user_rows:
                user_map[u.id] = (u.username, u.role)

        result = []
        for sid, s in strategies.items():
            if accessible_ids is not None and sid not in accessible_ids:
                continue

            # 用户列表
            users = []
            seen = set()
            owner_id = strategy_owners.get(sid)
            for su in su_by_strategy.get(sid, []):
                uname, urole = user_map.get(su.user_id, ("", ""))
                users.append(StrategyUserResponse(
                    user_id=su.user_id,
                    username=uname,
                    role=urole,
                    can_trade=su.can_trade,
                    is_owner=(su.user_id == owner_id),
                ))
                seen.add(su.user_id)
            if owner_id and owner_id not in seen:
                uname, urole = user_map.get(owner_id, ("", ""))
                users.append(StrategyUserResponse(
                    user_id=owner_id, username=uname, role=urole,
                    can_trade=True, is_owner=True,
                ))

            # 持仓列表
            active_codes = [code for code, pos in s.positions.items() if pos.total > 0]
            name_map = get_stock_names(active_codes)
            positions = [
                PositionResponse(
                    stock_code=code,
                    stock_name=name_map.get(code, ""),
                    total=s.positions[code].total,
                    available=s.positions[code].available,
                    frozen=s.positions[code].frozen,
                    unavailable=s.positions[code].unavailable,
                    avg_price=s.positions[code].avg_price,
                    remark=s.positions[code].remark,
                )
                for code in active_codes
            ]

            # 计算总资产
            position_value = sum(
                pos.total * pos.avg_price for pos in s.positions.values()
            )
            total_assets = s.total_cash + position_value

            result.append(StrategyOverviewResponse(
                strategy_id=s.strategy_id,
                name=s.name,
                description=s.description,
                trade_mode=s.trade_mode,
                initial_cash=s.initial_cash,
                available_cash=s.available_cash,
                frozen_cash=s.frozen_cash,
                total_assets=total_assets,
                users=users,
                positions=positions,
            ))

        return result
    finally:
        session.close()


# ── 成交记录 ────────────────────────────────────

@router.get("/trades", response_model=list[TradeResponse])
async def list_trades(strategy_id: str | None = None, _user: dict = Depends(require_api_token)):
    """查询成交记录（可按策略筛选，按权限过滤）"""
    all_trades = []

    strategies = get_strategies()

    # 按权限过滤可见策略
    accessible_ids = get_accessible_strategy_ids(_user)

    if strategy_id:
        # 指定策略时，先验证权限
        if accessible_ids is not None and strategy_id not in accessible_ids:
            raise HTTPException(403, f"无权访问策略 {strategy_id}")
        target_ids = [strategy_id]
    else:
        if accessible_ids is not None:
            target_ids = [sid for sid in strategies.keys() if sid in accessible_ids]
        else:
            target_ids = list(strategies.keys())

    for sid in target_ids:
        s = strategies.get(sid)
        if s is None:
            continue
        all_trades.extend(s.trades)

    # 按时间倒序
    all_trades.sort(key=lambda t: t.traded_time, reverse=True)

    # 批量获取股票名称
    codes = list({t.stock_code for t in all_trades})
    name_map = get_stock_names(codes)

    return [
        TradeResponse(
            traded_id=t.traded_id,
            strategy_id=t.strategy_id,
            order_id=t.order_id,
            stock_code=t.stock_code,
            stock_name=name_map.get(t.stock_code, ""),
            order_type=int(t.order_type),
            traded_price=t.traded_price,
            traded_volume=t.traded_volume,
            traded_amount=t.traded_amount,
            traded_time=t.traded_time,
            order_remark=t.order_remark,
        )
        for t in all_trades
    ]
