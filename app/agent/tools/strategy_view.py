"""StrategyView 工具 — 查看策略列表与持仓明细。

系统级工具，与 Shell / ReadFile / Cronjob 平级。
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from app.agent.tools.base import Tool, ToolParam

logger = logging.getLogger(__name__)


def _json_safe(obj):
    """递归将 Decimal / datetime 转为 JSON 可序列化类型"""
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(i) for i in obj]
    return obj


class StrategyView(Tool):
    """查看策略列表与持仓明细"""

    name = "StrategyView"
    description = (
        "View my strategy list and position details. "
        "When strategy_id is omitted, returns a summary of all strategies "
        "(name, description, detail preview). "
        "When strategy_id is provided, returns full details including "
        "positions and cash status."
    )

    parameters = [
        ToolParam(
            "strategy_id", str,
            "Strategy ID. Omit to list all strategies; "
            "provide to get positions and detailed info.",
            default="", required=False,
        ),
    ]

    async def call(self, arguments: dict) -> dict:
        strategy_id = arguments.get("strategy_id", "")

        from app.services.cron_service import _current_user_id
        user_id = _current_user_id.get()
        if not user_id:
            return {"is_error": True, "message": "未登录，无法查看策略信息"}

        if not strategy_id:
            return self._action_list(user_id)
        else:
            return self._action_detail(user_id, strategy_id)

    # ── 内部方法 ─────────────────────────────────────

    def _get_accessible_ids(self, user_id: int) -> set[str] | None:
        from app.dependencies import repository
        from app.permissions.service import get_accessible_strategy_ids
        from app.auth.models import User

        session = repository.SessionLocal()
        try:
            row = session.query(User).filter_by(id=user_id).first()
            if row is None:
                return set()
            user = {"user_id": row.id, "sub": row.username, "role": row.role}
            return get_accessible_strategy_ids(session, user)
        finally:
            session.close()

    # ── 不传 strategy_id：列出所有策略摘要 ────────────

    def _action_list(self, user_id: int) -> dict:
        from app.dependencies import get_strategies

        strategies = get_strategies()
        accessible = self._get_accessible_ids(user_id)

        result = []
        for sid, s in strategies.items():
            if accessible is not None and sid not in accessible:
                continue

            result.append({
                "strategy_id": s.strategy_id,
                "name": s.name,
                "description": s.description,
                "detail": s.detail[:50] if s.detail else "",
            })

        return {
            "is_error": False,
            "output": json.dumps({
                "strategies": result,
                "count": len(result),
            }, ensure_ascii=False),
        }

    # ── 传入 strategy_id：持仓 + 资金 ────────────────

    def _action_detail(self, user_id: int, strategy_id: str) -> dict:
        from app.dependencies import get_strategies
        from app.store.analytics import get_stock_names

        accessible = self._get_accessible_ids(user_id)
        if accessible is not None and strategy_id not in accessible:
            return {"is_error": True, "message": f"策略 {strategy_id} 不存在"}

        strategies = get_strategies()
        s = strategies.get(strategy_id)
        if s is None:
            return {"is_error": True, "message": f"策略 {strategy_id} 不存在"}

        # 持仓明细
        positions = []
        for code, pos in s.positions.items():
            if pos.total > 0:
                positions.append({
                    "stock_code": code,
                    "total": pos.total,
                    "available": pos.available,
                    "frozen": pos.frozen,
                    "unavailable": pos.unavailable,
                    "avg_price": _json_safe(pos.avg_price),
                    "remark": pos.remark,
                })

        codes = [p["stock_code"] for p in positions]
        name_map = get_stock_names(codes) if codes else {}
        for p in positions:
            p["stock_name"] = name_map.get(p["stock_code"], "")

        # 总资产
        position_value = sum(
            pos.total * float(pos.avg_price)
            for pos in s.positions.values()
        )
        total_assets = float(s.total_cash) + position_value

        detail = {
            "strategy_id": s.strategy_id,
            "name": s.name,
            "description": s.description,
            "detail": s.detail,
            "trade_mode": s.trade_mode,
            "initial_cash": _json_safe(s.initial_cash),
            "available_cash": _json_safe(s.available_cash),
            "frozen_cash": _json_safe(s.frozen_cash),
            "total_assets": round(total_assets, 2),
            "positions": positions,
        }

        return {
            "is_error": False,
            "output": json.dumps(detail, ensure_ascii=False),
        }
