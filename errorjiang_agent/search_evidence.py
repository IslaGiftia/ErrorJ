from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any
from urllib.parse import urlsplit


DATE_RE = re.compile(
    r"(?P<year>20\d{2})[-/.年](?P<month>\d{1,2})[-/.月](?P<day>\d{1,2})"
)
OFFICIAL_SUFFIXES = (
    ".gov",
    ".gov.cn",
    ".edu",
    ".edu.cn",
)
OFFICIAL_HOSTS = frozenset(
    {
        "arxiv.org",
        "docs.github.com",
        "docs.python.org",
        "developer.mozilla.org",
        "edu.cn",
        "gov.cn",
        "learn.microsoft.com",
        "nvd.nist.gov",
        "who.int",
        "www.who.int",
    }
)


def _parse_date(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    match = DATE_RE.search(text)
    if match:
        try:
            return datetime(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_official(host: str) -> bool:
    host = host.lower()
    return host in OFFICIAL_HOSTS or any(
        host.endswith(suffix) for suffix in OFFICIAL_SUFFIXES
    )


def assess_search_evidence(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    result = dict(payload or {})
    current = now or datetime.now(timezone.utc)
    results = []
    domains = set()
    official_count = 0
    dated_count = 0
    undated_count = 0
    latest: datetime | None = None
    seen_titles: dict[str, int] = {}
    for raw in result.get("results") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        url = str(item.get("url") or "")
        try:
            host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
        except ValueError:
            host = ""
        if host:
            domains.add(host)
        official = _is_official(host)
        official_count += 1 if official else 0
        published = _parse_date(item.get("date"))
        if published is None:
            published = _parse_date(
                f"{item.get('title') or ''} {item.get('snippet') or ''}"
            )
        freshness_days = None
        if published:
            dated_count += 1
            freshness_days = max(
                0,
                (current.astimezone(timezone.utc) - published.astimezone(timezone.utc)).days,
            )
            latest = max(latest, published) if latest else published
            item["published_date"] = published.date().isoformat()
            item["freshness_days"] = freshness_days
        else:
            undated_count += 1
        authority = max(0.0, min(_number(item.get("authority")) / 10, 1.0))
        rerank = max(0.0, min(_number(item.get("rerank_score")), 1.0))
        recency = (
            max(0.0, 1.0 - min(freshness_days, 365) / 365)
            if freshness_days is not None
            else 0.0
        )
        item["source_quality"] = round(
            min(
                1.0,
                authority * 0.45
                + rerank * 0.25
                + (0.2 if official else 0.0)
                + recency * 0.1,
            ),
            3,
        )
        title_key = re.sub(
            r"\W+",
            "",
            str(item.get("title") or "").casefold(),
        )
        if title_key:
            seen_titles[title_key] = seen_titles.get(title_key, 0) + 1
            if seen_titles[title_key] > 1:
                item["possible_syndication"] = True
        item["official_source"] = official
        item["host"] = host
        results.append(item)
    result["results"] = results
    warnings = []
    if official_count == 0 and results:
        warnings.append("没有识别到官方或教育域名来源")
    if undated_count:
        warnings.append(f"{undated_count} 条结果缺少可识别发布日期")
    if any(item.get("possible_syndication") for item in results):
        warnings.append("存在标题重复，可能为转载或同一通稿")
    result["evidence"] = {
        "source_count": len(results),
        "unique_domains": len(domains),
        "official_sources": official_count,
        "dated_sources": dated_count,
        "undated_sources": undated_count,
        "latest_date": latest.date().isoformat() if latest else "",
        "warnings": warnings,
        "untrusted": True,
    }
    return result
