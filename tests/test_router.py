"""
核心交易接口测试: /api/*

测试范围:
  - GET    /api/health                       — 健康检查
  - GET    /api/strategies                   — 策略列表
  - POST   /api/strategies                   — 创建策略
  - GET    /api/strategies/{id}              — 策略详情
  - PUT    /api/strategies/{id}              — 更新策略
  - DELETE /api/strategies/{id}              — 删除策略
  - GET    /api/strategies/{id}/orders       — 委托列表
  - POST   /api/strategies/{id}/orders       — 下单
  - DELETE /api/strategies/{id}/orders/{oid} — 撤单
  - GET    /api/strategies/{id}/positions    — 持仓列表
  - PUT    /api/strategies/{id}/positions/{code}/remark — 更新持仓备注
  - GET    /api/trades                       — 成交记录

策略:
  - 所有接口已通过 conftest.py 的 dependency_overrides 绕过 JWT 认证
  - strategy_manager 通过 mock_strategy_manager fixture 注入
  - 数据库操作通过 mock_db_session fixture 隔离
  - 执行器 (sim/real) 通过 mock 隔离
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

import app.dependencies as deps


# ── /api/health ────────────────────────────────────

class TestHealth:

    def test_health_ok(self, client, mock_strategy_manager):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["strategies"] == 0

    def test_health_with_strategies(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1")
        mock_strategy_manager["s2"] = make_strategy("s2")
        resp = client.get("/api/health")
        assert resp.json()["strategies"] == 2


# ── /api/strategies (CRUD) ─────────────────────────

class TestListStrategies:

    def test_list_empty(self, client, mock_strategy_manager):
        resp = client.get("/api/strategies")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_all_fields(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1", name="策略A")
        resp = client.get("/api/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        s = data[0]
        assert s["strategy_id"] == "s1"
        assert s["name"] == "策略A"
        assert s["trade_mode"] == 0
        assert "initial_cash" in s
        assert "available_cash" in s
        assert "position_count" in s


class TestGetStrategy:

    def test_get_existing(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1", name="策略A")
        resp = client.get("/api/strategies/s1")
        assert resp.status_code == 200
        assert resp.json()["strategy_id"] == "s1"
        assert resp.json()["name"] == "策略A"

    def test_get_nonexistent_returns_404(self, client, mock_strategy_manager):
        resp = client.get("/api/strategies/ghost")
        assert resp.status_code == 404


class TestCreateStrategy:

    @patch.object(deps.repository, "add_strategy", return_value=True)
    def test_create_success(self, mock_add, client, mock_strategy_manager):
        resp = client.post("/api/strategies", json={
            "name": "新策略",
            "initial_cash": "500000",
            "trade_mode": 0,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["strategy_id"].startswith("s")
        # 策略应被加入内存
        assert data["strategy_id"] in mock_strategy_manager

    def test_create_with_invalid_trade_mode(self, client):
        resp = client.post("/api/strategies", json={
            "name": "坏策略",
            "trade_mode": 99,  # 非法
        })
        assert resp.status_code == 422

    def test_create_with_negative_cash(self, client):
        resp = client.post("/api/strategies", json={
            "name": "坏策略",
            "initial_cash": "-1",
        })
        assert resp.status_code == 422

    @patch.object(deps.repository, "add_strategy", return_value=False)
    def test_create_db_failure_returns_500(self, mock_add, client, mock_strategy_manager):
        resp = client.post("/api/strategies", json={"name": "新策略"})

        assert resp.status_code == 500
        assert "创建失败" in resp.json()["detail"]


class TestUpdateStrategy:

    def test_update_name(self, client, mock_strategy_manager, make_strategy):
        s = make_strategy("s1", name="原名")
        mock_strategy_manager["s1"] = s

        resp = client.put("/api/strategies/s1", json={"name": "新名"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "新名"
        assert s.name == "新名"  # 对象被原地修改

    def test_update_nonexistent_returns_404(self, client, mock_strategy_manager):
        resp = client.put("/api/strategies/ghost", json={"name": "新名"})
        assert resp.status_code == 404


class TestDeleteStrategy:

    @patch.object(deps.repository, "delete_strategy", return_value=True)
    def test_delete_empty_strategy(self, mock_del, client, mock_strategy_manager, make_strategy):
        s = make_strategy("s1")
        mock_strategy_manager["s1"] = s

        resp = client.delete("/api/strategies/s1")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert "s1" not in mock_strategy_manager

    def test_delete_nonexistent_returns_404(self, client, mock_strategy_manager):
        resp = client.delete("/api/strategies/ghost")
        assert resp.status_code == 404

    @patch.object(deps.repository, "delete_strategy", return_value=True)
    def test_delete_with_positions_returns_400(self, mock_del, client, mock_strategy_manager, make_strategy):
        from app.datatypes import Position
        s = make_strategy("s1")
        s.positions["000001.SZ"] = Position(stock_code="000001.SZ", total=100, available=100)
        mock_strategy_manager["s1"] = s

        resp = client.delete("/api/strategies/s1")
        assert resp.status_code == 400
        assert "持仓" in resp.json()["detail"]


# ── /api/strategies/{id}/orders ────────────────────

class TestListOrders:

    def test_list_orders_empty(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.get("/api/strategies/s1/orders")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_orders_nonexistent_strategy(self, client, mock_strategy_manager):
        resp = client.get("/api/strategies/ghost/orders")
        assert resp.status_code == 404

    def test_list_orders_returns_order_fields(self, client, mock_strategy_manager, make_strategy):
        from app import datatypes as dt
        s = make_strategy("s1")
        order = dt.Order(
            order_id="s1_1",
            strategy_id="s1",
            stock_code="000001.SZ",
            order_type=dt.OrderType.STOCK_BUY,
            price_type=dt.PriceType.FIX_PRICE,
            price=Decimal("10.50"),
            order_volume=1000,
            order_status=dt.OrderStatus.ORDER_UNREPORTED,
            created_at=datetime(2026, 1, 1, 10, 0),
        )
        s.orders["s1_1"] = order
        mock_strategy_manager["s1"] = s

        resp = client.get("/api/strategies/s1/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["order_id"] == "s1_1"
        assert data[0]["stock_code"] == "000001.SZ"
        assert data[0]["order_volume"] == 1000


class TestPlaceOrder:

    def test_place_order_nonexistent_strategy(self, client, mock_strategy_manager):
        resp = client.post("/api/strategies/ghost/orders", json={
            "stock_code": "000001.SZ",
            "order_type": 23,
            "price": "10.00",
            "order_volume": 100,
        })
        assert resp.status_code == 404

    def test_place_order_invalid_stock_code(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "INVALID",
            "order_type": 23,
            "price": "10.00",
            "order_volume": 100,
        })
        assert resp.status_code == 422

    def test_place_order_invalid_order_type(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "000001.SZ",
            "order_type": 99,
            "price": "10.00",
            "order_volume": 100,
        })
        assert resp.status_code == 422

    def test_place_order_invalid_volume(self, client, mock_strategy_manager, make_strategy):
        """委托数量不是 100 的整数倍 → 400."""
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "000001.SZ",
            "order_type": 23,
            "price": "10.00",
            "order_volume": 150,  # 不是 100 的整数倍
        })
        assert resp.status_code == 400

    def test_place_order_zero_price(self, client, mock_strategy_manager, make_strategy):
        """价格为 0 → 422 (Pydantic gt=0 校验)."""
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "000001.SZ",
            "order_type": 23,
            "price": "0",
            "order_volume": 100,
        })
        assert resp.status_code == 422

    @patch("app.api.router.get_sim_executor")
    @patch("app.api.router.get_calculator")
    def test_place_buy_order_success(self, mock_calc_fn, mock_sim_fn, client, mock_strategy_manager, make_strategy):
        """模拟买入下单 → 200 + order_id."""
        s = make_strategy("s1", initial_cash="1000000")
        mock_strategy_manager["s1"] = s

        # 手续费计算器
        mock_calc = MagicMock()
        mock_calc.calculate.return_value = Decimal("5.00")
        mock_calc_fn.return_value = mock_calc

        # 模拟执行器
        mock_sim = MagicMock()
        mock_sim.enqueue_order = AsyncMock()
        mock_sim_fn.return_value = mock_sim

        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "000001.SZ",
            "order_type": 23,
            "price": "10.00",
            "order_volume": 100,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["order_id"] != ""


class TestCancelOrder:

    def test_cancel_nonexistent_strategy(self, client, mock_strategy_manager):
        resp = client.delete("/api/strategies/ghost/orders/o1")
        assert resp.status_code == 404

    def test_cancel_nonexistent_order(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.delete("/api/strategies/s1/orders/o_ghost")
        assert resp.status_code == 404

    @patch("app.api.router.get_sim_executor")
    def test_cancel_pending_order(self, mock_sim_fn, client, mock_strategy_manager, make_strategy):
        """撤销未成交订单 → 200."""
        from app import datatypes as dt

        s = make_strategy("s1")
        order = dt.Order(
            order_id="s1_1",
            strategy_id="s1",
            stock_code="000001.SZ",
            order_type=dt.OrderType.STOCK_BUY,
            price_type=dt.PriceType.FIX_PRICE,
            price=Decimal("10.00"),
            order_volume=1000,
            order_status=dt.OrderStatus.ORDER_UNREPORTED,
            created_at=datetime.now(),
        )
        s.orders["s1_1"] = order
        mock_strategy_manager["s1"] = s

        mock_sim = MagicMock()
        mock_sim.cancel_order = AsyncMock()
        mock_sim_fn.return_value = mock_sim

        resp = client.delete("/api/strategies/s1/orders/s1_1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["order_id"] == "s1_1"


# ── /api/strategies/{id}/positions ─────────────────

class TestListPositions:

    def test_list_positions_empty(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.get("/api/strategies/s1/positions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_positions_nonexistent_strategy(self, client, mock_strategy_manager):
        resp = client.get("/api/strategies/ghost/positions")
        assert resp.status_code == 404

    @patch("app.api.router.get_stock_names", return_value={"000001.SZ": "平安银行"})
    def test_list_positions_with_data(self, mock_names, client, mock_strategy_manager, make_strategy):
        from app.datatypes import Position
        s = make_strategy("s1")
        s.positions["000001.SZ"] = Position(
            stock_code="000001.SZ",
            total=1000,
            available=800,
            frozen=200,
            avg_price=Decimal("15.50"),
        )
        mock_strategy_manager["s1"] = s

        resp = client.get("/api/strategies/s1/positions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        pos = data[0]
        assert pos["stock_code"] == "000001.SZ"
        assert pos["stock_name"] == "平安银行"
        assert pos["total"] == 1000
        assert pos["available"] == 800
        assert pos["frozen"] == 200

    @patch("app.api.router.get_stock_names", return_value={})
    def test_zero_position_not_listed(self, mock_names, client, mock_strategy_manager, make_strategy):
        """total=0 的持仓不应出现在列表中."""
        from app.datatypes import Position
        s = make_strategy("s1")
        s.positions["000001.SZ"] = Position(stock_code="000001.SZ", total=0)
        mock_strategy_manager["s1"] = s

        resp = client.get("/api/strategies/s1/positions")
        assert resp.status_code == 200
        assert resp.json() == []


class TestUpdatePositionRemark:

    def test_update_remark_success(self, client, mock_strategy_manager, make_strategy):
        from app.datatypes import Position
        s = make_strategy("s1")
        s.positions["000001.SZ"] = Position(stock_code="000001.SZ", total=100)
        mock_strategy_manager["s1"] = s

        resp = client.put("/api/strategies/s1/positions/000001.SZ/remark", json={
            "remark": "长线持有",
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_update_remark_nonexistent_position(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.put("/api/strategies/s1/positions/999999.SH/remark", json={
            "remark": "不存在",
        })
        assert resp.status_code == 404


# ── /api/trades ────────────────────────────────────

class TestListTrades:

    def test_trades_empty(self, client, mock_strategy_manager):
        resp = client.get("/api/trades")
        assert resp.status_code == 200
        assert resp.json() == []
    @patch("app.api.router.get_stock_names", return_value={})
    def test_trades_returns_records(self, mock_names, client, mock_strategy_manager, make_strategy):
        from app import datatypes as dt
        s = make_strategy("s1")
        trade = dt.Trade(
            traded_id="s1_1_0",
            strategy_id="s1",
            order_id="s1_1",
            stock_code="000001.SZ",
            order_type=23,
            traded_price=Decimal("10.00"),
            traded_volume=1000,
            traded_amount=Decimal("10000.00"),
            traded_time=datetime(2026, 1, 1, 10, 0),
        )
        s.trades.append(trade)
        mock_strategy_manager["s1"] = s

        resp = client.get("/api/trades")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["stock_code"] == "000001.SZ"
        assert data[0]["traded_volume"] == 1000

    @patch("app.api.router.get_stock_names", return_value={})
    def test_trades_filter_by_strategy(self, mock_names, client, mock_strategy_manager, make_strategy):
        from app import datatypes as dt
        s1 = make_strategy("s1")
        s2 = make_strategy("s2")
        s1.trades.append(dt.Trade(
            traded_id="s1_1_0", strategy_id="s1", order_id="s1_1",
            stock_code="000001.SZ", order_type=23,
            traded_price=Decimal("10.00"), traded_volume=100,
            traded_amount=Decimal("1000"), traded_time=datetime(2026, 1, 1),
        ))
        s2.trades.append(dt.Trade(
            traded_id="s2_1_0", strategy_id="s2", order_id="s2_1",
            stock_code="600000.SH", order_type=23,
            traded_price=Decimal("20.00"), traded_volume=200,
            traded_amount=Decimal("4000"), traded_time=datetime(2026, 1, 2),
        ))
        mock_strategy_manager["s1"] = s1
        mock_strategy_manager["s2"] = s2

        resp = client.get("/api/trades?strategy_id=s1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["stock_code"] == "000001.SZ"


# ── 输入校验边界 ────────────────────────────────────

class TestInputValidation:

    def test_order_volume_zero(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "000001.SZ",
            "order_type": 23,
            "price": "10.00",
            "order_volume": 0,
        })
        assert resp.status_code == 422

    def test_order_volume_negative(self, client, mock_strategy_manager, make_strategy):
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "000001.SZ",
            "order_type": 23,
            "price": "10.00",
            "order_volume": -100,
        })
        assert resp.status_code == 422

    def test_order_volume_too_large(self, client, mock_strategy_manager, make_strategy):
        """超过 100 万股上限 → 422."""
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "000001.SZ",
            "order_type": 23,
            "price": "10.00",
            "order_volume": 2000000,
        })
        assert resp.status_code == 422

    def test_price_too_high(self, client, mock_strategy_manager, make_strategy):
        """超过 A 股价格上限 → 422."""
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "000001.SZ",
            "order_type": 23,
            "price": "1000000",
            "order_volume": 100,
        })
        assert resp.status_code == 422

    def test_stock_code_with_suffix(self, client, mock_strategy_manager, make_strategy):
        """带 .SH/.SZ 后缀的代码应该通过校验 (非 422)."""
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "000001.SZ",
            "order_type": 23,
            "price": "10.00",
            "order_volume": 100,
        })
        # 状态码不应是 422 (格式校验通过; 可能 400/500 来自业务逻辑)
        assert resp.status_code != 422

    def test_stock_code_without_suffix(self, client, mock_strategy_manager, make_strategy):
        """6 位纯数字代码也应通过校验 (非 422)."""
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "000001",
            "order_type": 23,
            "price": "10.00",
            "order_volume": 100,
        })
        assert resp.status_code != 422  # 格式校验通过

    def test_stock_code_invalid_format(self, client, mock_strategy_manager, make_strategy):
        """格式错误的代码 → 422."""
        mock_strategy_manager["s1"] = make_strategy("s1")
        resp = client.post("/api/strategies/s1/orders", json={
            "stock_code": "ABC",
            "order_type": 23,
            "price": "10.00",
            "order_volume": 100,
        })
        assert resp.status_code == 422
