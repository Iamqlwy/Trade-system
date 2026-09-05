"""监控调度引擎

脚本保留在 agent workspace，元数据存储在数据库 monitor_records 表（通过 upload API 写入）。
加载/执行时通过 session_id 定位 workspace，从工作区读取脚本。

职责：
  - 从 DB 加载监控元数据（含 script_metadata 和 params）
  - 动态解析股票列表（直接代码 + 策略持仓）
  - 按 interval 定时调度执行 check.py
  - 同监控+同股票冷却防重复触发
  - 持久 Docker 单容器 + docker exec 执行 + 触发日志 + WebSocket 广播
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess as _sp
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────

_INTERVAL_MAP: dict[str, float] = {
    "10s": 10, "30s": 30,
    "1m": 60, "5m": 300, "10m": 600,
    "15m": 900, "30m": 1800, "1h": 3600,
}

_VALID_INTERVALS = set(_INTERVAL_MAP.keys())

# klines 数据目录（挂载到 Docker 容器内供脚本读取）
_KLINES_DIR = Path("C:/klines")

# 持久 Docker 容器名称
_CONTAINER_NAME = "quant-monitor"

# 交易时段（小时, 分钟）— 仅在这些时段内调度执行
_TRADING_SESSIONS = [
    ((9, 15), (9, 25)),    # 集合竞价
    ((9, 30), (11, 30)),   # 上午连续竞价
    ((13, 0), (15, 0)),    # 下午连续竞价
]

# 交易日缓存：{日期str: bool}，避免每秒都读文件
_trading_day_cache: dict[str, bool] = {}
_trading_day_cache_date: str = ""  # 当天日期，跨天失效


def _get_recent_trading_days(ref_date: str, n: int = 30) -> list[str]:
    """获取 ref_date（YYYYMMDD）之前最近 N 个交易日。

    优先 akshare，降级工作日算法。
    """
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        df = df.sort_values(by="trade_date").drop_duplicates(subset=["trade_date"])
        days = df["trade_date"].astype(str).str.replace("-", "").tolist()
        days = [d for d in days if d <= ref_date]
        return days[-n:] if len(days) > n else days
    except Exception:
        pass

    return _workday_fallback(ref_date, n)


def _workday_fallback(ref_date: str, n: int) -> list[str]:
    """降级：仅按周一至周五生成交易日（不含节假日）。"""
    from datetime import timedelta
    result: list[str] = []
    year = int(ref_date[:4])
    month = int(ref_date[4:6])
    day = int(ref_date[6:8])
    d = datetime(year, month, day).date()
    while len(result) < n:
        if d.weekday() < 5:
            result.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    result.reverse()
    return result


def _is_trading_day(date_str: str | None = None) -> bool:
    """判断指定日期是否为交易日（YYYYMMDD 格式，默认今天）。

    缓存机制：同一日期只查询一次。
    """
    global _trading_day_cache, _trading_day_cache_date

    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    # 跨天清缓存
    today_str = datetime.now().strftime("%Y%m%d")
    if _trading_day_cache_date != today_str:
        _trading_day_cache.clear()
        _trading_day_cache_date = today_str

    if date_str in _trading_day_cache:
        return _trading_day_cache[date_str]

    # 周末直接 False
    year, month, day = int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])
    try:
        if datetime(year, month, day).weekday() >= 5:
            _trading_day_cache[date_str] = False
            return False
    except ValueError:
        _trading_day_cache[date_str] = False
        return False

    # 查最近 30 个交易日，看 date_str 是否在其中
    recent = _get_recent_trading_days(date_str, n=30)
    is_td = date_str in recent
    _trading_day_cache[date_str] = is_td
    return is_td


def _is_trading_time() -> bool:
    """判断当前是否为交易时段：交易日 + 交易时间段。"""
    now = datetime.now()
    # 时间窗口检查
    t = (now.hour, now.minute)
    in_session = any((sh, sm) <= t <= (eh, em) for (sh, sm), (eh, em) in _TRADING_SESSIONS)
    if not in_session:
        return False
    # 交易日检查
    return _is_trading_day(now.strftime("%Y%m%d"))


def _is_traceback(text: str) -> bool:
    """检测文本是否包含 Python 异常堆栈"""
    return (
        "Traceback (most recent call last)" in text
        or "Traceback (most recent call first)" in text
    )


def _is_json(text: str) -> bool:
    """检测文本是否为合法 JSON"""
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


# ── 数据结构 ──────────────────────────────────

@dataclass
class MonitorInfo:
    """监控元信息（从 DB 加载）"""
    monitor_id: str = ""
    monitor_name: str = ""
    description: str = ""
    stock_codes: list[str] = field(default_factory=list)
    strategy_ids: list[str] = field(default_factory=list)     # 策略ID列表（动态获取持仓）
    interval: str = "30s"
    trigger_mode: str = "periodic"
    enabled: bool = True
    cooldown_seconds: int = 300     # 同监控+同股票 防重复触发冷却（秒），默认 5 分钟
    script_metadata: dict = field(default_factory=dict)   # AI 生成的脚本元数据
    params: dict = field(default_factory=dict)            # 用户配置的参数值
    owner_id: Optional[int] = None  # 创建者用户ID（None=老数据/无归属）
    # 工作区定位（脚本保留在 agent workspace，不拷贝）
    session_id: str = ""            # agent 会话 ID（定位 workspace 目录）
    script_path: str = "check.py"   # workspace 内的相对路径
    # 运行时状态（不持久化）
    next_run: float = 0.0
    last_run: Optional[str] = None
    last_result: Optional[dict] = None
    error_message: str = ""
    consecutive_errors: int = 0


# ── 引擎 ──────────────────────────────────────

class MonitorEngine:
    """监控调度引擎 — 持久单容器 docker exec 模式"""

    def __init__(
        self,
        market_data: Any,
    ):
        self._market_data = market_data

        self._monitors: dict[str, MonitorInfo] = {}
        self._price_histories: dict[str, deque] = {}
        self._alert_subs: list[WebSocket] = []
        self._last_trigger: dict[tuple[str, str], float] = {}
        self._kline_1m = None  # 延迟初始化
        self._running = False
        self._task: Optional[asyncio.Task] = None
        # Docker 沙箱镜像和容器
        self._sandbox_image = "quant-sandbox:latest"

    # ── 生命周期 ──────────────────────────────

    async def start(self) -> None:
        self._running = True
        # 注入 Kline1mAggregator
        try:
            from ..dependencies import get_kline_1m
            self._kline_1m = get_kline_1m()
        except Exception:
            pass
        # 启动持久 Docker 容器
        await self._ensure_container()
        self._load_monitors()
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info("MonitorEngine 启动，发现 %d 个监控", len(self._monitors))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # 销毁持久容器
        await self._remove_container()
        logger.info("MonitorEngine 已停止")

    # ── 调度循环 ──────────────────────────────

    async def _schedule_loop(self) -> None:
        scan_counter = 0
        while self._running:
            try:
                if scan_counter % 5 == 0:
                    self._load_monitors()

                # 非交易时段跳过调度
                if _is_trading_time():
                    now = time.time()
                    for mid, info in list(self._monitors.items()):
                        if not info.enabled or info.trigger_mode != "periodic":
                            continue
                        if now >= info.next_run:
                            asyncio.create_task(self._run_one(mid))

                self._sample_prices()
            except Exception:
                logger.exception("调度循环异常")

            scan_counter += 1
            await asyncio.sleep(1)

    def _sample_prices(self) -> None:
        all_codes = self._resolve_all_stock_codes()
        for code in all_codes:
            price = self._market_data.get_price(code)
            if price is not None and price > Decimal("0"):
                if code not in self._price_histories:
                    self._price_histories[code] = deque(maxlen=3600)
                self._price_histories[code].append(price)

    def _resolve_all_stock_codes(self) -> set[str]:
        """收集所有被监控股票代码（用于价格采样）"""
        codes: set[str] = set()
        for info in self._monitors.values():
            if info.enabled and info.script_metadata.get("has_stock_param", False):
                codes.update(self._resolve_stock_codes(info))
        return codes

    # ── 股票解析 ──────────────────────────────

    def _resolve_stock_codes(self, info: MonitorInfo) -> list[str]:
        """解析最终股票列表 = 直接代码 + 策略持仓"""
        codes: set[str] = set()

        # 1. 直接指定的股票代码
        codes.update(info.stock_codes)

        # 2. 策略持仓动态获取
        codes.update(self._get_strategy_positions(info.strategy_ids))

        return list(codes)

    def _get_strategy_positions(self, strategy_ids: list[str]) -> set[str]:
        """从 strategy_manager 获取指定策略的所有持仓股票代码"""
        codes: set[str] = set()
        try:
            from ..dependencies import strategy_manager
            for sid in strategy_ids:
                strategy = strategy_manager.get(sid)
                if strategy:
                    codes.update(strategy.positions.keys())
        except Exception:
            logger.debug("获取策略持仓失败: %s", strategy_ids)
        return codes

    # ── 冷却检查 ──────────────────────────────

    def _is_in_cooldown(self, monitor_id: str, stock_code: str, cooldown_sec: int) -> bool:
        """检查是否在冷却期内"""
        if cooldown_sec <= 0:
            return False
        key = (monitor_id, stock_code)
        last = self._last_trigger.get(key, 0)
        return (time.time() - last) < cooldown_sec

    def _mark_triggered(self, monitor_id: str, stock_code: str) -> None:
        """记录触发时间"""
        self._last_trigger[(monitor_id, stock_code)] = time.time()

    # ── 加载（从 DB）──────────────────────────────

    @staticmethod
    def _resolve_script_path(session_id: str, script_path: str) -> Optional[Path]:
        """从 agent workspace 解析监控脚本的绝对路径。

        session_id → {agent_home}/workspaces/{session_id}/{script_path}
        返回 None 表示 workspace 不存在。
        """
        from ..agent.config import get_workspace_dir
        workspace = get_workspace_dir(session_id)
        if not workspace.exists():
            return None
        # 防止路径穿越（只允许 workspace 内的文件）
        resolved = (workspace / script_path).resolve()
        if not str(resolved).startswith(str(workspace.resolve())):
            logger.warning("监控脚本路径越界: session=%s, path=%s", session_id, script_path)
            return None
        return resolved

    def _load_monitors(self) -> None:
        """从 DB 加载监控元数据，保留运行时状态。

        脚本保留在 agent workspace，通过 session_id + script_path 定位。
        workspace 或脚本文件不存在时跳过并记录警告。
        """
        from ..dependencies import repository
        from ..store.models import MonitorRecord

        session = repository.SessionLocal()
        try:
            rows = session.query(MonitorRecord).all()
            db_ids: set[str] = set()
            missing: list[str] = []      # workspace/脚本不存在

            for row in rows:
                mid = row.monitor_id
                db_ids.add(mid)

                # 跳过没有 session_id 的旧数据
                sid = row.session_id or ""
                if not sid:
                    missing.append(f"{mid}(无session_id)")
                    continue

                # 解析 workspace 中的脚本绝对路径
                abs_path = self._resolve_script_path(sid, row.script_path or "check.py")
                if abs_path is None or not abs_path.exists():
                    missing.append(mid)
                    continue

                existing = self._monitors.get(mid)
                info = MonitorInfo(
                    monitor_id=mid,
                    monitor_name=row.monitor_name or "",
                    description=row.description or "",
                    stock_codes=row.stock_codes or [],
                    strategy_ids=row.strategy_ids or [],
                    interval=row.interval or "30s",
                    trigger_mode=row.trigger_mode or "periodic",
                    enabled=row.enabled if row.enabled is not None else True,
                    cooldown_seconds=row.cooldown_seconds or 300,
                    script_metadata=row.script_metadata or {},
                    params=row.params or {},
                    owner_id=row.owner_id,
                    session_id=sid,
                    script_path=row.script_path or "check.py",
                )

                if info.interval not in _VALID_INTERVALS:
                    info.interval = "30s"
                if info.trigger_mode not in ("periodic", "manual"):
                    info.trigger_mode = "periodic"

                # 保留运行时状态
                if existing:
                    info.next_run = existing.next_run
                    info.last_run = existing.last_run
                    info.last_result = existing.last_result
                    info.error_message = existing.error_message
                    info.consecutive_errors = existing.consecutive_errors

                if info.next_run == 0:
                    info.next_run = time.time()

                self._monitors[mid] = info

            # 清理已删除的监控
            removed = set(self._monitors.keys()) - db_ids
            for mid in removed:
                del self._monitors[mid]
                # 清理冷却记录
                keys_to_remove = [k for k in self._last_trigger if k[0] == mid]
                for k in keys_to_remove:
                    del self._last_trigger[k]

            # 诊断日志
            if missing:
                logger.warning(
                    "监控脚本不可用（workspace 或文件不存在）: %s",
                    ", ".join(missing),
                )
            if removed:
                logger.info("清理已删除的监控: %s", ", ".join(removed))
            logger.debug(
                "监控加载完成: DB=%d, 已加载=%d, 不可用=%d, 已清理=%d",
                len(db_ids), len(self._monitors), len(missing), len(removed),
            )

        except Exception:
            logger.exception("从 DB 加载监控失败")
        finally:
            session.close()

    def _save_to_db(self, info: MonitorInfo) -> None:
        """将 MonitorInfo 的元数据写回 DB。"""
        from ..dependencies import repository
        from ..store.models import MonitorRecord

        session = repository.SessionLocal()
        try:
            row = session.query(MonitorRecord).filter_by(
                monitor_id=info.monitor_id,
            ).first()
            if row:
                row.monitor_name = info.monitor_name
                row.description = info.description
                row.stock_codes = info.stock_codes
                row.strategy_ids = info.strategy_ids
                row.interval = info.interval
                row.trigger_mode = info.trigger_mode
                row.enabled = info.enabled
                row.cooldown_seconds = info.cooldown_seconds
                row.script_metadata = info.script_metadata
                row.params = info.params
                session.commit()
        except Exception:
            session.rollback()
            logger.exception("保存监控到 DB 失败: %s", info.monitor_id)
        finally:
            session.close()

    # ── 执行 ──────────────────────────────────

    async def _run_one(self, monitor_id: str) -> None:
        info = self._monitors.get(monitor_id)
        if not info:
            return

        # 非交易时段不执行
        if not _is_trading_time():
            return

        # ── 权限检查：owner 是否仍有监控权限 ──
        if info.owner_id is not None and not _user_has_monitor_permission(info.owner_id):
            logger.warning(
                "Monitor '%s' skipped: user %d lost can_use_monitor permission",
                monitor_id, info.owner_id,
            )
            return

        interval_sec = _INTERVAL_MAP.get(info.interval, 30)
        info.next_run = time.time() + interval_sec

        has_stock = info.script_metadata.get("has_stock_param", False)

        if has_stock:
            # 模式 1：有股票参数 → 逐只股票执行
            resolved_codes = self._resolve_stock_codes(info)
            pending_codes = [
                code for code in resolved_codes
                if not self._is_in_cooldown(info.monitor_id, code, info.cooldown_seconds)
            ]
            if not pending_codes:
                return
        else:
            # 模式 2：复杂固定条件 → 单次执行，按 monitor 整体冷却
            if self._is_in_cooldown(info.monitor_id, "__monitor__", info.cooldown_seconds):
                return
            pending_codes = []

        try:
            result = await self._execute_script(info, pending_codes)
            self._process_results(info, pending_codes, result)
            info.consecutive_errors = 0
            info.error_message = ""
        except Exception as e:
            info.consecutive_errors += 1
            info.error_message = str(e)
            logger.warning("监控 %s 执行失败: %s", monitor_id, e)
            # 错误也进入冷却
            self._mark_triggered(info.monitor_id, "__monitor__")
            for code in pending_codes:
                self._mark_triggered(info.monitor_id, code)
            # 记录错误到 DB + 通知用户
            asyncio.create_task(self._log_error(info, "", str(e)))
            asyncio.create_task(self._notify_user(info, "", str(e), is_error=True))
            if info.consecutive_errors >= 5:
                info.enabled = False
                self._save_to_db(info)
                logger.warning("监控 %s 连续错误 %d 次，已自动禁用", monitor_id, info.consecutive_errors)

        info.last_run = datetime.now().isoformat()

    def _process_results(
        self, info: MonitorInfo, stock_codes: list[str], result,
    ) -> None:
        """处理 _execute_script 聚合后的结果列表。

        每个元素为单个 JSON object: {triggered, message, data, stock_code?}
        由 _execute_script 逐只股票 docker exec 后聚合而成。
        """
        if not isinstance(result, list):
            return

        for entry in result:
            if not isinstance(entry, dict):
                continue
            triggered = entry.get("triggered", False)
            code = entry.get("stock_code", "")
            error = entry.get("error")

            # 记录单只股票执行错误（也进入冷却）
            if error:
                if code:
                    self._mark_triggered(info.monitor_id, code)
                asyncio.create_task(self._log_error(info, code, error))
                asyncio.create_task(self._notify_user(info, code, error, is_error=True))
                continue

            info.last_result = {
                "stock_code": code,
                "triggered": triggered,
                "message": entry.get("message", ""),
                "time": datetime.now().strftime("%H:%M:%S"),
            }
            if triggered:
                cooldown_key = code or "__monitor__"
                if code and self._is_in_cooldown(info.monitor_id, code, info.cooldown_seconds):
                    continue
                self._mark_triggered(info.monitor_id, cooldown_key)
                asyncio.create_task(self._log_alert(info, code, entry))

    # ── Docker 容器管理 ────────────────────────

    async def _ensure_container(self) -> None:
        """启动持久 Docker 容器。已存在则跳过，不健康则重建。"""
        # 检查容器是否存在
        check = await asyncio.to_thread(
            _sp.run, ["docker", "inspect", _CONTAINER_NAME],
            capture_output=True, timeout=10,
        )
        if check.returncode == 0:
            # 检查是否正在运行
            inspect = await asyncio.to_thread(
                _sp.run,
                ["docker", "inspect", "-f", "{{.State.Running}}", _CONTAINER_NAME],
                capture_output=True, timeout=10,
            )
            running = inspect.stdout.decode().strip() == "true"
            if running:
                logger.info("持久容器 %s 已在运行", _CONTAINER_NAME)
                return
            # 容器存在但未运行，删除重建
            await asyncio.to_thread(
                _sp.run, ["docker", "rm", "-f", _CONTAINER_NAME],
                capture_output=True, timeout=10,
            )

        # 构建挂载参数
        from ..agent.config import get_workspaces_dir
        workspaces_dir = get_workspaces_dir()

        cmd = [
            "docker", "run", "-d", "--name", _CONTAINER_NAME,
            "--read-only", "--init",
            "--network=none",
            "--memory=256m", "--cpus=0.5",
            "--pids-limit=32",
            "--user=1000:1000",
            "--security-opt=no-new-privileges",
            "--workdir=/workspaces",
            "-v", f"{workspaces_dir}:/workspaces:ro",
        ]
        if _KLINES_DIR.exists():
            cmd.extend(["-v", f"{_KLINES_DIR}:/data/klines:ro"])

        cmd.extend([self._sandbox_image, "tail", "-f", "/dev/null"])

        result = await asyncio.to_thread(
            _sp.run, cmd, capture_output=True, timeout=30,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            logger.error("创建持久容器失败: %s", stderr)
            raise RuntimeError(f"Docker 容器创建失败: {stderr}")

        logger.info("持久容器 %s 已启动", _CONTAINER_NAME)

    async def _remove_container(self) -> None:
        """销毁持久 Docker 容器。"""
        try:
            await asyncio.to_thread(
                _sp.run, ["docker", "rm", "-f", _CONTAINER_NAME],
                capture_output=True, timeout=10,
            )
            logger.info("持久容器 %s 已销毁", _CONTAINER_NAME)
        except Exception:
            logger.warning("销毁持久容器失败", exc_info=True)

    # ── 脚本执行 ──────────────────────────────

    def _build_param_args(self, metadata: dict, params: dict) -> list[str]:
        """从 metadata + params 构建 CLI 参数列表。

        e.g., metadata 定义 lookback_days(int, default=30), params 值 60
        → ["--lookback_days", "60"]
        """
        args: list[str] = []
        for pdef in metadata.get("parameters", []):
            name = pdef.get("name")
            if not name:
                continue  # 跳过无效的参数定义
            value = params.get(name, pdef.get("default"))
            if value is None:
                continue
            ptype = pdef.get("type", "string")
            if ptype == "bool":
                if value:
                    args.append(f"--{name}")
            else:
                args.extend([f"--{name}", str(value)])
        return args

    async def _exec_script(
        self, info: MonitorInfo, stock_code: Optional[str] = None,
    ) -> Optional[dict]:
        """在持久容器中 docker exec 执行一次脚本，返回单个 JSON object。"""
        has_stock = info.script_metadata.get("has_stock_param", False)

        cmd = [
            "docker", "exec", _CONTAINER_NAME,
            "python3", f"/workspaces/{info.session_id}/{info.script_path}",
        ]

        # 添加 --stock 参数
        if has_stock and stock_code:
            cmd.extend(["--stock", stock_code])

        # 添加用户配置的参数
        cmd.extend(self._build_param_args(info.script_metadata, info.params))

        try:
            result = await asyncio.to_thread(
                _sp.run, cmd, capture_output=True, timeout=30,
            )
        except _sp.TimeoutExpired:
            raise ValueError(f"监控脚本执行超时 (30s)")

        stdout = result.stdout.decode("utf-8", errors="replace").strip()
        stderr = result.stderr.decode("utf-8", errors="replace").strip()

        if result.returncode != 0:
            if _is_traceback(stderr):
                lines = stderr.strip().split("\n")
                raise ValueError(f"监控脚本异常 (exit={result.returncode}): {lines[-1]}")
            raise ValueError(
                f"监控脚本执行失败 (exit={result.returncode}): {stderr[:500] or stdout[:500]}"
            )

        # 解析 stdout 中的 JSON object
        parsed = None
        if stdout:
            for line in stdout.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        parsed = obj
                        break
                except (json.JSONDecodeError, ValueError):
                    continue

        if parsed is None:
            if stderr:
                if _is_traceback(stderr):
                    raise ValueError(f"监控脚本异常: {stderr.strip().split(chr(10))[-1]}")
                raise ValueError(f"监控脚本无有效 JSON 输出; stderr: {stderr[:300]}")
            raise ValueError("监控脚本无有效 JSON 输出")

        # 错误检测
        if "error" in parsed:
            raise ValueError(parsed["error"])

        if "triggered" not in parsed:
            raise ValueError("脚本输出缺少 triggered 字段")

        return parsed

    async def _execute_script(
        self, info: MonitorInfo, stock_codes: list[str],
    ) -> Optional[list]:
        """调度脚本执行。

        has_stock_param=True → 逐只股票 exec 一次，聚合结果。
        has_stock_param=False → 单次 exec，无参数。
        """
        has_stock = info.script_metadata.get("has_stock_param", False)
        results: list[dict] = []

        if has_stock and stock_codes:
            for code in stock_codes:
                try:
                    parsed = await self._exec_script(info, stock_code=code)
                    if parsed:
                        parsed["stock_code"] = code
                        results.append(parsed)
                except Exception as e:
                    logger.warning(
                        "监控 %s 股票 %s 执行失败: %s",
                        info.monitor_id, code, e,
                    )
                    results.append({
                        "stock_code": code,
                        "triggered": False,
                        "message": "",
                        "error": str(e),
                    })
        elif not has_stock:
            parsed = await self._exec_script(info, stock_code=None)
            if parsed:
                results.append(parsed)

        return results if results else None

    # ── 日志 ──────────────────────────────────

    async def _log_alert(self, info: MonitorInfo, code: str, result: dict) -> None:
        from ..dependencies import repository
        from ..store.models import MonitorAlertLog

        now = datetime.now()
        log_entry = {
            "monitor_id": info.monitor_id,
            "monitor_name": info.monitor_name,
            "stock_code": code,
            "triggered": True,
            "message": result.get("message", ""),
            "data": result.get("data"),
            "timestamp": now.isoformat(),
        }

        # 写入数据库
        session = repository.SessionLocal()
        try:
            session.add(MonitorAlertLog(
                monitor_id=info.monitor_id,
                monitor_name=info.monitor_name,
                stock_code=code,
                message=result.get("message", ""),
                data=result.get("data"),
                triggered_at=now,
            ))
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("写入监控触发记录失败")
        finally:
            session.close()

        # WebSocket 广播
        dead: list[WebSocket] = []
        for ws in self._alert_subs:
            try:
                await ws.send_text(json.dumps(log_entry, ensure_ascii=False, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._alert_subs.remove(ws)

        logger.info("监控触发: [%s] %s - %s", info.monitor_name, code, result.get("message", ""))
        # 通知用户
        asyncio.create_task(self._notify_user(info, code, result.get("message", ""), is_error=False))

    async def _log_error(self, info: MonitorInfo, code: str, error_msg: str) -> None:
        """记录脚本执行错误到 monitor_alert_logs。"""
        from ..dependencies import repository
        from ..store.models import MonitorAlertLog

        now = datetime.now()
        try:
            session = repository.SessionLocal()
            try:
                session.add(MonitorAlertLog(
                    monitor_id=info.monitor_id,
                    monitor_name=info.monitor_name,
                    stock_code=code,
                    message=f"[ERROR] {error_msg}",
                    data={"error": True},
                    triggered_at=now,
                ))
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("写入监控错误记录失败")
            finally:
                session.close()
        except Exception:
            pass  # 避免日志写入失败导致连锁异常

        logger.warning("监控错误: [%s] %s - %s", info.monitor_name, code or "-", error_msg)

    async def _notify_user(
        self, info: MonitorInfo, code: str, message: str, *, is_error: bool,
    ) -> None:
        """通过 NotificationHub 向监控创建者发送站内通知。"""
        if not info.owner_id:
            return
        try:
            from ..services.notification_hub import notification_hub
            await notification_hub.notify_user(info.owner_id, {
                "type": "monitor_alert",
                "monitor_id": info.monitor_id,
                "monitor_name": info.monitor_name,
                "stock_code": code,
                "message": message,
                "is_error": is_error,
                "timestamp": datetime.now().isoformat(),
            })
        except Exception:
            pass  # 通知失败不影响主流程

    # ── WebSocket ─────────────────────────────

    def add_alert_subscriber(self, ws: WebSocket) -> None:
        self._alert_subs.append(ws)

    def remove_alert_subscriber(self, ws: WebSocket) -> None:
        if ws in self._alert_subs:
            self._alert_subs.remove(ws)

    # ── 控制接口 ──────────────────────────────

    def list_monitors(self, user: dict | None = None) -> list[dict]:
        """列出监控。传入 user 时按权限过滤（admin 全部，普通用户仅自己的）。"""
        is_admin = user and user.get("role") == "admin"
        user_id = user["user_id"] if user else None

        result = []
        for info in self._monitors.values():
            # 权限过滤：admin 看全部；非 admin 只看自己的
            if user and not is_admin and info.owner_id != user_id:
                continue
            result.append({
                "monitor_id": info.monitor_id,
                "monitor_name": info.monitor_name,
                "description": info.description,
                "stock_codes": info.stock_codes,
                "strategy_ids": info.strategy_ids,
                "interval": info.interval,
                "trigger_mode": info.trigger_mode,
                "enabled": info.enabled,
                "cooldown_seconds": info.cooldown_seconds,
                "script_metadata": info.script_metadata,
                "params": info.params,
                "owner_id": info.owner_id,
                "last_run": info.last_run,
                "last_result": info.last_result,
                "error_message": info.error_message,
            })
        return result

    def get_monitor(self, monitor_id: str) -> Optional[dict]:
        info = self._monitors.get(monitor_id)
        if not info:
            return None

        # 从 workspace 读取脚本内容
        script_content = ""
        abs_path = self._resolve_script_path(info.session_id, info.script_path)
        if abs_path is not None and abs_path.exists():
            try:
                script_content = abs_path.read_text(encoding="utf-8")
            except Exception:
                pass

        return {
            "monitor_id": info.monitor_id,
            "monitor_name": info.monitor_name,
            "description": info.description,
            "stock_codes": info.stock_codes,
            "strategy_ids": info.strategy_ids,
            "interval": info.interval,
            "trigger_mode": info.trigger_mode,
            "enabled": info.enabled,
            "cooldown_seconds": info.cooldown_seconds,
            "script_metadata": info.script_metadata,
            "params": info.params,
            "owner_id": info.owner_id,
            "last_run": info.last_run,
            "last_result": info.last_result,
            "error_message": info.error_message,
            "script_content": script_content,
        }

    async def run_now(self, monitor_id: str) -> dict:
        """手动执行（跳过冷却）"""
        info = self._monitors.get(monitor_id)
        if not info:
            return {"error": f"监控 {monitor_id} 不存在"}

        # 确保容器可用
        try:
            await self._ensure_container()
        except Exception as e:
            return {"error": f"Docker 容器不可用: {e}"}

        has_stock = info.script_metadata.get("has_stock_param", False)
        stock_codes = self._resolve_stock_codes(info) if has_stock else []

        results = []
        try:
            result = await self._execute_script(info, stock_codes)
            self._process_results(info, stock_codes, result)
            results.append({"stock_codes": stock_codes, "result": result, "error": None})
        except Exception as e:
            results.append({"stock_codes": stock_codes, "result": None, "error": str(e)})

        info.last_run = datetime.now().isoformat()
        return {"monitor_id": monitor_id, "results": results}

    def toggle(self, monitor_id: str) -> dict:
        info = self._monitors.get(monitor_id)
        if not info:
            return {"error": f"监控 {monitor_id} 不存在"}
        info.enabled = not info.enabled
        self._save_to_db(info)
        return {"monitor_id": monitor_id, "enabled": info.enabled}

    def update_monitor(self, monitor_id: str, updates: dict) -> dict:
        """全字段更新监控元数据"""
        info = self._monitors.get(monitor_id)
        if not info:
            return {"error": f"监控 {monitor_id} 不存在"}

        if "monitor_name" in updates:
            info.monitor_name = str(updates["monitor_name"])
        if "description" in updates:
            info.description = str(updates["description"])
        if "stock_codes" in updates:
            v = updates["stock_codes"]
            if isinstance(v, list):
                info.stock_codes = [str(c) for c in v]
            else:
                return {"error": "stock_codes 必须是列表"}
        if "strategy_ids" in updates:
            v = updates["strategy_ids"]
            if isinstance(v, list):
                info.strategy_ids = [str(s) for s in v]
            else:
                return {"error": "strategy_ids 必须是列表"}
        if "interval" in updates:
            if updates["interval"] in _VALID_INTERVALS:
                info.interval = updates["interval"]
            else:
                return {"error": f"无效的间隔: {updates['interval']}"}
        if "trigger_mode" in updates:
            if updates["trigger_mode"] in ("periodic", "manual"):
                info.trigger_mode = updates["trigger_mode"]
            else:
                return {"error": f"无效的 trigger_mode"}
        if "enabled" in updates:
            info.enabled = bool(updates["enabled"])
        if "cooldown_seconds" in updates:
            try:
                info.cooldown_seconds = int(updates["cooldown_seconds"])
            except (ValueError, TypeError):
                return {"error": "cooldown_seconds 必须是整数"}
        if "params" in updates and updates["params"] is not None:
            if isinstance(updates["params"], dict):
                info.params = updates["params"]
            else:
                return {"error": "params 必须是字典"}

        self._save_to_db(info)
        return {
            "monitor_id": info.monitor_id,
            "monitor_name": info.monitor_name,
            "description": info.description,
            "stock_codes": info.stock_codes,
            "strategy_ids": info.strategy_ids,
            "interval": info.interval,
            "trigger_mode": info.trigger_mode,
            "enabled": info.enabled,
            "cooldown_seconds": info.cooldown_seconds,
            "script_metadata": info.script_metadata,
            "params": info.params,
            "owner_id": info.owner_id,
        }

    def delete_monitor(self, monitor_id: str) -> dict:
        info = self._monitors.get(monitor_id)
        if not info:
            return {"error": f"监控 {monitor_id} 不存在"}

        try:
            # 只删 DB 记录（脚本保留在 agent workspace，由 workspace 生命周期管理）
            from ..dependencies import repository
            from ..store.models import MonitorRecord

            session = repository.SessionLocal()
            try:
                session.query(MonitorRecord).filter_by(monitor_id=monitor_id).delete()
                session.commit()
            except Exception:
                session.rollback()
                logger.warning("删除监控 DB 记录失败: %s", monitor_id)
            finally:
                session.close()

            del self._monitors[monitor_id]
            # 清理冷却记录
            keys_to_remove = [k for k in self._last_trigger if k[0] == monitor_id]
            for k in keys_to_remove:
                del self._last_trigger[k]
            logger.info("监控已删除: %s", monitor_id)
            return {"monitor_id": monitor_id, "deleted": True}
        except Exception as e:
            return {"error": f"删除失败: {e}"}


# ── 股票搜索 ──────────────────────────────────

_stock_basic_cache: Optional[list[dict]] = None
_stock_basic_mtime: float = 0


def search_stocks(query: str, limit: int = 20) -> list[dict]:
    """从 C:/klines/stock_basic.csv 搜索股票（支持名称/代码/拼音）"""
    import csv
    global _stock_basic_cache, _stock_basic_mtime

    csv_path = Path("C:/klines/stock_basic.csv")
    if not csv_path.exists():
        return []

    # 缓存：文件修改时间变化时重新加载
    mtime = csv_path.stat().st_mtime
    if _stock_basic_cache is None or mtime != _stock_basic_mtime:
        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                _stock_basic_cache = [
                    {
                        "ts_code": row.get("ts_code", ""),
                        "symbol": row.get("symbol", ""),
                        "name": row.get("name", ""),
                        "cnspell": row.get("cnspell", ""),
                        "industry": row.get("industry", ""),
                    }
                    for row in reader
                    if row.get("list_status", "L") == "L"  # 仅上市中
                ]
            _stock_basic_mtime = mtime
        except Exception:
            return []

    if not _stock_basic_cache:
        return []

    q = query.strip().lower()
    if not q:
        return _stock_basic_cache[:limit]

    results = []
    for s in _stock_basic_cache:
        if (q in s["ts_code"].lower()
                or q in s["symbol"]
                or q in s["name"]
                or q in s["cnspell"].lower()):
            results.append(s)
            if len(results) >= limit:
                break

    return results


def get_stock_info(ts_code: str) -> dict | None:
    """根据 ts_code 精确查找股票信息，不存在返回 None。"""
    # 先确保缓存已加载
    results = search_stocks(ts_code, limit=5000)
    for s in results:
        if s["ts_code"] == ts_code:
            return s
    return None


def _user_has_monitor_permission(user_id: int) -> bool:
    """检查用户是否仍有监控任务权限（admin 始终通过）"""
    try:
        from ..auth.models import User
        from ..dependencies import repository
        session = repository.SessionLocal()
        try:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return False
            if user.role == "admin":
                return True
            return bool(user.can_use_monitor) if user.can_use_monitor is not None else True
        finally:
            session.close()
    except Exception:
        logger.exception("Failed to check monitor permission for user %d", user_id)
        return True  # 查询失败时允许执行，避免误杀
