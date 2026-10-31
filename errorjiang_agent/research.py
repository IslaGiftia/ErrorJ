from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import re
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .errors import AgentError


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "spm",
    "from",
    "source",
}


class ResearchProvider(Protocol):
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...

    def web_search(
        self,
        query: str,
        count: int = 5,
        original_question: str = "",
    ) -> dict[str, Any]:
        ...

    def web_fetch(self, url: str) -> dict[str, Any]:
        ...


class WebResearchEngine:
    def __init__(
        self,
        provider: ResearchProvider,
        *,
        max_queries: int = 4,
        max_fetches: int = 3,
        max_results: int = 6,
    ):
        self.provider = provider
        self.max_queries = max(2, min(int(max_queries), 5))
        self.max_fetches = max(1, min(int(max_fetches), 5))
        self.max_results = max(4, min(int(max_results), 10))

    def run(
        self,
        query: str,
        original_question: str = "",
        count: int = 5,
    ) -> dict[str, Any]:
        base_query = " ".join(str(query or "").split()).strip()[:160]
        if not base_query:
            raise AgentError("搜索词不能为空。")
        if not callable(getattr(self.provider, "web_search", None)):
            raise AgentError("当前模型 Provider 不支持网页搜索。")
        if not callable(getattr(self.provider, "web_fetch", None)):
            raise AgentError("当前模型 Provider 不支持网页抓取。")

        queries = self._plan_queries(base_query, original_question)
        batches, errors = self._search_all(
            queries,
            max(3, min(int(count), 10)),
            original_question,
        )
        merged = self._merge_results(batches)
        if not merged:
            detail = "；".join(errors[:3]) or "没有返回可用结果。"
            raise AgentError(f"全网搜索失败：{detail}")

        pages, fetch_errors = self._fetch_pages(
            merged[: self.max_fetches],
        )
        errors.extend(fetch_errors)
        payload = {
            "query": base_query,
            "queries": queries,
            "untrusted": True,
            "fetched_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "results": [
                self._compact_result(item)
                for item in merged[: self.max_results]
            ],
            "pages": pages,
            "errors": errors[:6],
        }
        return self._fit_payload(payload)

    def _plan_queries(
        self,
        query: str,
        original_question: str,
    ) -> list[str]:
        question = " ".join(str(original_question or query).split()).strip()
        messages = [
            {
                "role": "system",
                "content": (
                    "你是网页搜索策略规划器。根据用户问题生成 2 到 4 个"
                    "互补的中文搜索词，用于查找最新事实、背景、原因、"
                    "不同来源或官方回应。不要回答问题，只输出 JSON："
                    '{"queries":["关键词1","关键词2"]}。'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户问题：{question[:500]}\n"
                    f"初始搜索词：{query[:160]}"
                ),
            },
        ]
        planned: list[str] = []
        try:
            response = self.provider.chat(messages, [])
            content = str(response.get("content") or "")
            payload = self._extract_json(content)
            if isinstance(payload, dict):
                planned = payload.get("queries") or []
            elif isinstance(payload, list):
                planned = payload
        except Exception:
            planned = []
        if isinstance(planned, str):
            planned = [planned]
        elif not isinstance(planned, (list, tuple)):
            planned = []
        queries = self._clean_queries([query, *list(planned)])
        if len(queries) < 2:
            queries = self._clean_queries(
                [query, *self._fallback_queries(query, question)]
            )
        return queries[: self.max_queries]

    @staticmethod
    def _extract_json(content: str) -> Any:
        text = str(content or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}

    def _clean_queries(self, values: list[Any]) -> list[str]:
        result = []
        seen = set()
        for value in values:
            query = " ".join(str(value or "").split()).strip()[:100]
            key = query.casefold()
            if not query or key in seen:
                continue
            seen.add(key)
            result.append(query)
            if len(result) >= self.max_queries:
                break
        return result

    @staticmethod
    def _fallback_queries(query: str, question: str) -> list[str]:
        text = f"{query} {question}"
        candidates = []
        if any(word in text for word in ("最新", "今天", "近期", "进展")):
            candidates.append(f"{query} 最新消息 官方")
        if any(word in text for word in ("为什么", "原因", "导致", "影响")):
            candidates.extend(
                [
                    f"{query} 原因 分析",
                    f"{query} 影响 专家",
                ]
            )
        elif any(word in text for word in ("对比", "区别", "哪个好")):
            candidates.extend(
                [
                    f"{query} 对比",
                    f"{query} 实测 评价",
                ]
            )
        else:
            candidates.extend(
                [
                    f"{query} 最新",
                    f"{query} 来源 官方",
                ]
            )
        return candidates

    def _search_all(
        self,
        queries: list[str],
        count: int,
        original_question: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        batches = []
        errors = []
        with ThreadPoolExecutor(
            max_workers=min(len(queries), 4),
            thread_name_prefix="web-research-search",
        ) as pool:
            futures = {
                pool.submit(
                    self.provider.web_search,
                    query,
                    count,
                    original_question,
                ): (index, query)
                for index, query in enumerate(queries)
            }
            for future in as_completed(futures):
                index, query = futures[future]
                try:
                    data = future.result()
                    batches.append(
                        {
                            "query_index": index,
                            "query": query,
                            "data": data if isinstance(data, dict) else {},
                        }
                    )
                except Exception as exc:
                    errors.append(f"{query}: {exc}")
        return batches, errors

    def _merge_results(
        self,
        batches: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for batch in batches:
            query = str(batch.get("query") or "")
            query_weight = 1.0 / (int(batch.get("query_index") or 0) + 1)
            data = batch.get("data") or {}
            for item in data.get("results") or []:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                title = str(item.get("title") or "").strip()
                key = self._canonical_url(url) or title.casefold()
                if not key:
                    continue
                current = merged.get(key)
                if current is None:
                    current = dict(item)
                    current["matched_queries"] = []
                    current["_hits"] = 0
                    current["_query_weight"] = 0.0
                    merged[key] = current
                if query and query not in current["matched_queries"]:
                    current["matched_queries"].append(query)
                current["_hits"] += 1
                current["_query_weight"] = max(
                    float(current["_query_weight"]),
                    query_weight,
                )
                for field in ("summary", "snippet"):
                    incoming = str(item.get(field) or "").strip()
                    if len(incoming) > len(str(current.get(field) or "")):
                        current[field] = incoming
        results = list(merged.values())
        results.sort(key=self._result_rank, reverse=True)
        return results

    @staticmethod
    def _result_rank(item: dict[str, Any]) -> tuple[float, float, float, float]:
        def number(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        return (
            number(item.get("_hits")),
            number(item.get("_query_weight")),
            number(item.get("authority")),
            number(item.get("rerank_score")),
        )

    def _fetch_pages(
        self,
        results: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        pages = []
        errors = []
        fetchable = [
            item
            for item in results
            if str(item.get("url") or "").startswith(("http://", "https://"))
        ][: self.max_fetches]
        if not fetchable:
            return pages, errors
        with ThreadPoolExecutor(
            max_workers=len(fetchable),
            thread_name_prefix="web-research-fetch",
        ) as pool:
            futures = {
                pool.submit(self.provider.web_fetch, item["url"]): item
                for item in fetchable
            }
            for future in as_completed(futures):
                item = futures[future]
                url = str(item.get("url") or "")
                try:
                    page = future.result()
                    content = " ".join(
                        str((page or {}).get("content") or "").split()
                    )
                    pages.append(
                        {
                            "title": str(
                                (page or {}).get("title")
                                or item.get("title")
                                or ""
                            )[:300],
                            "url": url,
                            "content": content[:1800],
                            "untrusted": True,
                        }
                    )
                except Exception as exc:
                    errors.append(f"抓取 {url}: {exc}")
        return pages, errors

    @staticmethod
    def _compact_result(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": str(item.get("title") or "")[:160],
            "url": str(item.get("url") or "")[:600],
            "site_name": str(item.get("site_name") or "")[:80],
            "date": item.get("date"),
            "snippet": str(item.get("snippet") or "")[:160],
            "summary": str(item.get("summary") or "")[:400],
            "matched_queries": [
                str(value)[:80]
                for value in list(item.get("matched_queries") or [])[:3]
            ],
        }

    @staticmethod
    def _fit_payload(
        payload: dict[str, Any],
        budget: int = 14500,
    ) -> dict[str, Any]:
        if len(json.dumps(payload, ensure_ascii=False)) <= budget:
            return payload
        for page in payload.get("pages") or []:
            page["content"] = str(page.get("content") or "")[:1200]
        if len(json.dumps(payload, ensure_ascii=False)) <= budget:
            return payload
        for item in payload.get("results") or []:
            item["summary"] = str(item.get("summary") or "")[:240]
            item["snippet"] = str(item.get("snippet") or "")[:120]
        payload["pages"] = list(payload.get("pages") or [])[:2]
        payload["results"] = list(payload.get("results") or [])[:5]
        if len(json.dumps(payload, ensure_ascii=False)) <= budget:
            return payload
        for page in payload.get("pages") or []:
            page["content"] = str(page.get("content") or "")[:800]
        payload["results"] = list(payload.get("results") or [])[:4]
        return payload

    @staticmethod
    def _canonical_url(value: str) -> str:
        text = str(value or "").strip()
        if not text.startswith(("http://", "https://")):
            return ""
        try:
            parsed = urlsplit(text)
        except ValueError:
            return text
        host = (parsed.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        query = []
        for key, val in parse_qsl(parsed.query, keep_blank_values=True):
            lowered = key.lower()
            if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS:
                continue
            query.append((key, val))
        path = parsed.path.rstrip("/") or "/"
        return urlunsplit(
            (
                parsed.scheme.lower(),
                host,
                path,
                urlencode(query, doseq=True),
                "",
            )
        )
