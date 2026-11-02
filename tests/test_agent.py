import asyncio
import json

import pytest

from app.agent import Agent, validate_answer
from app.llm import ModelReply
from app.memory import SessionStore
from app.models import ToolResult
from tests.conftest import FakeModel, FakeTools


def call(name="search_docs", arguments='{"query":"path parameters"}'):
    return ModelReply(
        tool_calls=[
            {"id": "call1", "type": "function", "function": {"name": name, "arguments": arguments}}
        ]
    )


def final(evidence, **updates):
    payload = {
        "answer": "Use path parameters [Dabc].",
        "abstain": False,
        "citations": [{"id": evidence.id, "quote": evidence.text}],
    }
    payload.update(updates)
    return ModelReply(content=json.dumps(payload), usage={"total_tokens": 12})


async def collect(agent, question="path parameters", history=None, session_id="a"):
    return [item async for item in agent.run(question, history or [], session_id)]


async def test_loop_pairs_tool_messages_and_validates_citations(settings, evidence):
    model = FakeModel([call(), final(evidence)])
    events = await collect(Agent(model, FakeTools(evidence), settings))
    assert events[-1][0] == "done"
    assert events[-1][1]["abstained"] is False
    assert events[-1][1]["sources"][0]["url"] == evidence.url
    assert model.calls[-1][-1]["tool_call_id"] == "call1"
    assert model.calls[-1][-2]["tool_calls"][0]["id"] == "call1"
    assert "reasoning" not in json.dumps(events)


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"answer": "Uncited statement"}, "invalid_citation"),
        ({"answer": "Wrong [Dunknown]"}, "invalid_citation"),
        (
            {"citations": [{"id": "Dabc", "quote": "fabricated source quotation"}]},
            "quote_not_in_evidence",
        ),
        ({"answer": "Cited [Dabc]\n\nUnsupported paragraph"}, "uncited_paragraph"),
        ({"answer": "See https://fake.test [Dabc]"}, "unsupported_url"),
    ],
)
def test_citation_failures_fail_closed(evidence, change, reason):
    answer = final(evidence, **change)
    assert validate_answer(answer.content, {evidence.id: evidence})[3] == reason


async def test_no_evidence_refuses(settings, evidence):
    events = await collect(Agent(FakeModel([final(evidence)]), FakeTools(), settings))
    assert events[-1][1]["abstained"]
    assert events[-1][1]["sources"] == []


async def test_max_steps_model_error_and_timeout(settings):
    loop = Agent(FakeModel([call()]), FakeTools(), settings.model_copy(update={"max_steps": 2}))
    assert (await collect(loop))[-1][1]["reason"] == "max_steps"
    assert len(loop.tools.calls) == 2
    failed = Agent(FakeModel([RuntimeError("SECRET")]), FakeTools(), settings)
    events = await collect(failed)
    assert events[-1][1]["reason"] == "model_unavailable"
    assert "SECRET" not in json.dumps(events)

    class SlowModel:
        async def complete(self, *args):
            await asyncio.sleep(1)

    slow = Agent(SlowModel(), FakeTools(), settings.model_copy(update={"llm_timeout": 0.01}))
    assert (await collect(slow))[-1][1]["reason"] == "model_timeout"


async def test_error_returned_to_model_and_not_cached(settings, evidence):
    tools = FakeTools(result=ToolResult(error="tool_timeout"))
    model = FakeModel([call(), final(evidence)])
    agent = Agent(model, tools, settings)
    result = (await collect(agent))[-1][1]
    assert result["abstained"]
    assert "tool_timeout" in model.calls[-1][-1]["content"]
    assert len(agent.cache) == 0


async def test_cache_context_session_case_version_and_realtime(settings, evidence):
    agent = Agent(FakeModel([call(), final(evidence)]), FakeTools(evidence), settings)
    assert not (await collect(agent))[-1][1]["cache_hit"]
    assert (await collect(agent))[-1][1]["cache_hit"]
    base = agent.cache_key("Depends", [], "a")
    assert base != agent.cache_key("depends", [], "a")
    assert base != agent.cache_key("Depends", [], "b")
    assert base != agent.cache_key("Depends", [{"role": "user", "content": "CORS"}], "a")
    agent.tools.retriever.version = "v2"
    assert base != agent.cache_key("Depends", [], "a")
    github = Agent(
        FakeModel([call("search_github_issues"), final(evidence)]), FakeTools(evidence), settings
    )
    await collect(github)
    assert len(github.cache) == 0
    fresh = Agent(FakeModel([call(), final(evidence)]), FakeTools(evidence), settings)
    await collect(fresh, "latest path parameters")
    assert len(fresh.cache) == 0


async def test_memory_window_isolation_and_concurrent_turns():
    store = SessionStore(turns=2)
    async with store.acquire("a") as session:
        for index in range(3):
            session.append(f"question {index}", f"answer {index}")
        assert len(session.messages()) == 4
        assert session.messages()[0]["content"] == "question 1"
    async with store.acquire("b") as session:
        assert session.messages() == []
    order = []

    async def write(number):
        async with store.acquire("a") as session:
            order.append(("start", number))
            await asyncio.sleep(0.01)
            session.append(str(number), "ok")
            order.append(("end", number))

    await asyncio.gather(write(1), write(2))
    assert order == [("start", 1), ("end", 1), ("start", 2), ("end", 2)]


async def test_session_expiry_and_active_capacity():
    now = [0]
    store = SessionStore(capacity=1, ttl=2, clock=lambda: now[0])
    async with store.acquire("a") as session:
        session.append("hello", "world")
        with pytest.raises(RuntimeError, match="capacity"):
            async with store.acquire("b"):
                pass
    now[0] = 3
    async with store.acquire("a") as session:
        assert session.messages() == []


async def test_cancel_releases_session_without_partial_turn(settings):
    from app.service import ChatService

    started = asyncio.Event()

    class SlowModel:
        async def complete(self, *args):
            started.set()
            await asyncio.sleep(10)

    service = ChatService(Agent(SlowModel(), FakeTools(), settings), settings)

    async def consume():
        return [event async for event in service.stream("question", "a")]

    task = asyncio.create_task(consume())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    session = service.sessions.sessions["a"]
    assert not session.lock.locked()
    assert session.users == 0 and session.messages() == []


async def test_multiple_tool_call_results_stay_paired(settings, evidence):
    first = call()
    second = call("search_github_issues").tool_calls[0]
    second["id"] = "call2"
    first.tool_calls.append(second)
    model = FakeModel([first, final(evidence)])
    result = (await collect(Agent(model, FakeTools(evidence), settings)))[-1][1]
    tool_messages = [message for message in model.calls[-1] if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in tool_messages] == ["call1", "call2"]
    assert result["used_github"] and not result["abstained"]


async def test_demo_quotes_body_instead_of_heading(evidence):
    from app.llm import DemoModel

    body = "HTTPException is a normal Python exception with additional API data."
    evidence.text = (
        "### Raise an HTTPException in your code\n\n"
        "```mermaid\nsequenceDiagram\n\nNote over client: HTTPException raise response\n```\n\n"
        + body
    )
    reply = await DemoModel().complete(
        [
            {"role": "user", "content": "How do I raise HTTPException?"},
            {"role": "tool", "content": json.dumps({"evidence": [evidence.to_dict()]})},
        ],
        [],
    )
    assert json.loads(reply.content)["citations"][0]["quote"] == body
