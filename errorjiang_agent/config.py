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
    errorjiang_base_url: str
    errorjiang_token: str
    admin_qqs: frozenset[int]
    bind_code: str
    admin_user_id: int
    onebot_api_base: str
    onebot_access_token: str
    onebot_webhook_secret: str
    group_enabled: bool
    context_messages: int
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
        secret = os.environ.get("ONEBOT_WEBHOOK_SECRET", "").strip()
        if not secret:
            secret = os.environ.get("ERRORJIANG_AGENT_TOKEN", "").strip()
        return cls(
            host=os.environ.get("ERRORJIANG_AGENT_HOST", "127.0.0.1").strip(),
            port=env_int("ERRORJIANG_AGENT_PORT", 8011),
            db_path=Path(
                os.environ.get(
                    "ERRORJIANG_AGENT_DB",
                    str(root / "data" / "agent.db"),
                )
            ),
            deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", "").strip(),
            deepseek_base_url=os.environ.get(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ).rstrip("/"),
            deepseek_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip(),
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
            onebot_access_token=os.environ.get(
                "ONEBOT_ACCESS_TOKEN", ""
            ).strip(),
            onebot_webhook_secret=secret,
            group_enabled=env_bool("ERRORJIANG_AGENT_GROUP_ENABLED", False),
            context_messages=max(
                2, min(env_int("ERRORJIANG_AGENT_CONTEXT_MESSAGES", 8), 20)
            ),
            max_tool_rounds=max(
                1, min(env_int("ERRORJIANG_AGENT_MAX_TOOL_ROUNDS", 4), 8)
            ),
        )

    def validate(self) -> None:
        missing = []
        if not self.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY")
        if not self.errorjiang_token:
            missing.append("ERRORJIANG_AGENT_TOKEN")
        if not self.admin_qqs and not self.bind_code:
            missing.append("ERRORJIANG_AGENT_ADMIN_QQS/ERRORJIANG_AGENT_BIND_CODE")
        if not self.onebot_webhook_secret:
            missing.append("ONEBOT_WEBHOOK_SECRET")
        if missing:
            raise ValueError("缺少配置：" + ", ".join(missing))
