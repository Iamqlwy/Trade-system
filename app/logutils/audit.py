"""
量化交易系统 - 审计日志助手

记录所有金融操作的结构化日志，输出到独立的 audit.log 文件。
用于合规审计、交易回溯和 bug 定位。

审计事件类型：
  - ORDER_PLACED:   下单
  - ORDER_CANCELLED: 撤单
  - TRADE_EXECUTED:  成交
  - AUTH_EVENT:      认证（登录/注册/失败）
  - SYSTEM_EVENT:    系统事件（启动/关闭/持久化）
"""

import logging
from datetime import datetime

from .correlation import get_request_id, get_order_id, get_strategy_id, get_api_token_id


def _get_audit_logger() -> logging.Logger:
    """获取审计日志器（在 logging_config.py 中配置）"""
    return logging.getLogger("audit")


def _log_event(event_type: str, **fields) -> None:
    """写一条审计日志"""
    logger = _get_audit_logger()
    extra_data = {
        "event": event_type,
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "request_id": get_request_id() or "",
        "order_id": get_order_id() or "",
        "strategy_id": get_strategy_id() or "",
        "api_token_id": get_api_token_id(),
    }
    extra_data.update(fields)
    logger.info(event_type, extra={"extra_data": extra_data})


# ── 金融操作审计 ─────────────────────────────────

def log_order_placed(
    strategy_id: str,
    order_id: str,
    stock_code: str,
    order_type: str,
    price_type: str,
    volume: int,
    price,
    commission,
    trade_mode: str,
) -> None:
    """记录下单审计事件"""
    _log_event(
        "ORDER_PLACED",
        strategy_id=strategy_id,
        order_id=order_id,
        stock_code=stock_code,
        order_type=order_type,
        price_type=price_type,
        volume=volume,
        price=str(price),
        commission=str(commission),
        trade_mode=trade_mode,
    )


def log_order_cancelled(
    strategy_id: str,
    order_id: str,
    stock_code: str,
    unfilled_volume: int,
    reason: str = "用户主动撤单",
) -> None:
    """记录撤单审计事件"""
    _log_event(
        "ORDER_CANCELLED",
        strategy_id=strategy_id,
        order_id=order_id,
        stock_code=stock_code,
        unfilled_volume=unfilled_volume,
        reason=reason,
    )


def log_trade_executed(
    trade_id: str,
    order_id: str,
    strategy_id: str,
    stock_code: str,
    order_type: str,
    volume: int,
    price,
    amount,
    trade_mode: str = "SIM",
) -> None:
    """记录成交审计事件"""
    _log_event(
        "TRADE_EXECUTED",
        trade_id=trade_id,
        order_id=order_id,
        strategy_id=strategy_id,
        stock_code=stock_code,
        order_type=order_type,
        volume=volume,
        price=str(price),
        amount=str(amount),
        trade_mode=trade_mode,
    )


# ── 认证审计 ─────────────────────────────────────

def log_order_rejected(
    confirmation_id: str,
    strategy_id: str,
    stock_code: str,
    order_type: str,
    price,
    volume: int,
    reject_reason: str,
    api_token_name: str = "",
) -> None:
    """记录下单被拒绝审计事件"""
    _log_event(
        "ORDER_REJECTED",
        confirmation_id=confirmation_id,
        strategy_id=strategy_id,
        stock_code=stock_code,
        order_type=order_type,
        price=str(price),
        volume=volume,
        reject_reason=reject_reason,
        api_token_name=api_token_name,
    )


def log_auth_event(
    username: str,
    action: str,
    success: bool,
    detail: str = "",
) -> None:
    """
    记录认证审计事件。

    action: "LOGIN" | "LOGOUT" | "REGISTER" | "LOGIN_FAILED" | "TOKEN_INVALID"
    """
    _log_event(
        "AUTH_EVENT",
        username=username,
        action=action,
        success=success,
        detail=detail,
    )


# ── 系统事件审计 ─────────────────────────────────

def log_system_event(
    action: str,
    detail: str = "",
    success: bool = True,
) -> None:
    """
    记录系统事件。

    action: "SYSTEM_START" | "SYSTEM_STOP" | "PERSISTENCE" | "RESTORE"
    """
    _log_event(
        "SYSTEM_EVENT",
        action=action,
        detail=detail,
        success=success,
    )
