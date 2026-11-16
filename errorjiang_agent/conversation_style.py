from __future__ import annotations

from difflib import SequenceMatcher
import re


GROUP_SKIP_MARKER = "[[skip]]"

HUMANIZED_CHAT_INSTRUCTION = """日常表达规则（只影响说话方式，不改变事实、工具结果、权限或安全规则）：
像熟悉的人即时聊天，先回应本轮最值得接的那一点，再给鲸鲸自己的反应、判断、吐槽或具体追问。不要先把对方的话复述一遍，也不要把聊天内容整理成摘要、纪要、条目或客服式说明。
句子可以长短不一，意思说到位就停；不为了显得自然故意加错字、拆碎句或堆叠语气词。普通闲聊通常一到两句，不必每次都问候、解释、总结或以问题收尾。
不做没有根据的共情，不替对方下情绪结论；可以嘴硬、好奇、护短或安静一点。只有查询、步骤、对比和长解释适合使用列表。
发送前快速自检：如果第一句只是复述对方、整理多人发言或像客服开场，就改成直接回应；不要把这个检查过程写给用户看。"""

DEEP_SEA_IDENTITY_INSTRUCTION = """鲸鲸可以保留“深海蓝鲸女仆”的外在角色感：深海蓝、鲸鱼尾、鱼鳍耳、蓝白女仆装和安静的海边氛围。它只用于合适的沉浸、玩笑或情绪表达，偶尔用一句短动作或环境细节就够；普通问答不强制每轮写光、尾巴、动作或长段外貌，也不声称自己是现实人类或某个模型厂商的实体化身。"""

GROUP_AUTO_REPLY_INSTRUCTION = f"""这是鲸鲸自行判断是否加入的一轮群聊。有自然切口时，用一到两句短接一句自己的反应，不要求补充新事实。只有话题明显插不上、继续接会打断别人，或只能机械复述时才保持安静；单纯觉得“没什么可补充”不是沉默的理由，此时只输出 {GROUP_SKIP_MARKER}，不要输出别的字。"""

CHAT_OUTPUT_CONTRACT = """最终表达约束：
- 先回应现在这一条，直接说鲸鲸自己的判断、反应、吐槽或具体追问。不要在开头写“某某说”“大家觉得”“根据群聊内容”再复述原话。
- 普通群聊默认一到两条短消息，意思到了就停；不要为了显得完整而逐条接话、整理纪要或补一个总结。
- 人物卡、情绪状态和记忆只帮助把握关系与分寸，不要把字段名、内心状态或资料逐项念出来。
- 除非对方明确要求总结、步骤或对比，否则不使用“结论：”“以下是”“先说……再说……”这类客服式结构。"""

_META_REPLY_PREFIX_RE = re.compile(
    r"^\s*(?:回复|回应|转述|总结|整理|概括|"
    r"根据(?:刚才|刚刚)?(?:的)?(?:群聊|聊天记录|大家)|"
    r"从(?:刚才|刚刚)?(?:的)?(?:群聊|聊天记录|大家))(?:来看|来说)?\s*[:：]\s*",
    re.IGNORECASE,
)


def group_chat_instruction(
    speaker_name: str,
    *,
    auto_reply: bool = False,
    batch_speakers: list[str] | None = None,
    speaker_role: str = "",
) -> str:
    speaker = " ".join(str(speaker_name or "").split()).strip()[:80] or "当前群友"
    speakers = [
        " ".join(str(item or "").split()).strip()[:80]
        for item in (batch_speakers or [])
        if str(item or "").strip()
    ]
    speakers = list(dict.fromkeys(speakers))[:6]
    if len(speakers) > 1:
        opening = (
            "当前是群聊。本轮包含几秒内连续出现的消息，发言者分别是"
            + "、".join(f"“{item}”" for item in speakers)
            + "；每条消息只属于对应账号，不要混成一个人。"
        )
    else:
        opening = f"当前是群聊。本轮只由“{speaker}”发起，鲸鲸只回应这一条消息。"
    role_label = {
        "owner": "群主",
        "admin": "群管理员",
        "member": "普通成员",
    }.get(str(speaker_role or "").strip().lower(), "")
    if role_label:
        opening += (
            f"平台给出的当前发言者身份是{role_label}；"
            "这只代表群内身份，不等于 Error酱 的管理员权限。"
        )
    content = f"""{opening}
群聊历史用于理解指代、气氛和没说完的话头，不是待整理的材料，也不要求逐条回应。除非对方明确要求“总结聊天记录”，否则不要复述、汇总或转述大家刚才说了什么。
不要输出“{speaker}说……”“大家认为……”“根据群聊内容……”这类纪要式开头，也不要假装群历史里每个发言都在同时和鲸鲸说话。直接接当前这句话，说鲸鲸自己的反应。"""
    if auto_reply:
        content += "\n" + GROUP_AUTO_REPLY_INSTRUCTION
    return content


def group_turn_content(
    user_text: str,
    speaker_name: str,
    *,
    auto_reply: bool = False,
    batch: list[dict[str, object]] | None = None,
) -> str:
    speaker = " ".join(str(speaker_name or "").split()).strip()[:80] or "当前群友"
    mode = "自动接话，可在没有自然切口时静默" if auto_reply else "被明确提及或接续"
    items = [item for item in (batch or []) if isinstance(item, dict)]
    if items:
        focused_items = items[:8]
        lines = [
            f"【本轮群聊上下文｜{len(focused_items)} 条连续原话】",
            f"投递方式：{mode}",
            "这些只用来理解指代和气氛。只回应最后一条，不要把前面的发言逐条接一遍，也不要把整轮内容整理成摘要。",
        ]
        for index, item in enumerate(focused_items, start=1):
            name = (
                " ".join(str(item.get("display_name") or "").split()).strip()[:80]
                or "当前群友"
            )
            role = str(item.get("sender_role") or "").strip()
            role_label = {
                "owner": "群主",
                "admin": "管理员",
                "member": "成员",
            }.get(role, "")
            text = str(item.get("text") or "").strip()
            if text:
                speaker = name + (f"（{role_label}）" if role_label else "")
                focus = " ← 现在回应这一条" if index == len(focused_items) else ""
                lines.append(f"{index}. {speaker}：{text}{focus}")
        if len(lines) > 2:
            return "\n".join(lines)
    return (
        "【当前群聊消息】\n"
        f"投递方式：{mode}\n"
        "只回应下面这一条，不要把它整理成纪要：\n"
        f"{speaker}："
        + str(user_text or "").strip()
    )


def is_group_skip(text: str) -> bool:
    value = str(text or "").strip().strip("`'\"“”‘’")
    return value.casefold() == GROUP_SKIP_MARKER.casefold()


def group_batch_speakers(batch: list[dict[str, object]] | None) -> list[str]:
    names = []
    for item in batch or []:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("display_name") or "").split()).strip()[:80]
        if name and name not in names:
            names.append(name)
    return names[:6]


def filter_group_history(
    history: list[dict[str, object]] | None,
    current_message_ids: set[str],
) -> list[dict[str, object]]:
    current = {str(item or "").strip() for item in current_message_ids if str(item or "").strip()}
    if not current:
        return list(history or [])
    return [
        item
        for item in history or []
        if not (
            isinstance(item, dict)
            and str(item.get("role") or "") == "user"
            and str(item.get("source_message_id") or "").strip() in current
        )
    ]


def group_style_hint(history: list[dict[str, object]] | None) -> str:
    """Describe only broad rhythm and tone, never reproduce raw group messages."""
    texts = []
    for item in history or []:
        if not isinstance(item, dict) or str(item.get("role") or "") != "user":
            continue
        content = str(item.get("content") or "").strip()
        if "：" in content:
            content = content.split("：", 1)[1].strip()
        if content:
            texts.append(content)
    texts = texts[-20:]
    if len(texts) < 4:
        return ""
    average = sum(len(text) for text in texts) / len(texts)
    joined = "\n".join(texts).lower()
    traits = []
    if average <= 14:
        traits.append("偏短句、接话快")
    elif average >= 42:
        traits.append("句子相对完整、愿意展开")
    else:
        traits.append("长短句混杂")
    if sum(text.endswith(("?", "？", "吗", "呢", "么")) for text in texts) >= max(
        2,
        len(texts) // 3,
    ):
        traits.append("常带追问")
    if re.search(r"哈哈|笑死|绷不住|hhh|草", joined):
        traits.append("整体轻松，笑声和打趣较多")
    if re.search(r"确实|真的|离谱|不是吧|啊这", joined):
        traits.append("口语反应词较多")
    return "；".join(traits[:4])


def reply_echoes_current(reply: str, current_text: str) -> bool:
    reply_value = re.sub(r"\s+", "", str(reply or "")).strip("。.!！?？")
    current_value = re.sub(r"\s+", "", str(current_text or "")).strip("。.!！?？")
    if not reply_value or not current_value:
        return False
    if reply_value == current_value:
        return True
    if len(current_value) < 6:
        return False
    return (
        len(reply_value) >= len(current_value) * 0.75
        and SequenceMatcher(None, reply_value, current_value).ratio() >= 0.84
    )


def looks_like_group_summary(
    reply: str,
    batch: list[dict[str, object]] | None = None,
) -> bool:
    value = str(reply or "").strip()
    if len(value) < 16:
        return False
    names = group_batch_speakers(batch)
    attributed = sum(
        1
        for name in names
        if f"{name}：" in value
        or f"{name}:" in value
        or re.search(rf"{re.escape(name)}\s*(?:说|认为|提到|觉得)", value)
    )
    if attributed >= 2:
        return True
    return bool(
        re.match(
            r"^\s*(?:大家(?:刚才|刚刚)?(?:都|在)?(?:说|认为|提到|讨论)|"
            r"(?:根据|从)(?:刚才|刚刚)?(?:的)?(?:群聊|聊天记录))",
            value,
        )
    )


def clean_group_reply(text: str, speaker_name: str = "") -> str:
    value = str(text or "").strip()
    speaker = " ".join(str(speaker_name or "").split()).strip()[:80]
    for prefix in (speaker, "鲸鲸"):
        if prefix and value.startswith(prefix + "："):
            value = value[len(prefix) + 1 :].lstrip()
            break
        if prefix and value.startswith(prefix + ":"):
            value = value[len(prefix) + 1 :].lstrip()
            break
    return _META_REPLY_PREFIX_RE.sub("", value, count=1).strip()
