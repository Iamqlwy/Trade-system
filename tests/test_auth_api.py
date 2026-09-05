"""
认证接口测试: /api/auth/*

测试范围:
  - POST /api/auth/register — 用户注册 (首次用户 → admin)
  - POST /api/auth/login    — 用户登录 (JWT token 签发)
  - GET  /api/auth/me       — 当前用户信息 (需 Bearer token)

策略:
  - register / login 直接操作数据库 (通过 mock SessionLocal)
  - me 接口通过 conftest.py 中的 dependency_overrides 绕过 JWT
"""
from unittest.mock import MagicMock

from app.auth.security import hash_password


# ── /api/auth/register ─────────────────────────────

class TestRegister:

    def _make_query_mock(self, first_result=None, all_result=None):
        """构造 session.query(...).filter_by(...).first() / .all() 的 mock 链."""
        query_obj = MagicMock()
        query_obj.filter_by.return_value.first.return_value = first_result
        if all_result is not None:
            query_obj.all.return_value = all_result
        return query_obj

    def test_register_first_user_becomes_admin(self, client, mock_db_session):
        """第一个注册的用户自动成为 admin, 拥有全部权限."""
        # session.query() 被调用 3 次:
        #   1) query(User).filter_by(username=...).first() → None (无同名用户)
        #   2) query(User).filter_by(role="admin").first() → None (无 admin → 首次注册)
        #   3) query(Strategys).all() → [] (无策略, 循环跳过)
        mock_db_session.query.side_effect = [
            self._make_query_mock(first_result=None),
            self._make_query_mock(first_result=None),
            self._make_query_mock(all_result=[]),
        ]

        resp = client.post("/api/auth/register", json={
            "username": "alice",
            "password": "StrongPass1",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "alice"
        assert data["user"]["role"] == "admin"
        assert data["user"]["max_strategies"] == -1   # admin 无限制
        mock_db_session.commit.assert_called()

    def test_register_second_user_is_viewer(self, client, mock_db_session):
        """非首个注册用户默认为 viewer 角色."""
        existing_admin = MagicMock()
        existing_admin.role = "admin"
        # session.query() 被调用 2 次:
        #   1) query(User).filter_by(username=...).first() → None (无同名用户)
        #   2) query(User).filter_by(role="admin").first() → existing_admin (has_admin=True)
        # has_admin=True → 不进入 Strategys 查询分支
        mock_db_session.query.side_effect = [
            self._make_query_mock(first_result=None),
            self._make_query_mock(first_result=existing_admin),
        ]

        resp = client.post("/api/auth/register", json={
            "username": "bob",
            "password": "BobPass123",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["role"] == "viewer"
        assert data["user"]["max_strategies"] == 10

    def test_register_duplicate_username_returns_400(self, client, mock_db_session):
        """用户名已存在时返回 400."""
        existing_user = MagicMock()
        mock_db_session.query.side_effect = [
            self._make_query_mock(first_result=existing_user),
        ]

        resp = client.post("/api/auth/register", json={
            "username": "alice",
            "password": "StrongPass1",
        })

        assert resp.status_code == 400
        assert "已存在" in resp.json()["detail"]

    def test_register_username_too_short(self, client):
        """用户名少于 3 个字符 → 422 校验错误."""
        resp = client.post("/api/auth/register", json={
            "username": "ab",
            "password": "StrongPass1",
        })
        assert resp.status_code == 422

    def test_register_username_invalid_chars(self, client):
        """用户名含非法字符 → 422."""
        resp = client.post("/api/auth/register", json={
            "username": "hello world",
            "password": "StrongPass1",
        })
        assert resp.status_code == 422

    def test_register_password_too_short(self, client):
        """密码少于 8 个字符 → 422."""
        resp = client.post("/api/auth/register", json={
            "username": "alice",
            "password": "Ab1",
        })
        assert resp.status_code == 422

    def test_register_password_no_digit(self, client):
        """密码不含数字 → 422."""
        resp = client.post("/api/auth/register", json={
            "username": "alice",
            "password": "NoDigitsHere",
        })
        assert resp.status_code == 422

    def test_register_password_no_letter(self, client):
        """密码不含字母 → 422."""
        resp = client.post("/api/auth/register", json={
            "username": "alice",
            "password": "12345678",
        })
        assert resp.status_code == 422


# ── /api/auth/login ────────────────────────────────

class TestLogin:

    def _setup_user(self, mock_db_session, username="alice", password="GoodPass1", role="admin"):
        """构造一个模拟用户对象并挂到 session.query 上."""
        user = MagicMock()
        user.id = 1
        user.username = username
        user.role = role
        user.password_hash = hash_password(password)
        user.can_use_agent = True
        user.can_create_real = True
        user.max_strategies = -1 if role == "admin" else 10
        user.can_use_cron = True
        user.can_use_monitor = True
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = user
        return user

    def test_login_success(self, client, mock_db_session):
        """正确凭据 → 200 + JWT token."""
        self._setup_user(mock_db_session)

        resp = client.post("/api/auth/login", json={
            "username": "alice",
            "password": "GoodPass1",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["user"]["username"] == "alice"
        assert data["user"]["role"] == "admin"

    def test_login_wrong_password(self, client, mock_db_session):
        """密码错误 → 401."""
        self._setup_user(mock_db_session)

        resp = client.post("/api/auth/login", json={
            "username": "alice",
            "password": "WrongPassword1",
        })

        assert resp.status_code == 401
        assert "用户名或密码错误" in resp.json()["detail"]

    def test_login_nonexistent_user(self, client, mock_db_session):
        """用户不存在 → 401."""
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None

        resp = client.post("/api/auth/login", json={
            "username": "ghost",
            "password": "GoodPass1",
        })

        assert resp.status_code == 401

    def test_login_empty_username(self, client):
        """用户名为空 → 422."""
        resp = client.post("/api/auth/login", json={
            "username": "  ",
            "password": "GoodPass1",
        })
        assert resp.status_code == 422

    def test_login_empty_password(self, client):
        """密码为空 → 422."""
        resp = client.post("/api/auth/login", json={
            "username": "alice",
            "password": "  ",
        })
        assert resp.status_code == 422

    def test_login_returns_valid_jwt(self, client, mock_db_session):
        """登录返回的 JWT token 可以被解码."""
        self._setup_user(mock_db_session)

        resp = client.post("/api/auth/login", json={
            "username": "alice",
            "password": "GoodPass1",
        })

        token = resp.json()["token"]
        from app.auth.security import decode_token
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "alice"
        assert payload["role"] == "admin"


# ── /api/auth/me ───────────────────────────────────

class TestMe:

    def test_me_returns_user_info(self, client, mock_db_session):
        """GET /api/auth/me → 当前用户信息.

        注意: conftest.py 已将 require_api_token 替换为 fake_admin,
        此处 mock_db_session 提供数据库中的用户记录.
        """
        db_user = MagicMock()
        db_user.id = 1
        db_user.username = "testadmin"
        db_user.role = "admin"
        db_user.can_use_agent = True
        db_user.can_create_real = True
        db_user.max_strategies = -1
        db_user.can_use_cron = True
        db_user.can_use_monitor = True
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = db_user

        resp = client.get("/api/auth/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testadmin"
        assert data["role"] == "admin"
        assert data["max_strategies"] == -1

    def test_me_user_not_in_db_returns_401(self, client, mock_db_session):
        """数据库中用户不存在 (已被删除) → 401."""
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None

        resp = client.get("/api/auth/me")

        assert resp.status_code == 401
        assert "不存在" in resp.json()["detail"]
