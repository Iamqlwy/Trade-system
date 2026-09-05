"""自选股 API

REST: /api/watchlist — 分组 CRUD、股票增删
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth.dependencies import require_api_token

logger = logging.getLogger(__name__)

watchlist_router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


# ── Request / Response 模型 ─────────────────────

class CreateGroupRequest(BaseModel):
    name: str


class RenameGroupRequest(BaseModel):
    name: str


class AddStockRequest(BaseModel):
    ts_code: str
    symbol: str
    name: str


class BatchAddStocksRequest(BaseModel):
    stocks: list[AddStockRequest]


# ── 分组 CRUD ──────────────────────────────────

@watchlist_router.get("/groups")
async def list_groups(token: dict = Depends(require_api_token)):
    """获取当前用户所有自选股分组（含股票列表）"""
    from ..dependencies import repository
    from ..store.models import WatchlistGroup

    session = repository.SessionLocal()
    try:
        groups = (
            session.query(WatchlistGroup)
            .filter(WatchlistGroup.user_id == token["user_id"])
            .order_by(WatchlistGroup.sort_order, WatchlistGroup.created_at)
            .all()
        )
        return [
            {
                "id": g.id,
                "user_id": g.user_id,
                "name": g.name,
                "sort_order": g.sort_order,
                "created_at": g.created_at.isoformat() if g.created_at else None,
                "updated_at": g.updated_at.isoformat() if g.updated_at else None,
                "stocks": [
                    {
                        "id": s.id,
                        "ts_code": s.ts_code,
                        "symbol": s.symbol,
                        "name": s.name,
                        "added_at": s.added_at.isoformat() if s.added_at else None,
                    }
                    for s in g.stocks
                ],
            }
            for g in groups
        ]
    finally:
        session.close()


@watchlist_router.post("/groups")
async def create_group(
    req: CreateGroupRequest,
    token: dict = Depends(require_api_token),
):
    """创建自选股分组"""
    from ..dependencies import repository
    from ..store.models import WatchlistGroup

    session = repository.SessionLocal()
    try:
        group = WatchlistGroup(
            user_id=token["user_id"],
            name=req.name.strip(),
        )
        session.add(group)
        session.commit()
        session.refresh(group)
        return {
            "id": group.id,
            "user_id": group.user_id,
            "name": group.name,
            "sort_order": group.sort_order,
            "created_at": group.created_at.isoformat() if group.created_at else None,
            "updated_at": group.updated_at.isoformat() if group.updated_at else None,
            "stocks": [],
        }
    except Exception as e:
        session.rollback()
        logger.error("创建自选分组失败: %s", e)
        raise HTTPException(status_code=500, detail=f"创建分组失败: {e}")
    finally:
        session.close()


@watchlist_router.put("/groups/{group_id}")
async def rename_group(
    group_id: int,
    req: RenameGroupRequest,
    token: dict = Depends(require_api_token),
):
    """重命名自选股分组"""
    from ..dependencies import repository
    from ..store.models import WatchlistGroup

    session = repository.SessionLocal()
    try:
        group = session.query(WatchlistGroup).filter_by(id=group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
        if group.user_id != token["user_id"]:
            raise HTTPException(status_code=403, detail="无权操作此分组")

        group.name = req.name.strip()
        group.updated_at = datetime.now()
        session.commit()
        return {"id": group.id, "name": group.name, "updated": True}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error("重命名自选分组失败: %s", e)
        raise HTTPException(status_code=500, detail=f"重命名失败: {e}")
    finally:
        session.close()


@watchlist_router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    token: dict = Depends(require_api_token),
):
    """删除自选股分组（级联删除股票）"""
    from ..dependencies import repository
    from ..store.models import WatchlistGroup

    session = repository.SessionLocal()
    try:
        group = session.query(WatchlistGroup).filter_by(id=group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
        if group.user_id != token["user_id"]:
            raise HTTPException(status_code=403, detail="无权操作此分组")

        session.delete(group)
        session.commit()
        return {"id": group_id, "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error("删除自选分组失败: %s", e)
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
    finally:
        session.close()


# ── 股票管理 ──────────────────────────────────

def _validate_stock(ts_code: str) -> dict | None:
    """校验 ts_code 是否为合法上市股票，返回股票信息或 None。"""
    from ..monitor.engine import get_stock_info
    return get_stock_info(ts_code)


@watchlist_router.post("/groups/{group_id}/stocks")
async def add_stock(
    group_id: int,
    req: AddStockRequest,
    token: dict = Depends(require_api_token),
):
    """添加股票到自选分组"""
    from ..dependencies import repository
    from ..store.models import WatchlistGroup, WatchlistStock

    # 校验股票代码合法性
    stock_info = _validate_stock(req.ts_code)
    if stock_info is None:
        raise HTTPException(status_code=400, detail=f"股票代码 {req.ts_code} 不存在或不合法")

    session = repository.SessionLocal()
    try:
        group = session.query(WatchlistGroup).filter_by(id=group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
        if group.user_id != token["user_id"]:
            raise HTTPException(status_code=403, detail="无权操作此分组")

        # 检查是否已存在
        existing = (
            session.query(WatchlistStock)
            .filter_by(group_id=group_id, ts_code=req.ts_code)
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="该股票已在自选列表中")

        stock = WatchlistStock(
            group_id=group_id,
            ts_code=stock_info["ts_code"],
            symbol=stock_info["symbol"],
            name=stock_info["name"],
        )
        session.add(stock)
        session.commit()
        session.refresh(stock)
        return {
            "id": stock.id,
            "ts_code": stock.ts_code,
            "symbol": stock.symbol,
            "name": stock.name,
            "added_at": stock.added_at.isoformat() if stock.added_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error("添加自选股票失败: %s", e)
        raise HTTPException(status_code=500, detail=f"添加失败: {e}")
    finally:
        session.close()


@watchlist_router.post("/groups/{group_id}/stocks/batch")
async def batch_add_stocks(
    group_id: int,
    req: BatchAddStocksRequest,
    token: dict = Depends(require_api_token),
):
    """批量添加股票到自选分组（跳过已存在和不合法的）"""
    from ..dependencies import repository
    from ..store.models import WatchlistGroup, WatchlistStock

    session = repository.SessionLocal()
    try:
        group = session.query(WatchlistGroup).filter_by(id=group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="分组不存在")
        if group.user_id != token["user_id"]:
            raise HTTPException(status_code=403, detail="无权操作此分组")

        # 获取已存在的 ts_code 集合
        existing_codes = set(
            s.ts_code
            for s in session.query(WatchlistStock.ts_code)
            .filter_by(group_id=group_id)
            .all()
        )

        added = []
        skipped = 0
        invalid = []
        for item in req.stocks:
            # 校验股票代码合法性
            stock_info = _validate_stock(item.ts_code)
            if stock_info is None:
                invalid.append(item.ts_code)
                continue

            if stock_info["ts_code"] in existing_codes:
                skipped += 1
                continue
            stock = WatchlistStock(
                group_id=group_id,
                ts_code=stock_info["ts_code"],
                symbol=stock_info["symbol"],
                name=stock_info["name"],
            )
            session.add(stock)
            added.append(stock_info["ts_code"])
            existing_codes.add(stock_info["ts_code"])

        session.commit()
        result = {"added": len(added), "skipped": skipped, "codes": added}
        if invalid:
            result["invalid"] = invalid
        return result
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error("批量添加自选股票失败: %s", e)
        raise HTTPException(status_code=500, detail=f"批量添加失败: {e}")
    finally:
        session.close()


@watchlist_router.delete("/stocks/{stock_id}")
async def remove_stock(
    stock_id: int,
    token: dict = Depends(require_api_token),
):
    """从自选分组中移除股票"""
    from ..dependencies import repository
    from ..store.models import WatchlistGroup, WatchlistStock

    session = repository.SessionLocal()
    try:
        stock = session.query(WatchlistStock).filter_by(id=stock_id).first()
        if not stock:
            raise HTTPException(status_code=404, detail="股票不存在")

        # 验证分组归属
        group = session.query(WatchlistGroup).filter_by(id=stock.group_id).first()
        if not group or group.user_id != token["user_id"]:
            raise HTTPException(status_code=403, detail="无权操作此股票")

        session.delete(stock)
        session.commit()
        return {"id": stock_id, "deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error("删除自选股票失败: %s", e)
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")
    finally:
        session.close()
