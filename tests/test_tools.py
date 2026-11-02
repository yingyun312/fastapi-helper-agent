import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.embedder import APIEmbedder
from app.llm import ChatModel
from app.tools import ToolRegistry


@pytest.mark.parametrize(
    "name,args",
    [
        ("delete_all", "{}"),
        ("search_docs", "{"),
        ("search_docs", '{"query":"hi","top_k":0}'),
        ("search_docs", '{"query":"hi","top_k":"5"}'),
        ("search_docs", '{"query":"hi","surprise":true}'),
        ("search_docs", '{"query":"  "}'),
        ("search_github_issues", '{"query":"repo:evil/evil OR secret"}'),
    ],
)
async def test_tool_validation(retriever, settings, name, args):
    tools = ToolRegistry(retriever, settings)
    result = await tools.execute(name, args)
    assert result.error in {"unknown_tool", "invalid_tool_arguments"}
    await tools.close()


async def test_github_scope_rate_limit_and_partial_results(retriever, settings):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "incomplete_results": True,
                "items": [
                    {
                        "number": 123,
                        "title": "Test issue",
                        "body": "User reported a problem",
                        "updated_at": "2026-01-01",
                        "html_url": "https://github.com/fastapi/fastapi/issues/123",
                    },
                    {
                        "number": 456,
                        "title": "Outside scope",
                        "html_url": "https://github.com/other/repo/issues/456",
                    },
                ],
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.github.com"
    )
    tools = ToolRegistry(retriever, settings.model_copy(update={"app_mode": "live"}), client)
    result = await tools.execute("search_github_issues", '{"query":"dependencies yield"}')
    assert len(result.evidence) == 1
    assert result.evidence[0].retrieved_at
    assert result.warnings == ["github_results_incomplete"]
    assert requests[0].url.params["q"].startswith("repo:fastapi/fastapi ")
    await tools.close()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(403, headers={"Retry-After": "60"})),
        base_url="https://api.github.com",
    )
    tools = ToolRegistry(retriever, settings.model_copy(update={"app_mode": "live"}), client)
    assert (
        await tools.execute("search_github_issues", '{"query":"Depends"}')
    ).error == "github_rate_limited"
    await tools.close()


async def test_tools_timeout_demo_and_low_evidence(retriever, settings, monkeypatch):
    tools = ToolRegistry(retriever, settings.model_copy(update={"tool_timeout": 0.01}))
    assert (
        await tools.execute("search_github_issues", '{"query":"Depends"}')
    ).error == "github_disabled_in_demo"
    assert not (await tools.execute("search_docs", '{"query":"qwertyxyz"}')).evidence

    async def slow(args):
        await asyncio.sleep(1)

    monkeypatch.setattr(tools, "search_docs", slow)
    assert (await tools.execute("search_docs", '{"query":"path"}')).error == "tool_timeout"
    await tools.close()


def test_api_embedding_batch_order_and_shape(settings):
    batches = []

    def create(**kwargs):
        batches.append(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=i, embedding=[float(i), 1.0])
                for i in reversed(range(len(kwargs["input"])))
            ]
        )

    embedder = APIEmbedder(settings, SimpleNamespace(embeddings=SimpleNamespace(create=create)))
    result = embedder.embed(["text"] * 35)
    assert [len(batch["input"]) for batch in batches] == [32, 3]
    assert result[0] == [0.0, 1.0]
    assert result[31] == [31.0, 1.0]


async def test_real_openai_sdk_compatible_http_protocol(settings):
    # OpenAI 3 uses httpx2; older supported releases use httpx. No external HTTP is made.
    import inspect

    from openai import AsyncOpenAI

    transport_module = __import__(
        "httpx2" if "httpx2" in str(inspect.signature(AsyncOpenAI)) else "httpx"
    )
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return transport_module.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "fake",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "t1",
                                    "type": "function",
                                    "function": {
                                        "name": "search_docs",
                                        "arguments": '{"query":"path"}',
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            },
        )

    http = transport_module.AsyncClient(transport=transport_module.MockTransport(handler))
    sdk = AsyncOpenAI(api_key="test-placeholder", base_url="https://model.test", http_client=http)
    model = ChatModel(settings, sdk)
    reply = await model.complete([{"role": "user", "content": "hello"}], [])
    assert reply.tool_calls[0]["function"]["name"] == "search_docs"
    assert reply.usage["total_tokens"] == 5
    assert requests[0]["thinking"] == {"type": "disabled"}
    await model.close()
