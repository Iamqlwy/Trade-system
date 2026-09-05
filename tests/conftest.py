"""
pytest 全局配置

关键: JWT_SECRET 必须在任何 app.* 模块被导入之前设置到环境变量,
因为 app/auth/security.py 在模块级检查 JWT_SECRET, 缺失则 RuntimeError.

测试策略:
  - 创建轻量 FastAPI 测试应用 (跳过 lifespan, 不连接 MySQL/xtquant)
  - 通过 dependency_overrides 绕过 JWT 认证, 模拟 admin 用户
  - 通过 unittest.mock 隔离全局单例 (strategy_manager, repository)
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── 环境变量 (必须在 app 模块导入之前设置) ─────────────
os.environ.setdefault("JWT_SECRET", "a" * 48)  # 满足 ≥32 字符且无弱模式
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test_db")

# 确保项目根目录在 sys.path (pytest 从根目录运行时通常已自动添加)
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.dependencies as deps


# ── 测试用 FastAPI 应用 (不走 lifespan) ─────────────
@pytest.fixture(scope="session")
def app() -> FastAPI:
    """创建测试用 FastAPI 应用.

    与生产应用的区别:
      - 不执行 lifespan (不连 MySQL, 不加载 xtquant)
      - 不注册 CORS / auth 中间件 (通过 dependency_overrides 绕过)
      - 只挂载认证 + 核心交易两个路由
    """
    from app.api.auth_api import router as auth_router
    from app.api.router import router as api_router

    test_app = FastAPI()
    test_app.include_router(auth_router)
    test_app.include_router(api_router)

    # 全局绕过认证: 所有 Depends(require_api_token/...) 直接返回 admin 用户
    fake_admin = {
        "sub": "testadmin",
        "user_id": 1,
        "role": "admin",
    }
    from app.auth.dependencies import require_api_token
    from app.permissions import (
        require_strategy_access,
        require_strategy_trade,
        require_strategy_modify,
    )

    test_app.dependency_overrides[require_api_token] = lambda: fake_admin
    test_app.dependency_overrides[require_strategy_access] = lambda: fake_admin
    test_app.dependency_overrides[require_strategy_trade] = lambda: fake_admin
    test_app.dependency_overrides[require_strategy_modify] = lambda: fake_admin

    return test_app


@pytest.fixture(scope="session")
def client(app: FastAPI) -> TestClient:
    """HTTP 测试客户端 (同步, 与 Flask test_client 等价)."""
    return TestClient(app)


@pytest.fixture
def mock_db_session():
    """模拟数据库会话.

    用途: 测试中需要精确控制 session.query(...).filter_by(...).first()
    返回值时, patch 此 fixture 的返回值.

    用法示例:
        def test_login(mock_db_session):
            mock_user = MagicMock()
            mock_user.id = 1
            mock_db_session.query.return_value.filter_by.return_value.first.return_value = mock_user
    """
    session = MagicMock()
    with patch.object(deps.repository, "SessionLocal", return_value=session):
        yield session


@pytest.fixture
def mock_strategy_manager():
    """空的策略管理器.

    默认提供空 dict; 测试中可自行填充 Strategy 对象.
    同时 patch router 模块中的 get_accessible_strategy_ids 为 None (admin 全部可见).

    注意: router 通过 ``from ..dependencies import get_strategies, get_strategy``
    将函数绑定到 *自己的* 命名空间, 因此必须 patch ``app.api.router.xxx``
    而非 ``app.dependencies.xxx`` (后者的重绑定对 router 不可见).

    用法:
        def test_list_strategies(mock_strategy_manager):
            mock_strategy_manager["s1"] = make_strategy("s1")
            resp = client.get("/api/strategies")
    """
    mgr: dict = {}
    import app.api.router as api_router_mod
    with (
        # 核心: patch router 命名空间中的引用 (handler 实际使用的名称)
        patch.object(api_router_mod, "get_strategies", return_value=mgr),
        patch.object(api_router_mod, "get_strategy", side_effect=lambda sid: mgr.get(sid)),
        patch.object(api_router_mod, "get_accessible_strategy_ids", return_value=None),
        # deps 单例也需要 patch (其他模块如 auth_api 可能直接从 deps 引用)
        patch.object(deps, "strategy_manager", mgr),
    ):
        yield mgr


@pytest.fixture
def mock_market_data():
    """模拟 MarketData 单例."""
    md = MagicMock()
    md.get_all_ticks.return_value = {}
    with patch.object(deps, "market_data", md):
        yield md


# ── 辅助工厂函数 / fixture ─────────────────────────

@pytest.fixture
def make_strategy():
    """快速创建 Strategy 实例的 fixture.

    用法:
        def test_xxx(make_strategy):
            s = make_strategy("s1", name="策略A")
    """
    from decimal import Decimal
    from app.engine.strategy import Strategy

    def _factory(
        strategy_id: str = "test_s1",
        name: str = "测试策略",
        initial_cash: str = "1000000",
        trade_mode: int = 0,
    ):
        return Strategy(
            strategy_id=strategy_id,
            name=name,
            initial_cash=Decimal(initial_cash),
            available_cash=Decimal(initial_cash),
            frozen_cash=Decimal("0"),
            trade_mode=trade_mode,
        )

    return _factory
