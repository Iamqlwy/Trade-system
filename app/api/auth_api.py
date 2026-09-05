"""
JSON auth endpoints for SPA frontend.
"""
import logging
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..auth.security import hash_password, verify_password, create_token, decode_token
from ..auth.models import User
from ..dependencies import repository
from ..auth.dependencies import require_api_token
from ..logutils.audit import log_auth_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── 输入校验常量 ────────────────────────────────
_USERNAME_MIN = 3
_USERNAME_MAX = 20
_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")
_PASSWORD_MIN = 8
_PASSWORD_MAX = 128

# ── 登录限速 ─────────────────────────────────
# 内存级速率限制器，防止暴力破解
# 同时按 IP 和用户名限速，防止反代后所有请求共享同一 IP
_login_attempts_ip: dict[str, list[float]] = {}  # IP → [失败时间戳]
_login_attempts_user: dict[str, list[float]] = {}  # username → [失败时间戳]
_LOGIN_MAX_ATTEMPTS = 5  # 最大失败次数
_LOGIN_LOCKOUT_SECONDS = 300  # 锁定时间（5 分钟）


def _check_login_rate_limit(ip: str, username: str) -> None:
    """检查 IP 和用户名是否被限速，超限时抛出 HTTPException"""
    now = time.time()

    # 检查 IP 限速
    for store, key, label in [
        (_login_attempts_ip, ip, "IP"),
        (_login_attempts_user, username, "用户名"),
    ]:
        attempts = store.get(key, [])
        attempts = [t for t in attempts if now - t < _LOGIN_LOCKOUT_SECONDS]
        store[key] = attempts

        if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
            remaining = int(_LOGIN_LOCKOUT_SECONDS - (now - attempts[0]))
            logger.warning("登录限速: %s=%s 已被锁定，剩余 %d 秒", label, key, remaining)
            raise HTTPException(
                status_code=429,
                detail=f"登录尝试过多，请 {max(remaining, 1)} 秒后重试",
            )


def _record_login_failure(ip: str, username: str) -> None:
    """记录一次登录失败（同时记录 IP 和用户名）"""
    now = time.time()
    for store, key in [(_login_attempts_ip, ip), (_login_attempts_user, username)]:
        if key not in store:
            store[key] = []
        store[key].append(now)


def _clear_login_failures(ip: str, username: str) -> None:
    """登录成功后清除失败记录"""
    _login_attempts_ip.pop(ip, None)
    _login_attempts_user.pop(username, None)


def _session() -> Session:
    return repository.SessionLocal()


class LoginRequest(BaseModel):
    """登录请求 — 不做格式校验，凭据对错由数据库验证决定"""
    username: str
    password: str

    @field_validator("username", "password")
    @classmethod
    def _non_empty(cls, v: str, info) -> str:
        v = v.strip()
        if not v:
            raise ValueError(f"{info.field_name} 不能为空")
        return v


class RegisterRequest(BaseModel):
    """注册请求 — 严格格式校验"""
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < _USERNAME_MIN:
            raise ValueError(f"用户名至少 {_USERNAME_MIN} 个字符")
        if len(v) > _USERNAME_MAX:
            raise ValueError(f"用户名最多 {_USERNAME_MAX} 个字符")
        if not _USERNAME_PATTERN.match(v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < _PASSWORD_MIN:
            raise ValueError(f"密码至少 {_PASSWORD_MIN} 个字符")
        if len(v) > _PASSWORD_MAX:
            raise ValueError(f"密码最多 {_PASSWORD_MAX} 个字符")
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("密码必须包含至少一个字母")
        if not re.search(r"[0-9]", v):
            raise ValueError("密码必须包含至少一个数字")
        return v


class UserInfo(BaseModel):
    id: int
    username: str
    role: str
    can_use_agent: bool = True
    can_create_real: bool = True
    max_strategies: int = 10
    can_use_cron: bool = True
    can_use_monitor: bool = True


def _user_to_info(u) -> UserInfo:
    """从 DB User 对象构造 UserInfo（admin 强制全权限）"""
    is_admin = u.role == "admin"
    return UserInfo(
        id=u.id,
        username=u.username,
        role=u.role,
        can_use_agent=is_admin or (u.can_use_agent if u.can_use_agent is not None else True),
        can_create_real=is_admin or (u.can_create_real if u.can_create_real is not None else True),
        max_strategies=-1 if is_admin else (u.max_strategies if u.max_strategies is not None else 10),
        can_use_cron=is_admin or (u.can_use_cron if u.can_use_cron is not None else True),
        can_use_monitor=is_admin or (u.can_use_monitor if u.can_use_monitor is not None else True),
    )


class LoginResponse(BaseModel):
    token: str
    user: UserInfo


@router.post("/login", response_model=LoginResponse)
async def api_login(req: LoginRequest, request: Request):
    # 登录限速检查（同时检查 IP 和用户名）
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip, req.username)

    session = _session()
    try:
        user = session.query(User).filter_by(username=req.username).first()
        if not user or not verify_password(req.password, user.password_hash):
            _record_login_failure(client_ip, req.username)
            logger.warning("API 登录失败: username=%s ip=%s", req.username, client_ip)
            log_auth_event(username=req.username, action="LOGIN_FAILED", success=False)
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 登录成功，清除失败记录
        _clear_login_failures(client_ip, req.username)
        token = create_token(user.id, user.username, user.role)
        logger.info("API 登录成功: username=%s role=%s ip=%s", user.username, user.role, client_ip)
        log_auth_event(username=user.username, action="LOGIN", success=True)
        return LoginResponse(
            token=token,
            user=_user_to_info(user),
        )
    finally:
        session.close()


@router.post("/register", response_model=LoginResponse)
async def api_register(req: RegisterRequest):
    session = _session()
    try:
        existing = session.query(User).filter_by(username=req.username).first()
        if existing:
            raise HTTPException(status_code=400, detail="用户名已存在")

        # First user is admin — check existing admins to avoid race condition
        # where two concurrent registrations both see count()==0
        has_admin = session.query(User).filter_by(role="admin").first() is not None
        is_first = not has_admin
        user = User(
            username=req.username,
            password_hash=hash_password(req.password),
            role="viewer" if has_admin else "admin",
            # admin 引导用户：全部权限 + 策略无限制；普通用户：全部开启 + 默认 10 个策略
            can_use_agent=True,
            can_create_real=True,
            max_strategies=-1 if is_first else 10,
            can_use_cron=True,
            can_use_monitor=True,
        )
        try:
            session.add(user)
            session.flush()  # 获取 user.id 但不提交
        except IntegrityError:
            session.rollback()
            raise HTTPException(status_code=400, detail="用户名已存在")

        # Grant access to all strategies for first user (admin bootstrap)
        if not has_admin:
            from ..store.models import Strategys
            from ..auth.models import StrategyUser
            for s in session.query(Strategys).all():
                session.add(StrategyUser(user_id=user.id, strategy_id=s.strategy_id, can_trade=True))

        session.commit()  # 原子提交：用户 + 权限一起写入

        token = create_token(user.id, user.username, user.role)
        log_auth_event(username=user.username, action="REGISTER", success=True)
        return LoginResponse(
            token=token,
            user=_user_to_info(user),
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.exception("API 注册失败")
        raise HTTPException(status_code=400, detail=f"注册失败: {e}")
    finally:
        session.close()


@router.get("/me", response_model=UserInfo)
async def api_me(user: dict = Depends(require_api_token)):
    # 验证用户仍在数据库中（数据库重置后 token 虽未过期但用户已不存在）
    session = _session()
    try:
        db_user = session.query(User).filter_by(id=user["user_id"]).first()
        if not db_user:
            raise HTTPException(status_code=401, detail="用户不存在或已被删除")
        return _user_to_info(db_user)
    finally:
        session.close()
