import asyncio
import json
from contextlib import asynccontextmanager, suppress
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import Settings
from app.service import build_service


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID | None = None

    @field_validator("message")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Message is blank")
        return value.strip()


def encode_sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def create_app(service=None, settings=None):
    @asynccontextmanager
    async def lifespan(application):
        application.state.service = service
        application.state.startup_error = None
        if service is None:
            try:
                application.state.service = await asyncio.to_thread(
                    build_service, settings or Settings.from_env()
                )
            except Exception:
                application.state.startup_error = (
                    "Run ingestion and check local configuration; see README."
                )
        yield
        if service is None and application.state.service:
            await application.state.service.close()

    application = FastAPI(title="FastAPI Docs Q&A Agent", lifespan=lifespan)

    @application.get("/health")
    async def health():
        active = application.state.service
        if not active:
            return JSONResponse(
                {"status": "not_ready", "detail": application.state.startup_error}, status_code=503
            )
        return {
            "status": "ok",
            "mode": active.settings.app_mode,
            "index_version": active.agent.tools.retriever.version,
        }

    @application.post("/chat")
    async def chat(body: ChatRequest):
        active = application.state.service
        if active is None:
            return JSONResponse(
                {"error": "not_ready", "detail": application.state.startup_error}, status_code=503
            )
        session_id = str(body.session_id or uuid4())

        async def stream():
            queue = asyncio.Queue(maxsize=256)

            async def produce():
                try:
                    async for event, data in active.stream(body.message, session_id):
                        await queue.put((event, data))
                except TimeoutError:
                    await queue.put(("error", {"code": "request_timeout", "retryable": True}))
                except Exception:
                    await queue.put(("error", {"code": "request_failed", "retryable": True}))
                await queue.put(None)

            task = asyncio.create_task(produce())
            try:
                yield encode_sse(
                    "meta", {"session_id": session_id, "mode": active.settings.app_mode}
                )
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), 10)
                    except TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    if item is None:
                        break
                    yield encode_sse(*item)
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    return application


app = create_app()
