from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


DEFAULT_LEXICON_PATH = (
    Path(__file__).resolve().parent / "resources" / "meme_lexicon.json"
)
TIER_SCORE = {"SSS": 6, "SS": 5, "S": 4, "A": 3, "B": 2, "C": 1}
AUTO_IGNORE_TERMS = frozenset(
    {
        "普通人",
        "干货",
        "真的",
        "笑死",
        "哈哈哈",
        "确实",
        "好家伙",
        "不是吧",
        "什么意思",
    }
)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class MemeLexicon:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or DEFAULT_LEXICON_PATH)
        self.entries: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        for name, raw in payload.items():
            if not isinstance(raw, dict):
                continue
            term = " ".join(str(name or "").split()).strip()
            meaning = " ".join(str(raw.get("meaning") or "").split()).strip()
            if not term or not meaning:
                continue
            self.entries.append(
                {
                    "term": term[:80],
                    "meaning": meaning[:600],
                    "usage": " ".join(
                        str(raw.get("usage") or "").split()
                    ).strip()[:300],
                    "source": " ".join(
                        str(raw.get("source") or "").split()
                    ).strip()[:200],
                    "tier": str(raw.get("tier") or "").upper()[:3],
                    "heat": _number(raw.get("heat")),
                }
            )
        self.entries.sort(
            key=lambda item: (
                TIER_SCORE.get(str(item.get("tier") or ""), 0),
                _number(item.get("heat")),
                len(str(item.get("term") or "")),
            ),
            reverse=True,
        )

    @staticmethod
    def _entry_payload(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "term": entry.get("term"),
            "meaning": entry.get("meaning"),
            "usage": entry.get("usage") or "",
            "source": entry.get("source") or "",
            "tier": entry.get("tier") or "",
            "heat": entry.get("heat") or 0,
        }

    def lookup(self, query: str, limit: int = 3) -> dict[str, Any]:
        value = " ".join(str(query or "").split()).strip()[:120]
        if not value:
            return {
                "query": "",
                "matched": [],
                "error": "请提供要查询的梗名或原句。",
            }
        lowered = value.casefold()
        scored = []
        for entry in self.entries:
            term = str(entry.get("term") or "")
            key = term.casefold()
            if not key:
                continue
            if key == lowered:
                match_score = 120
            elif key in lowered:
                match_score = 90 + min(len(key), 20)
            elif lowered in key:
                match_score = 70 + min(len(lowered), 20)
            else:
                continue
            scored.append(
                (
                    match_score,
                    TIER_SCORE.get(str(entry.get("tier") or ""), 0),
                    _number(entry.get("heat")),
                    entry,
                )
            )
        scored.sort(
            key=lambda item: (item[0], item[1], item[2], len(item[3]["term"])),
            reverse=True,
        )
        matches = [
            self._entry_payload(item[3])
            for item in scored[: max(1, min(int(limit), 5))]
        ]
        return {
            "query": value,
            "matched": matches,
            "source": "geng-skill gengku snapshot (MIT)",
            "reference_only": True,
        }

    @staticmethod
    def _contains(text: str, term: str) -> bool:
        if not term:
            return False
        if re.search(r"[A-Za-z0-9]", term):
            pattern = (
                r"(?<![A-Za-z0-9])"
                + re.escape(term)
                + r"(?![A-Za-z0-9])"
            )
            return bool(re.search(pattern, text, re.IGNORECASE))
        return term.casefold() in text.casefold()

    def context_for_text(
        self,
        text: str,
        limit: int = 2,
        max_chars: int = 900,
    ) -> str:
        value = " ".join(str(text or "").split()).strip()[:4000]
        if not value:
            return ""
        explicit = bool(
            re.search(r"(?:什么梗|啥梗|梗是什么|什么意思|怎么来的|来源)", value)
        )
        matches = []
        for entry in self.entries:
            term = str(entry.get("term") or "")
            if not term or term in AUTO_IGNORE_TERMS:
                continue
            if len(term) < 2 or (
                re.fullmatch(r"[A-Za-z0-9]+", term) and len(term) < 3
            ):
                continue
            if not self._contains(value, term):
                continue
            if (
                not explicit
                and len(term) <= 2
                and TIER_SCORE.get(str(entry.get("tier") or ""), 0) < 5
            ):
                continue
            matches.append(entry)
        matches.sort(
            key=lambda item: (
                len(str(item.get("term") or "")),
                TIER_SCORE.get(str(item.get("tier") or ""), 0),
                _number(item.get("heat")),
            ),
            reverse=True,
        )
        lines = []
        used = 0
        for entry in matches[: max(1, min(int(limit), 4))]:
            line = f"{entry['term']}：{entry['meaning']}"
            if entry.get("usage"):
                line += f"（用法：{entry['usage']}）"
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line)
        return "\n".join(lines)
