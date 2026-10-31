from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    db_path: Path
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_fallback_provider: str
    llm_fallback_base_url: str
    llm_fallback_api_key: str
    llm_fallback_model: str
    errorjiang_base_url: str
    errorjiang_token: str
    admin_qqs: frozenset[int]
    bind_code: str
    admin_user_id: int
    onebot_api_base: str
    onebot_ws_url: str
    onebot_access_token: str
    onebot_webhook_secret: str
    qqbot_enabled: bool
    qqbot_app_id: str
    qqbot_app_secret: str
    qqbot_bot_qq: str
    qqbot_admin_openids: frozenset[str]
    qqbot_group_ids: frozenset[str]
    qqbot_auto_bind_first_admin: bool
    group_enabled: bool
    group_ids: frozenset[int]
    context_messages: int
    context_char_limit: int
    max_tool_rounds: int

    @classmethod
    def load(cls, base_dir: Path | None = None) -> "Config":
        root = base_dir or Path(__file__).resolve().parent
        load_env_file(root / ".env")
        qq_values = set()
        for item in os.environ.get("ERRORJIANG_AGENT_ADMIN_QQS", "").split(","):
            item = item.strip()
            if item.isdigit():
                qq_values.add(int(item))
        group_values = set()
        for item in os.environ.get("ERRORJIANG_AGENT_GROUP_IDS", "").split(","):
            item = item.strip()
            if item.isdigit():
                group_values.add(int(item))
        qqbot_group_values = {
            item.strip()
            for item in os.environ.get("QQBOT_GROUP_IDS", "").split(",")
            if item.strip()
        }
        qqbot_admin_values = {
            item.strip()
            for item in os.environ.get("QQBOT_ADMIN_OPENIDS", "").split(",")
            if item.strip()
        }
        secret = os.environ.get("ONEBOT_WEBHOOK_SECRET", "").strip()
        if not secret:
            secret = os.environ.get("ERRORJIANG_AGENT_TOKEN", "").strip()
        deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        deepseek_base_url = os.environ.get(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        ).rstrip("/")
        deepseek_model = os.environ.get(
            "DEEPSEEK_MODEL", "deepseek-chat"
        ).strip()
        llm_provider = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
        llm_base_url = os.environ.get("LLM_BASE_URL", "").strip().rstrip("/")
        if not llm_base_url:
            llm_base_url = deepseek_base_url
        llm_api_key = os.environ.get("LLM_API_KEY", "").strip()
        if not llm_api_key:
            llm_api_key = deepseek_api_key
        llm_model = os.environ.get("LLM_MODEL", "").strip()
        if not llm_model:
            llm_model = deepseek_model
        llm_fallback_provider = (
            os.environ.get("LLM_FALLBACK_PROVIDER", "").strip().lower()
        )
        return cls(
            host=os.environ.get("ERRORJIANG_AGENT_HOST", "127.0.0.1").strip(),
            port=env_int("ERRORJIANG_AGENT_PORT", 8011),
            db_path=Path(
                os.environ.get(
                    "ERRORJIANG_AGENT_DB",
                    str(root / "data" / "agent.db"),
                )
            ),
            deepseek_api_key=deepseek_api_key,
            deepseek_base_url=deepseek_base_url,
            deepseek_model=deepseek_model,
            llm_provider=llm_provider,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_fallback_provider=llm_fallback_provider,
            llm_fallback_base_url=os.environ.get(
                "LLM_FALLBACK_BASE_URL", ""
            ).strip().rstrip("/"),
            llm_fallback_api_key=os.environ.get(
                "LLM_FALLBACK_API_KEY", ""
            ).strip(),
            llm_fallback_model=os.environ.get(
                "LLM_FALLBACK_MODEL", ""
            ).strip(),
            errorjiang_base_url=os.environ.get(
                "ERRORJIANG_BASE_URL", "http://127.0.0.1:8000"
            ).rstrip("/"),
            errorjiang_token=os.environ.get(
                "ERRORJIANG_AGENT_TOKEN", ""
            ).strip(),
            admin_qqs=frozenset(qq_values),
            bind_code=os.environ.get("ERRORJIANG_AGENT_BIND_CODE", "").strip(),
            admin_user_id=env_int("ERRORJIANG_AGENT_ADMIN_USER_ID", 0),
            onebot_api_base=os.environ.get(
                "ONEBOT_API_BASE", "http://127.0.0.1:3000"
            ).rstrip("/"),
            onebot_ws_url=os.environ.get(
                "ONEBOT_WS_URL", "ws://127.0.0.1:3001"
            ).strip(),
            onebot_access_token=os.environ.get(
                "ONEBOT_ACCESS_TOKEN", ""
            ).strip(),
            onebot_webhook_secret=secret,
            qqbot_enabled=env_bool("QQBOT_ENABLED", False),
            qqbot_app_id=os.environ.get("QQBOT_APP_ID", "").strip(),
            qqbot_app_secret=os.environ.get("QQBOT_APP_SECRET", "").strip(),
            qqbot_bot_qq=os.environ.get("QQBOT_BOT_QQ", "").strip(),
            qqbot_admin_openids=frozenset(qqbot_admin_values),
            qqbot_group_ids=frozenset(qqbot_group_values),
            qqbot_auto_bind_first_admin=env_bool(
                "QQBOT_AUTO_BIND_FIRST_ADMIN", False
            ),
            group_enabled=env_bool("ERRORJIANG_AGENT_GROUP_ENABLED", False),
            group_ids=frozenset(group_values),
            context_messages=max(
                2, min(env_int("ERRORJIANG_AGENT_CONTEXT_MESSAGES", 8), 20)
            ),
            context_char_limit=max(
                4000,
                min(
                    env_int("ERRORJIANG_AGENT_CONTEXT_CHAR_LIMIT", 16000),
                    100000,
                ),
            ),
            max_tool_rounds=max(
                1, min(env_int("ERRORJIANG_AGENT_MAX_TOOL_ROUNDS", 4), 8)
            ),
        )

    def validate(self) -> None:
        missing = []
        if not self.llm_api_key and not self.deepseek_api_key:
            missing.append("LLM_API_KEY/DEEPSEEK_API_KEY")
        if not self.llm_base_url:
            missing.append("LLM_BASE_URL")
        if not self.llm_model:
            missing.append("LLM_MODEL")
        if self.llm_fallback_provider:
            if not self.llm_fallback_base_url:
                missing.append("LLM_FALLBACK_BASE_URL")
            if not self.llm_fallback_api_key:
                missing.append("LLM_FALLBACK_API_KEY")
            if not self.llm_fallback_model:
                missing.append("LLM_FALLBACK_MODEL")
        if not self.errorjiang_token:
            missing.append("ERRORJIANG_AGENT_TOKEN")
        if not self.admin_qqs and not self.bind_code:
            missing.append("ERRORJIANG_AGENT_ADMIN_QQS/ERRORJIANG_AGENT_BIND_CODE")
        if not self.onebot_webhook_secret:
            missing.append("ONEBOT_WEBHOOK_SECRET")
        if self.qqbot_enabled:
            if not self.qqbot_app_id:
                missing.append("QQBOT_APP_ID")
            if not self.qqbot_app_secret:
                missing.append("QQBOT_APP_SECRET")
        if self.group_enabled and not self.group_ids:
            missing.append("ERRORJIANG_AGENT_GROUP_IDS")
        if missing:
            raise ValueError("缺少配置：" + ", ".join(missing))
