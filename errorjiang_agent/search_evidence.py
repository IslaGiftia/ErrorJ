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
        "lolesports.com",
        "lol.qq.com",
        "lpl.qq.com",
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
    prefer_recent: bool = False,
    max_age_days: int | None = None,
    target_years: tuple[str, ...] = (),
    preferred_domains: tuple[str, ...] = (),
) -> dict[str, Any]:
    result = dict(payload or {})
    current = now or datetime.now(timezone.utc)
    results = []
    domains = set()
    official_count = 0
    dated_count = 0
    undated_count = 0
    stale_count = 0
    period_mismatch_count = 0
    time_matched_count = 0
    latest: datetime | None = None
    seen_titles: dict[str, int] = {}
    year_targets = {
        str(value)
        for value in target_years
        if re.fullmatch(r"20\d{2}", str(value))
    }
    preferred_hosts = tuple(
        str(value).lower().removeprefix("www.")
        for value in preferred_domains
        if str(value).strip()
    )
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
        stale = False
        if published:
            dated_count += 1
            freshness_days = max(
                0,
                (current.astimezone(timezone.utc) - published.astimezone(timezone.utc)).days,
            )
            latest = max(latest, published) if latest else published
            item["published_date"] = published.date().isoformat()
            item["freshness_days"] = freshness_days
            stale = bool(
                max_age_days is not None
                and freshness_days > max(0, int(max_age_days))
            )
        else:
            undated_count += 1
        combined_text = " ".join(
            str(item.get(field) or "")
            for field in ("title", "snippet", "summary", "published_date")
        )
        item_years = set(re.findall(r"\b(20\d{2})\b", combined_text))
        period_match = bool(year_targets and item_years & year_targets)
        period_mismatch = bool(
            year_targets
            and item_years
            and not (item_years & year_targets)
        )
        time_matched_count += 1 if period_match else 0
        period_mismatch_count += 1 if period_mismatch else 0
        stale_count += 1 if stale else 0
        authority = max(0.0, min(_number(item.get("authority")) / 10, 1.0))
        rerank = max(0.0, min(_number(item.get("rerank_score")), 1.0))
        recency_window = max(1, int(max_age_days or 365))
        recency = (
            max(0.0, 1.0 - min(freshness_days, recency_window) / recency_window)
            if freshness_days is not None
            else 0.0
        )
        preferred = bool(
            host
            and any(
                host == preferred_host
                or host.endswith("." + preferred_host)
                for preferred_host in preferred_hosts
            )
        )
        item["source_quality"] = round(
            max(
                0.0,
                min(
                    1.0,
                    authority * 0.45
                    + rerank * 0.25
                    + (0.2 if official else 0.0)
                    + recency * 0.1
                    + (0.08 if preferred else 0.0)
                    + (0.08 if period_match else 0.0)
                    - (0.25 if period_mismatch else 0.0)
                    - (0.25 if stale else 0.0),
                ),
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
        item["preferred_source"] = preferred
        item["stale"] = stale
        item["period_match"] = period_match
        item["period_mismatch"] = period_mismatch
        results.append(item)
    if prefer_recent:
        results.sort(
            key=lambda item: (
                not bool(item.get("stale")),
                not bool(item.get("period_mismatch")),
                bool(item.get("period_match")),
                _number(item.get("source_quality")),
                -int(item.get("freshness_days") or 99999),
            ),
            reverse=True,
        )
    result["results"] = results
    warnings = []
    if official_count == 0 and results:
        warnings.append("没有识别到官方或教育域名来源")
    if undated_count:
        warnings.append(f"{undated_count} 条结果缺少可识别发布日期")
    if any(item.get("possible_syndication") for item in results):
        warnings.append("存在标题重复，可能为转载或同一通稿")
    if stale_count:
        warnings.append(f"{stale_count} 条结果超出当前查询的时效范围")
    if period_mismatch_count:
        warnings.append(
            f"{period_mismatch_count} 条结果只提到其他年份，可能是旧赛季或旧资料"
        )
    result["evidence"] = {
        "source_count": len(results),
        "unique_domains": len(domains),
        "official_sources": official_count,
        "dated_sources": dated_count,
        "undated_sources": undated_count,
        "stale_sources": stale_count,
        "time_matched_sources": time_matched_count,
        "period_mismatch_sources": period_mismatch_count,
        "latest_date": latest.date().isoformat() if latest else "",
        "warnings": warnings,
        "untrusted": True,
    }
    return result
