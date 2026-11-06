from __future__ import annotations

import re
from typing import Any


SENSITIVE_MEMORY_RE = re.compile(
    r"(?:密码|口令|pass(?:word)?|token|api[\s_-]*key|secret|密钥|验证码)"
    r"\s*(?:是|为|[:：=])\s*\S+",
    re.IGNORECASE,
)
EXPLICIT_MEMORY_RE = re.compile(
    r"^\s*(?:请|帮我|麻烦)?\s*(?:记住|记一下|别忘了|不要忘记)"
    r"(?:一下|这个|这件事|我说的话)?\s*[：:,，]?\s*(?P<content>.+?)\s*$",
    re.IGNORECASE,
)
STABLE_MEMORY_RE = re.compile(
    r"(?:"
    r"我(?:更|最)?(?:喜欢|讨厌|不喜欢|习惯|偏好|害怕|不吃|过敏|希望)"
    r"|我的(?:生日|名字|称呼|城市|工作|习惯|偏好|忌口)"
    r"|(?:以后|每次)(?:都|不要|别|请|叫我)"
    r"|叫我.{1,30}"
    r"|我们(?:约定|说好|答应)"
    r"|(?:答应我|记住|别忘了|不要忘记|记一下)"
    r"|(?:明天|后天|周[一二三四五六日天]|下周|周末|月底|"
    r"\d{1,2}月\d{1,2}日)"
    r".{0,30}(?:要|准备|一起|约|提醒|别忘)"
    r"|(?:不能忘|很重要|长期项目|长期计划)"
    r")",
    re.IGNORECASE,
)


def extract_explicit_memory(text: str) -> dict[str, Any] | None:
    value = " ".join(str(text or "").split()).strip()
    match = EXPLICIT_MEMORY_RE.match(value)
    if not match:
        return None
    content = match.group("content").strip(" ：:,，")
    if (
        len(content) < 4
        or len(content) > 500
        or SENSITIVE_MEMORY_RE.search(content)
    ):
        return None
    if re.search(r"(?:喜欢|讨厌|不喜欢|偏好|习惯|过敏|忌口)", content):
        kind = "preference"
    elif re.search(r"(?:不要|不可以|别提|别叫|不准|边界)", content):
        kind = "boundary"
    elif re.search(r"(?:约定|答应|以后|下次|计划)", content):
        kind = "promise"
    elif re.search(r"(?:生日|纪念日|日期|月底|下周|明天|后天)", content):
        kind = "event"
    else:
        kind = "fact"
    return {
        "content": content,
        "kind": kind,
        "importance": 8,
        "confidence": 9,
    }


def should_extract_memory_now(
    user_text: str,
    assistant_text: str = "",
) -> tuple[bool, str]:
    del assistant_text
    value = " ".join(str(user_text or "").split()).strip()
    if len(value) < 6:
        return False, "too_short"
    if SENSITIVE_MEMORY_RE.search(value):
        return False, "sensitive"
    if extract_explicit_memory(value):
        return False, "handled_explicitly"
    match = STABLE_MEMORY_RE.search(value)
    if not match:
        return False, "not_stable"
    return True, match.group(0)[:80]
