import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.bm25 import tokenize
from app.config import Settings
from app.models import Evidence, ToolResult


class DocsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)
    mode: Literal["hybrid", "bm25", "vector"] = "hybrid"

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class GithubArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=200)
    top_k: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def plain_keywords(cls, value):
        if not value.strip() or re.search(r"\b(repo|org|user):|\b(OR|NOT)\b", value, re.I):
            raise ValueError("Use keywords without scope overrides or boolean operators")
        return value.strip()


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search the pinned official FastAPI documentation. Use English keywords for this English corpus.",
            "parameters": DocsArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_github_issues",
            "description": "Search current public FastAPI GitHub issues and PRs. Community reports are not official guarantees; does not search Discussions.",
            "parameters": GithubArgs.model_json_schema(),
        },
    },
]


class ToolRegistry:
    def __init__(self, retriever, settings: Settings, github_client=None):
        self.retriever, self.settings = retriever, settings
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "fastapi-helper-agent",
        }
        token = settings.github_token.get_secret_value()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.github = github_client or httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            timeout=settings.tool_timeout,
        )

    async def execute(self, name: str, arguments: str) -> ToolResult:
        try:
            if len(arguments) > 4000:
                return ToolResult(error="arguments_too_large")
            schema = {"search_docs": DocsArgs, "search_github_issues": GithubArgs}.get(name)
            if schema is None:
                return ToolResult(error="unknown_tool")
            payload = json.loads(arguments)
            if isinstance(payload, dict):
                payload.setdefault("top_k", self.settings.top_k)
            args = schema.model_validate(payload)
            action = self.search_docs(args) if name == "search_docs" else self.search_github(args)
            return await asyncio.wait_for(action, timeout=self.settings.tool_timeout)
        except (ValidationError, ValueError, TypeError):
            return ToolResult(error="invalid_tool_arguments")
        except TimeoutError:
            return ToolResult(error="tool_timeout")
        except Exception:
            # Never echo provider exceptions: they can contain credentials or request bodies.
            return ToolResult(error="tool_unavailable")

    async def search_docs(self, args: DocsArgs):
        hits, warnings = await asyncio.to_thread(
            self.retriever.search, args.query, args.mode, args.top_k
        )
        evidence = []
        query_tokens = set(tokenize(args.query))
        for hit in hits:
            lexical_ok = hit.bm25_score >= self.settings.min_bm25_score
            vector_ok = (
                self.settings.app_mode == "live"
                and hit.similarity is not None
                and hit.similarity >= self.settings.min_vector_similarity
            )
            if not (lexical_ok or vector_ok):
                continue
            chunk = hit.chunk
            if self.settings.app_mode == "demo":
                coverage = len(query_tokens & set(tokenize(chunk.text))) / max(len(query_tokens), 1)
                if coverage < self.settings.demo_min_query_coverage:
                    continue
            evidence.append(
                Evidence(
                    id="D" + chunk.id,
                    text=chunk.text[:6000],
                    source=chunk.source,
                    title=chunk.title,
                    heading=chunk.heading,
                    url=chunk.url,
                    version=chunk.version,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    score=hit.score,
                )
            )
        return ToolResult(evidence=evidence, warnings=warnings)

    async def search_github(self, args: GithubArgs):
        if self.settings.app_mode == "demo":
            return ToolResult(error="github_disabled_in_demo")
        response = await self.github.get(
            "/search/issues",
            params={
                "q": f"repo:fastapi/fastapi {args.query}",
                "per_page": args.top_k,
            },
        )
        if response.status_code in {403, 429}:
            return ToolResult(
                error="github_rate_limited",
                warnings=["retry_after=" + response.headers.get("retry-after", "unknown")[:32]],
            )
        response.raise_for_status()
        payload = response.json()
        evidence = []
        for item in payload.get("items", [])[: args.top_k]:
            url = item.get("html_url", "")
            if not re.fullmatch(r"https://github.com/fastapi/fastapi/(issues|pull)/[0-9]+", url):
                continue
            evidence.append(
                Evidence(
                    id="G" + str(item["number"]),
                    text=(item["title"] + "\n" + (item.get("body") or ""))[:6000],
                    title=item["title"],
                    source=f"fastapi/fastapi#{item['number']}",
                    url=url,
                    version=item.get("updated_at", "unknown"),
                    kind="github",
                    retrieved_at=datetime.now(UTC).isoformat(),
                )
            )
        warnings = ["github_results_incomplete"] if payload.get("incomplete_results") else []
        return ToolResult(evidence=evidence, warnings=warnings)

    async def close(self):
        await self.github.aclose()
