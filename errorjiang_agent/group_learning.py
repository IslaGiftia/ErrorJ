from __future__ import annotations

import re
from typing import Any


URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
CQ_RE = re.compile(r"\[CQ:[^\]]+\]")
CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,40}")
LATIN_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9_+-]{1,19}(?![A-Za-z0-9])"
)
SENSITIVE_RE = re.compile(
    r"(?:密码|口令|验证码|身份证|银行卡|手机号|密钥|令牌|token|api[_ -]?key)",
    re.IGNORECASE,
)

COMMON_TERMS = frozenset(
    """
    这个 那个 什么 怎么 为什么 可以 不能 没有 就是 不是 我们 你们 他们
    她们 大家 现在 今天 明天 昨天 时候 真的 感觉 一下 有点 还是 也是
    但是 然后 因为 所以 如果 已经 可能 应该 知道 觉得 东西 事情 问题
    地方 这里 那里 哪个 哪里 怎么办 有没有 有人 可以吗 是吗 对吧 好的
    收到 谢谢 哈哈 哈哈哈 笑死 真的假的 不是吧 我的天 太了 太啦 一个
    一些 这种 那种 其实 只是 还有 而且 或者 不过 反正 就是 主要 直接
    开始 结束 之前 之后 当时 最近 刚才 刚刚 马上 出来 进去 上去 下来
    看看 说说 问问 回复 消息 图片 表情 手机 电脑 网络 时间 工作 生活
    """.split()
)
COMMON_LATIN = frozenset(
    """
    the and for this that with from have you your are not yes but can
    com www http https test qq url img jpg png gif
    """.split()
)


def _message_terms(content: str) -> set[str]:
    text = URL_RE.sub(" ", str(content or ""))
    text = CQ_RE.sub(" ", text)
    if SENSITIVE_RE.search(text):
        return set()
    terms: set[str] = set()
    for match in LATIN_WORD_RE.findall(text):
        value = match.lower()
        if value not in COMMON_LATIN:
            terms.add(value)
    for run in CJK_RUN_RE.findall(text):
        max_size = min(6, len(run))
        for size in range(2, max_size + 1):
            for index in range(0, len(run) - size + 1):
                value = run[index : index + size]
                if value not in COMMON_TERMS:
                    terms.add(value)
        if len(terms) >= 120:
            break
    return terms


def extract_jargon_candidates(
    messages: list[dict[str, Any]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    occurrences: dict[str, set[int]] = {}
    members: dict[str, set[str]] = {}
    for message_index, message in enumerate(messages):
        if str(message.get("role") or "user") != "user":
            continue
        member_id = str(message.get("member_id") or "")
        for term in _message_terms(str(message.get("content") or "")):
            occurrences.setdefault(term, set()).add(message_index)
            if member_id:
                members.setdefault(term, set()).add(member_id)

    ranked = []
    for term, message_ids in occurrences.items():
        member_ids = members.get(term) or set()
        if len(message_ids) < 2 or len(member_ids) < 2:
            continue
        ranked.append(
            {
                "term": term,
                "occurrences": len(message_ids),
                "member_count": len(member_ids),
                "score": len(message_ids) * 10
                + len(member_ids) * 3
                + min(len(term), 6),
            }
        )
    ranked.sort(
        key=lambda item: (
            item["score"],
            item["occurrences"],
            len(item["term"]),
            item["term"],
        ),
        reverse=True,
    )

    selected = []
    for item in ranked:
        term = item["term"]
        if any(
            term in existing["term"] or existing["term"] in term
            for existing in selected
        ):
            continue
        selected.append(item)
        if len(selected) >= max(1, min(int(limit), 20)):
            break
    return selected
