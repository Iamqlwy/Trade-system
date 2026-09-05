"""
量化交易系统 - 配置管理

⚠️ db_url 使用 urllib.parse.quote_plus 对用户名/密码做 URL 编码，
  避免密码含 @ : / % 等特殊字符导致数据库连接串解析失败。
"""
import urllib.parse
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "winwin"

    # 服务
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # CORS（跨域白名单）
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "https://happywin.top",
        "https://www.happywin.top",
    ]

    # 日志
    log_level: str = "INFO"
    log_rotation_hours: int = 24       # 日志轮换间隔（小时）
    log_backup_days: int = 30          # 日志保留天数
    log_max_file_mb: int = 20          # 单文件上限（MB）
    log_audit_enabled: bool = True     # 是否启用审计日志

    # 行情
    tick_fetch_interval: float = 3.0  # 行情拉取间隔（秒）

    # 持久化
    store_interval: float = 60.0      # 自动保存间隔（秒）

    # Docker 沙箱（Agent Shell 工具 — 强制性，不可关闭）
    shell_sandbox_image: str = "quant-sandbox:latest"   # 沙箱镜像（预装 Python 3.13 + 量化库）
    # 网络隔离已硬编码强制开启（block_network=True），不可通过配置关闭，防止反弹 Shell
    shell_sandbox_max_memory_mb: int = 512          # 内存上限（MB）
    shell_sandbox_max_cpus: float = 1.0             # CPU 核心数上限
    shell_sandbox_max_pids: int = 128               # 进程数上限

    # xtquant
    xtaccount: str = ""               # 券商资金账号
    xtdata_path: str = ""             # xtquant data 目录
    xttrader_path: str = ""           # xtquant 交易端 userdata 目录（如 C:\申万宏源策略量化交易终端\userdata_mini）

    # LLM (Agent)
    llm_api_key: str = ""
    llm_base_url: str = "http://ev94rsohg01.copilot.rds.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen3.6-plus"
    llm_small_model: str = "qwen3-flash"   # 标题生成等轻量任务用的小模型
    llm_api_mode: str = "chat"        # "chat" | "anthropic"

    # OSS (阿里云对象存储 — 用于图片上传)
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_region: str = "cn-beijing"
    oss_endpoint: str = ""            # e.g. "https://oss-cn-beijing.aliyuncs.com"
    oss_bucket: str = ""
    oss_base_url: str = ""            # 公网 URL 前缀, e.g. "https://xxx.oss-cn-beijing.aliyuncs.com"

    # 知识库 (PostgreSQL - Docker pgbouncer)
    kb_db_host: str = "127.0.0.1"
    kb_db_port: int = 6432
    kb_db_user: str = "postgres"
    kb_db_password: str = "postgres"
    kb_db_name: str = "quant_kb"

    # Elasticsearch
    es_url: str = "http://127.0.0.1:9200"

    # Embedding (SiliconFlow)
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "Qwen/Qwen3-Embedding-4B"
    embedding_dimension: int = 1536

    @property
    def embedding_enabled(self) -> bool:
        return bool(self.embedding_api_key)

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "allow"}

    @property
    def oss_enabled(self) -> bool:
        """OSS 是否已配置（所有必填字段非空）"""
        return bool(
            self.oss_access_key_id
            and self.oss_access_key_secret
            and self.oss_bucket
            and self.oss_endpoint
            and self.oss_base_url
        )

    @property
    def db_url(self) -> str:
        u = urllib.parse.quote_plus(self.db_user)
        p = urllib.parse.quote_plus(self.db_password)
        return f"mysql+pymysql://{u}:{p}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def kb_db_url(self) -> str:
        """知识库 PostgreSQL 同步连接 URL（psycopg2）"""
        u = urllib.parse.quote_plus(self.kb_db_user)
        p = urllib.parse.quote_plus(self.kb_db_password)
        return f"postgresql+psycopg2://{u}:{p}@{self.kb_db_host}:{self.kb_db_port}/{self.kb_db_name}"


settings = Settings()
