import asyncio

from app.agent import Agent
from app.config import Settings
from app.embedder import make_embedder
from app.llm import ChatModel, DemoModel
from app.memory import SessionStore
from app.retriever import Retriever
from app.tools import ToolRegistry


class ChatService:
    def __init__(self, agent: Agent, settings: Settings):
        self.agent, self.settings = agent, settings
        self.sessions = SessionStore(
            settings.history_turns, settings.max_sessions, settings.session_ttl
        )

    async def stream(self, question, session_id):
        async with asyncio.timeout(self.settings.request_timeout):
            async with self.sessions.acquire(session_id) as session:
                async for event, data in self.agent.run(question, session.messages(), session_id):
                    if event == "done":
                        session.append(question, data["answer"])
                    yield event, data

    async def close(self):
        await self.agent.model.close()
        await self.agent.tools.close()
        self.agent.tools.retriever.embedder.close()


def build_service(settings: Settings):
    embedder = make_embedder(settings)
    try:
        retriever = Retriever(settings.index_dir, embedder)
        model = DemoModel() if settings.app_mode == "demo" else ChatModel(settings)
        return ChatService(Agent(model, ToolRegistry(retriever, settings), settings), settings)
    except Exception:
        embedder.close()
        raise
