import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.agent import Agent
from app.api import create_app
from app.llm import DemoModel
from app.service import ChatService
from app.tools import ToolRegistry


def parse_sse(text):
    result = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        if lines and lines[0].startswith("event:"):
            result.append((lines[0][7:], json.loads(lines[1][6:])))
    return result


def test_end_to_end_sse_and_session_isolation(retriever, settings):
    service = ChatService(Agent(DemoModel(), ToolRegistry(retriever, settings), settings), settings)
    with TestClient(create_app(service)) as client:
        assert client.get("/health").json()["mode"] == "demo"
        identity = str(uuid4())
        response = client.post(
            "/chat", json={"message": "path parameter braces", "session_id": identity}
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(response.text)
        assert events[0][0] == "meta" and events[-1][0] == "done"
        assert events[-1][1]["abstained"] is False
        assert (
            "".join(data["text"] for event, data in events if event == "token")
            == events[-1][1]["answer"]
        )
        assert len(service.sessions.sessions[identity].messages()) == 2
        second = client.post("/chat", json={"message": "qwertyxyz"})
        second_events = parse_sse(second.text)
        assert second_events[0][1]["session_id"] != identity
        assert second_events[-1][1]["abstained"]
        assert client.post("/chat", json={"message": " "}).status_code == 422
        assert client.post("/chat", json={"message": "x", "session_id": "bad"}).status_code == 422
        assert client.post("/chat", json={"message": "x" * 4001}).status_code == 422


def test_missing_index_returns_actionable_503(settings):
    with TestClient(create_app(settings=settings)) as client:
        assert client.get("/health").status_code == 503
        assert client.post("/chat", json={"message": "hello"}).status_code == 503


def test_request_deadline_has_terminal_error_and_no_memory(settings):
    import asyncio

    from tests.conftest import FakeTools

    class SlowModel:
        async def complete(self, *args):
            await asyncio.sleep(10)

    settings = settings.model_copy(update={"request_timeout": 0.01})
    service = ChatService(Agent(SlowModel(), FakeTools(), settings), settings)
    with TestClient(create_app(service)) as client:
        events = parse_sse(client.post("/chat", json={"message": "hello"}).text)
    assert events[-1] == ("error", {"code": "request_timeout", "retryable": True})
    assert not any(event == "done" for event, _ in events)
    assert not next(iter(service.sessions.sessions.values())).messages()
