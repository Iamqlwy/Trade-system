"""统一配置管理 — 从 .env 和 config.json 加载所有设置"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, SecretStr


# ---------------------------------------------------------------------------
# Agent Home
# ---------------------------------------------------------------------------

def get_agent_home() -> Path:
    """返回 Agent 主目录，优先读 AGENT_HOME 环境变量，默认 ~/.unified-agent"""
    if env_home := os.getenv("AGENT_HOME"):
        return Path(env_home).expanduser().resolve()
    # 兼容旧路径
    for legacy_env in ("SIMPLE_AGENT_HOME",):
        if legacy := os.getenv(legacy_env):
            return Path(legacy).expanduser().resolve()
    return Path.home() / ".unified-agent"


def ensure_dirs(home: Optional[Path] = None) -> Path:
    """创建 Agent 主目录及子目录"""
    if home is None:
        home = get_agent_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "sessions").mkdir(exist_ok=True)
    (home / "skills").mkdir(exist_ok=True)
    (home / "skills" / "users").mkdir(parents=True, exist_ok=True)
    (home / "workspaces").mkdir(exist_ok=True)
    (home / "cron").mkdir(exist_ok=True)
    return home


# ---------------------------------------------------------------------------
# .env 加载
# ---------------------------------------------------------------------------

def load_env(home: Optional[Path] = None) -> dict[str, str]:
    """从 Agent 主目录加载 .env 文件到 os.environ"""
    if home is None:
        home = get_agent_home()
    env_path = home / ".env"
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                result[key] = value
                os.environ.setdefault(key, value)
    return result


# ---------------------------------------------------------------------------
# LLM 配置模型
# ---------------------------------------------------------------------------

class LLMProvider(BaseModel):
    """LLM 提供商配置"""
    type: str = "openai"  # "openai" | "anthropic"
    base_url: str = ""
    api_key: SecretStr = SecretStr("")


class LLMModel(BaseModel):
    """模型配置"""
    provider: str = "openai"
    model: str = "qwen3.6-plus"
    max_context_size: int = 128_000


class LoopControl(BaseModel):
    """Agent 循环控制参数"""
    max_steps_per_turn: int = Field(default=1000, ge=1)
    max_retries_per_step: int = Field(default=3, ge=1)
    reserved_context_size: int = Field(default=50_000, ge=1_000)
    compaction_trigger_ratio: float = Field(default=0.85, ge=0.5, le=0.99)


class Config(BaseModel):
    """完整配置"""
    default_model: str = Field(default="", description="默认模型别名")
    models: dict[str, LLMModel] = Field(default_factory=dict)
    providers: dict[str, LLMProvider] = Field(default_factory=dict)
    loop_control: LoopControl = Field(default_factory=LoopControl)
    theme: str = "dark"
    default_editor: str = ""


# ---------------------------------------------------------------------------
# 配置加载 / 保存
# ---------------------------------------------------------------------------

def load_config(config_path: Optional[Path] = None) -> Config:
    """加载 config.json（或 config.yaml），不存在则返回默认配置"""
    home = get_agent_home()

    if config_path is None:
        config_path = home / "config.json"

    if config_path.exists():
        suffix = config_path.suffix.lower()
        with open(config_path, encoding="utf-8") as f:
            if suffix in (".yaml", ".yml"):
                data = yaml.safe_load(f) or {}
            elif suffix in (".toml", ".tml"):
                import tomllib
                data = tomllib.loads(f.read())
            else:
                data = json.load(f)
        return Config.model_validate(data)

    return Config()


def save_config(config: Config, config_path: Optional[Path] = None) -> None:
    """保存配置到 JSON 文件"""
    if config_path is None:
        config_path = get_agent_home() / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config.model_dump(mode="json", exclude_none=True), f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 模型解析（从环境变量 + 配置文件）
# ---------------------------------------------------------------------------

def get_model_config(
    home: Optional[Path] = None,  # noqa: ARG001
    config: Optional[Config] = None,  # noqa: ARG001
) -> dict[str, Any]:
    """解析模型配置。优先级：环境变量 > 配置文件 > 默认值"""
    env = dict(os.environ)

    base_url = (
        env.get("LLM_BASE_URL")
        or env.get("OPENAI_BASE_URL")
        or ""
    )
    api_key = (
        env.get("LLM_API_KEY")
        or env.get("OPENAI_API_KEY")
        or ""
    )
    model = (
        env.get("LLM_MODEL")
        or env.get("OPENAI_MODEL")
        or "qwen3.6-plus"
    )
    api_mode = env.get("LLM_API_MODE", "chat")  # "chat" | "anthropic"

    return {
        "api_mode": api_mode,
        "base_url": base_url,
        "api_key": api_key,
        "model": model,
        "max_iterations": int(env.get("MAX_ITERATIONS", "50")),
    }


def resolve_model(
    config: Config,
    model_name: Optional[str] = None,
) -> tuple[LLMModel, LLMProvider]:
    """从 Config 对象解析模型和提供商"""
    model: LLMModel | None = None
    provider: LLMProvider | None = None

    if not model_name and config.default_model:
        model = config.models.get(config.default_model)
        if model:
            provider = config.providers.get(model.provider)

    if model_name and model_name in config.models:
        model = config.models[model_name]
        provider = config.providers.get(model.provider)

    if model is None:
        model = LLMModel(
            provider="openai",
            model=os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", "qwen3.6-plus"),
            max_context_size=int(os.getenv("OPENAI_MAX_CONTEXT_SIZE", "128000")),
        )

    if provider is None:
        provider = LLMProvider(
            type="openai",
            base_url=os.getenv("LLM_BASE_URL", ""),
            api_key=SecretStr(os.getenv("LLM_API_KEY", "")),
        )

    return model, provider


# ---------------------------------------------------------------------------
# 目录快捷方法
# ---------------------------------------------------------------------------

def get_skills_dir(home: Optional[Path] = None) -> Path:
    """官方（全局）技能目录，保持向后兼容。"""
    if home is None:
        home = get_agent_home()
    return home / "skills"


def get_official_skills_dir(home: Optional[Path] = None) -> Path:
    """官方（全局）技能目录 — 系统内置技能存放位置。"""
    if home is None:
        home = get_agent_home()
    return home / "skills"


def get_user_skills_dir(user_id: int, home: Optional[Path] = None) -> Path:
    """用户级技能目录 — 每个用户有独立的 skills 空间。

    路径: {agent_home}/skills/users/{user_id}/
    """
    if home is None:
        home = get_agent_home()
    return home / "skills" / "users" / str(user_id)


def get_cron_dir(home: Optional[Path] = None) -> Path:
    if home is None:
        home = get_agent_home()
    return home / "cron"


def get_sessions_dir(home: Optional[Path] = None) -> Path:
    if home is None:
        home = get_agent_home()
    return home / "sessions"


def get_workspaces_dir(home: Optional[Path] = None) -> Path:
    """工作区根目录。"""
    if home is None:
        home = get_agent_home()
    return home / "workspaces"


def get_workspace_dir(session_or_run_id: str, home: Optional[Path] = None) -> Path:
    """获取指定 session 或 cron run 的独立工作区。

    路径: {agent_home}/workspaces/{session_or_run_id}/
    交互式 agent 用 session_id，cron 用 run_id。
    """
    return get_workspaces_dir(home) / session_or_run_id


# ---------------------------------------------------------------------------
# 从主应用 Settings 读取配置（Web 模式）
# ---------------------------------------------------------------------------

def get_model_config_from_settings(settings: Any) -> dict[str, Any]:
    """从主应用的 Settings 对象读取 LLM 配置。

    当 agent 在 Web 模式下运行时（通过 agent_manager），
    使用此函数代替 get_model_config() 以保持配置统一。

    Args:
        settings: app.config.Settings 实例
    """
    return {
        "api_mode": getattr(settings, "llm_api_mode", "chat"),
        "base_url": getattr(settings, "llm_base_url", ""),
        "api_key": getattr(settings, "llm_api_key", ""),
        "model": getattr(settings, "llm_model", "qwen3.6-plus"),
        "max_iterations": 50,
    }
