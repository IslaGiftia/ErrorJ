from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any


DOMAIN_LABELS = {
    "security": "安全与漏洞",
    "academic": "学术与论文",
    "finance": "金融与财报",
    "code": "代码与技术文档",
    "legal": "法律与政策",
    "health": "医疗与健康",
    "travel": "旅行与交通",
    "esports": "电竞与赛事",
    "gaming": "游戏与版本",
    "business": "企业与工商",
    "ip": "知识产权",
    "social_media": "社交平台内容",
}

DOMAIN_PATTERNS = {
    "security": re.compile(
        r"(?:\bCVE-\d{4}-\d{4,}\b|漏洞|安全公告|零日|0day|zero[- ]?day|"
        r"exploit|ransomware|恶意软件|渗透测试|数据泄露|供应链攻击|"
        r"vulnerability|advisory)",
        re.IGNORECASE,
    ),
    "academic": re.compile(
        r"(?:\bDOI\b|10\.\d{4,9}/\S+|arXiv|论文|文献|学术|期刊|"
        r"论文综述|研究综述|引用|同行评审|preprint|paper)",
        re.IGNORECASE,
    ),
    "finance": re.compile(
        r"(?:股票|股价|财报|营收|净利润|市值|基金|债券|汇率|IPO|"
        r"上市公司|证券|A股|港股|美股|纳斯达克|市盈率|分红|"
        r"earnings|market cap|stock price)",
        re.IGNORECASE,
    ),
    "code": re.compile(
        r"(?:代码|报错|异常|堆栈|接口文档|开发文档|框架|依赖|"
        r"traceback|stack trace|Python|JavaScript|TypeScript|Java|"
        r"React|Vue|Docker|Kubernetes|SQL|Rust|Golang|API reference|"
        r"documentation|bug)",
        re.IGNORECASE,
    ),
    "legal": re.compile(
        r"(?:法律|法规|条例|司法解释|判决|判例|案例|合同纠纷|侵权|"
        r"律师|行政处罚|政策原文|民法典|刑法|GDPR|legal case|statute)",
        re.IGNORECASE,
    ),
    "health": re.compile(
        r"(?:症状|疾病|药物|用药|治疗|医学|诊断|临床|医院|医生|"
        r"指南|副作用|clinical|medical|medicine|diagnosis)",
        re.IGNORECASE,
    ),
    "travel": re.compile(
        r"(?:签证|机票|酒店|旅行|旅游|景点|攻略|行程|航班|高铁|"
        r"交通|过境|入境|visa|flight|hotel|travel)",
        re.IGNORECASE,
    ),
    "esports": re.compile(
        r"(?:英雄联盟|League of Legends|\bLOL\b|\bLPL\b|\bLCK\b|"
        r"\bLEC\b|\bLCS\b|\bMSI\b|\bWorlds\b|\bS\d{1,2}\b|"
        r"\bIG\b|\bGEN(?:\.G)?\b|\bT1\b|\bJDG\b|\bBLG\b|"
        r"\bWBG\b|\bTES\b|\bFPX\b|\bEDG\b|\bRNG\b)",
        re.IGNORECASE,
    ),
    "gaming": re.compile(
        r"(?:游戏|版本更新|角色|攻略|副本|boss|抽卡|装备|"
        r"patch notes|game guide|gameplay)",
        re.IGNORECASE,
    ),
    "business": re.compile(
        r"(?:公司信息|企业信息|工商|注册资本|法定代表人|商业模式|"
        r"并购|融资|创业公司|company profile|business registration)",
        re.IGNORECASE,
    ),
    "ip": re.compile(
        r"(?:专利|商标|著作权|知识产权|国家知识产权局|"
        r"patent|trademark|copyright)",
        re.IGNORECASE,
    ),
    "social_media": re.compile(
        r"(?:微博|B站|bilibili|抖音|小红书|热搜|博主|原视频|"
        r"网友讨论|评论区|social media)",
        re.IGNORECASE,
    ),
}

DOMAIN_QUERY_SUFFIXES = {
    "security": ("官方 漏洞公告 CVE", "NVD official advisory"),
    "academic": ("DOI arXiv 论文 PDF", "official paper abstract"),
    "finance": ("官方公告 财报 数据 来源", "official filing earnings"),
    "code": ("official documentation API reference",),
    "legal": ("官方法规 司法解释 全文",),
    "health": ("临床指南 官方 医学来源",),
    "travel": ("官方 最新 签证 交通 攻略",),
    "esports": ("最新赛果 官方赛程 当前赛季",),
    "gaming": ("官方公告 版本更新 攻略",),
    "business": ("工商信息 官方公告 数据",),
    "ip": ("国家知识产权局 专利 商标 官方",),
    "social_media": ("原帖 原视频 网友讨论",),
}

REGION_CN_RE = re.compile(
    r"(?:中国|国内|人民币|A股|港股|中文|省市|县区|政策|"
    r"国家知识产权局|微博|B站|抖音|小红书)",
    re.IGNORECASE,
)
REGION_INTL_RE = re.compile(
    r"(?:全球|海外|国际|美股|美元|英文|arXiv|DOI|"
    r"NVD|GDPR|international|global)",
    re.IGNORECASE,
)
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)
ARXIV_RE = re.compile(r"\b(?:arXiv:)?\d{4}\.\d{4,5}(?:v\d+)?\b", re.IGNORECASE)
LOL_SEASON_RE = re.compile(r"\bS(?P<season>\d{1,2})\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(?P<year>20\d{2})\b")


@dataclass(frozen=True)
class SearchRoute:
    domains: tuple[str, ...]
    queries: tuple[str, ...]
    region: str
    language: str
    confidence: float
    matched_terms: tuple[str, ...]
    prefer_recent: bool = False
    freshness_days: int | None = None
    target_years: tuple[str, ...] = ()
    preferred_domains: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return " + ".join(
            DOMAIN_LABELS.get(domain, domain) for domain in self.domains
        ) or "通用网页"

    @property
    def primary_query(self) -> str:
        return self.queries[0] if self.queries else ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "domains": list(self.domains),
            "label": self.label,
            "region": self.region,
            "language": self.language,
            "confidence": self.confidence,
            "matched_terms": list(self.matched_terms),
            "prefer_recent": self.prefer_recent,
            "freshness_days": self.freshness_days,
            "target_years": list(self.target_years),
            "preferred_domains": list(self.preferred_domains),
        }


def _dedupe_queries(values: list[str], limit: int = 4) -> tuple[str, ...]:
    result = []
    seen = set()
    for value in values:
        query = " ".join(str(value or "").split()).strip()[:180]
        key = query.casefold()
        if not query or key in seen:
            continue
        seen.add(key)
        result.append(query)
        if len(result) >= limit:
            break
    return tuple(result)


def route_search_intent(
    query: str,
    question: str = "",
    *,
    max_domains: int = 2,
) -> SearchRoute:
    base_query = " ".join(str(query or "").split()).strip()[:160]
    source = f"{base_query} {question}".strip()
    domain_limit = max(1, min(max_domains, 3))
    scores: list[tuple[int, str, tuple[str, ...]]] = []
    for domain, pattern in DOMAIN_PATTERNS.items():
        matches = tuple(
            dict.fromkeys(
                match.group(0)
                for match in pattern.finditer(source)
                if match.group(0)
            )
        )
        if not matches:
            continue
        score = len(matches) * 2
        if domain == "security" and CVE_RE.search(source):
            score += 4
        if domain == "academic" and (
            DOI_RE.search(source) or ARXIV_RE.search(source)
        ):
            score += 4
        scores.append((score, domain, matches))
    scores.sort(key=lambda item: (-item[0], item[1]))
    domains = tuple(item[1] for item in scores[:domain_limit])
    matched_terms = tuple(
        dict.fromkeys(
            term
            for _, _, matches in scores[:domain_limit]
            for term in matches
        )
    )[:8]

    region = "auto"
    if REGION_CN_RE.search(source):
        region = "cn"
    if REGION_INTL_RE.search(source):
        region = "intl"
    if CVE_RE.search(source):
        region = "intl"
    language = "zh-CN"
    if (
        CVE_RE.search(source)
        or DOI_RE.search(source)
        or ARXIV_RE.search(source)
        or (domains == ("code",) and not REGION_CN_RE.search(source))
    ):
        language = "en"

    esports = "esports" in domains
    target_years: tuple[str, ...] = ()
    preferred_domains: tuple[str, ...] = ()
    freshness_days = None
    if esports:
        season = LOL_SEASON_RE.search(source)
        explicit_year = YEAR_RE.search(source)
        if season:
            target_year = 2010 + int(season.group("season"))
        elif explicit_year:
            target_year = int(explicit_year.group("year"))
        else:
            target_year = datetime.now().year
        target_years = (str(target_year),)
        preferred_domains = (
            "lolesports.com",
            "lpl.qq.com",
            "lol.qq.com",
        )
        freshness_days = 540

    special = []
    if base_query:
        cve = CVE_RE.search(source)
        if cve:
            special.append(f"{cve.group(0).upper()} NVD official advisory")
        doi = DOI_RE.search(source)
        if doi:
            special.append(f"{doi.group(0)} paper DOI")
        arxiv = ARXIV_RE.search(source)
        if arxiv:
            special.append(f"{arxiv.group(0)} arXiv paper")

    generated = []
    if base_query and esports:
        season = LOL_SEASON_RE.search(source)
        season_text = (
            f"S{int(season.group('season'))}" if season else "英雄联盟"
        )
        year = target_years[0]
        generated.extend(
            (
                f"{base_query} {year} {season_text} 最新赛果 官方赛程",
                f"{base_query} {year} 当前赛季 交手记录",
                f"site:lolesports.com {base_query} {year}",
            )
        )
    elif base_query:
        for domain in domains:
            for suffix in DOMAIN_QUERY_SUFFIXES.get(domain, ()):
                generated.append(f"{base_query} {suffix}")
    if base_query:
        generated.append(base_query)
    queries = _dedupe_queries([*special, *generated], 4)
    confidence = 0.0
    if scores:
        confidence = min(0.95, 0.55 + scores[0][0] * 0.06)
    return SearchRoute(
        domains=domains,
        queries=queries,
        region=region,
        language=language,
        confidence=round(confidence, 2),
        matched_terms=matched_terms,
        prefer_recent=esports,
        freshness_days=freshness_days,
        target_years=target_years,
        preferred_domains=preferred_domains,
    )
