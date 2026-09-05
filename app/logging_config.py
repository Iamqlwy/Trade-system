"""
量化交易系统 - 日志配置

功能：
1. 按模块分文件输出（engine / market / store / api / agent / monitor）
2. 终端仅 WARNING+，文件 INFO+
3. 时间 + 大小双重轮换（20MB 上限，按日归档）
4. JSON 结构化日志（文件） + 人类可读格式（终端）
5. 独立审计日志（audit.log）+ 独立错误日志（errors.log）
6. 请求关联 ID 自动注入（request_id / order_id / strategy_id）

日志文件布局：
  logs/
  ├── engine.log       # 交易引擎 — 撮合/成交/撤单
  ├── market.log       # 行情数据 — 拉取/tick 解析
  ├── store.log        # 数据持久化 — DB 读写
  ├── api.log          # API 请求 — HTTP/WebSocket
  ├── agent.log        # Agent 调度 — 定时任务/LLM/工具
  ├── monitor.log      # 监控引擎 — 监控调度/触发
  ├── app.log          # 汇总日志（含以上所有模块）
  ├── audit.log        # 审计日志（JSON）
  ├── errors.log       # 错误汇总（人类可读，ERROR+）
  └── *.log.YYYY-MM-DD # 历史轮换文件
"""

import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path


# ── 日志目录 ────────────────────────────────────

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


# ── 模块 → 日志文件映射 ──────────────────────────
#
# 每个顶层模块 logger 挂载独立的 file handler，propagate=True：
#   模块日志 → 专属文件 + app.log（汇总）+ 终端（WARNING+）
#
_MODULE_SPECS: dict[str, dict[str, str]] = {
    "app.engine":  {"file": "engine",  "desc": "交易引擎"},
    "app.market":  {"file": "market",  "desc": "行情数据"},
    "app.store":   {"file": "store",   "desc": "数据持久化"},
    "app.api":     {"file": "api",     "desc": "API 请求"},
    "app.agent":   {"file": "agent",   "desc": "Agent 调度"},
    "app.monitor": {"file": "monitor", "desc": "监控引擎"},
}


# ── 自定义 Handler ──────────────────────────────

class SizeAwareTimedRotatingHandler(logging.handlers.TimedRotatingFileHandler):
    """
    Windows 安全的时间 + 大小双重轮换处理器。

    为什么用 TimedRotatingFileHandler 而非 RotatingFileHandler：
    - Windows 上文件被其他进程持有句柄时重命名会失败
    - TimedRotatingFileHandler 在轮换时先关闭旧文件再重命名，更可靠
    - 额外添加大小检查：每次 emit 前检查文件是否超过 maxBytes
    """

    def __init__(
        self,
        filename,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
        max_bytes=20 * 1024 * 1024,
    ):
        super().__init__(
            filename=filename,
            when=when,
            interval=interval,
            backupCount=backupCount,
            encoding=encoding,
            delay=True,
            utc=False,
        )
        self.max_bytes = max_bytes

    def shouldRollover(self, record):
        # 先检查父类的时间条件
        result = super().shouldRollover(record)
        if result:
            return result
        # 再检查大小
        if self.max_bytes and self.max_bytes > 0:
            msg = self.format(record) + self.terminator
            try:
                size = os.path.getsize(self.baseFilename)
            except OSError:
                size = 0
            if size + len(msg.encode("utf-8")) > self.max_bytes:
                return 1
        return 0


# ── 自定义 Formatter ────────────────────────────

class JSONFormatter(logging.Formatter):
    """
    JSON 结构化日志格式化器。

    输出字段：timestamp, level, logger, message, module, function, line
    可选字段：request_id, order_id, strategy_id, exception, extra_data
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 关联 ID（由 CorrelationFilter 注入）
        request_id = getattr(record, "request_id", "")
        order_id = getattr(record, "order_id", "")
        strategy_id = getattr(record, "strategy_id", "")
        if request_id:
            log_data["request_id"] = request_id
        if order_id:
            log_data["order_id"] = order_id
        if strategy_id:
            log_data["strategy_id"] = strategy_id

        # 异常信息
        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = self.formatException(record.exc_info)

        # 额外数据（审计日志通过 extra={"extra_data": {...}} 传入）
        extra_data = getattr(record, "extra_data", None)
        if extra_data and isinstance(extra_data, dict):
            log_data.update(extra_data)

        return json.dumps(log_data, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """
    控制台格式化器 — 人类可读，带请求关联信息。
    """

    def format(self, record: logging.LogRecord) -> str:
        # 构建关联前缀
        parts = []
        request_id = getattr(record, "request_id", "")
        order_id = getattr(record, "order_id", "")
        if request_id:
            parts.append(f"rid={request_id}")
        if order_id:
            parts.append(f"oid={order_id}")

        prefix = f"[{', '.join(parts)}] " if parts else ""

        base = super().format(record)
        # 在 message 前插入关联信息
        # 原始格式: [asctime] [levelname] name: message
        # 目标格式: [asctime] [levelname] [rid=xxx, oid=yyy] name: message
        return base.replace(
            f"{record.name}: ",
            f"{prefix}{record.name}: ",
            1,
        ) if prefix else base


# ── 主配置函数 ──────────────────────────────────

def setup_logging(level: str = "INFO") -> None:
    """
    初始化完整日志系统。

    终端仅显示 WARNING 及以上，文件记录 INFO 及以上。
    六个核心模块各自输出到独立日志文件。

    Args:
        level: 根日志级别（INFO / DEBUG / WARNING / ERROR）
    """
    from .config import settings

    file_level = getattr(logging, level.upper(), logging.INFO)
    console_level = logging.WARNING  # 终端只显示 WARNING+
    LOG_DIR.mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(file_level)

    # 清除所有 logger 的旧 handler（uvicorn reload 时会重复添加）
    # 不仅清除 root，还要清除模块级 logger 的 handler
    for logger_obj in logging.Logger.manager.loggerDict.values():
        if isinstance(logger_obj, logging.Logger):
            logger_obj.handlers.clear()
            logger_obj.filters.clear()
    root.handlers.clear()

    # 关联过滤器（所有 handler 共享）
    from .logutils.correlation import CorrelationFilter
    correlation_filter = CorrelationFilter()

    # ── 1. 控制台 Handler（人类可读，WARNING+） ──
    console_fmt = ConsoleFormatter(
        fmt="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_fmt)
    console_handler.addFilter(correlation_filter)
    root.addHandler(console_handler)

    # ── 2. 模块文件 Handler（JSON，INFO+） ──────
    max_file_bytes = getattr(settings, "log_max_file_mb", 20) * 1024 * 1024
    backup_days = getattr(settings, "log_backup_days", 30)
    json_formatter = JSONFormatter()

    for logger_name, spec in _MODULE_SPECS.items():
        file_name = spec["file"]
        handler = SizeAwareTimedRotatingHandler(
            filename=str(LOG_DIR / f"{file_name}.log"),
            when="D",
            interval=1,
            backupCount=backup_days,
            max_bytes=max_file_bytes,
        )
        handler.setFormatter(json_formatter)
        handler.addFilter(correlation_filter)

        mod_logger = logging.getLogger(logger_name)
        mod_logger.addHandler(handler)
        # propagate=True（默认）：模块日志同时到达 root 的 console + app.log

    # ── 3. 汇总日志文件 Handler（JSON，INFO+） ──
    rotation_hours = getattr(settings, "log_rotation_hours", 24)
    backup_count = max(backup_days, backup_days * (24 // max(rotation_hours, 1)))

    app_handler = SizeAwareTimedRotatingHandler(
        filename=str(LOG_DIR / "app.log"),
        when="H",
        interval=rotation_hours,
        backupCount=backup_count,
        max_bytes=max_file_bytes,
    )
    app_handler.setFormatter(json_formatter)
    app_handler.addFilter(correlation_filter)
    root.addHandler(app_handler)

    # ── 4. 错误日志文件 Handler（ERROR+，人类可读） ──
    error_handler = SizeAwareTimedRotatingHandler(
        filename=str(LOG_DIR / "errors.log"),
        when="D",
        interval=1,
        backupCount=30,
        max_bytes=max_file_bytes,
    )
    error_handler.setLevel(logging.ERROR)
    error_fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s (%(module)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    error_handler.setFormatter(error_fmt)
    error_handler.addFilter(correlation_filter)
    root.addHandler(error_handler)

    # ── 5. 审计日志 Handler（独立文件，JSON） ──
    audit_enabled = getattr(settings, "log_audit_enabled", True)
    if audit_enabled:
        audit_handler = SizeAwareTimedRotatingHandler(
            filename=str(LOG_DIR / "audit.log"),
            when="D",
            interval=1,
            backupCount=90,  # 审计日志保留更久
            max_bytes=max_file_bytes,
        )
        audit_handler.setFormatter(json_formatter)
        audit_handler.addFilter(correlation_filter)

        audit_logger = logging.getLogger("audit")
        audit_logger.setLevel(logging.INFO)
        audit_logger.addHandler(audit_handler)
        audit_logger.propagate = False  # 不传播到根日志器

    # ── 6. 第三方库静音 ──────────────────────────
    # 抑制 SQLAlchemy 引擎日志（太吵）
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    # 抑制 uvicorn 访问日志（与我们的 API 日志重复）
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    root.info(
        "日志系统初始化完成: level=%s, rotation=%dh, backup=%dd, max_file=%dMB, audit=%s",
        level.upper(), rotation_hours, backup_days,
        max_file_bytes // (1024 * 1024),
        audit_enabled,
    )
    root.info(
        "模块日志: %s",
        ", ".join(f"{spec["desc"]}({spec["file"]}.log)" for spec in _MODULE_SPECS.values()),
    )
    root.info("终端级别: WARNING+, 文件级别: %s+", level.upper())


def get_module_logger(module_name: str) -> logging.Logger:
    """
    获取模块专用 logger（便捷函数）。

    等价于 logging.getLogger(module_name)，模块 handler 已由 setup_logging 配置。

    Usage:
        from app.logging_config import get_module_logger
        logger = get_module_logger("app.engine.real_executor")
    """
    return logging.getLogger(module_name)