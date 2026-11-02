import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass
class Session:
    turns: deque
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0
    touched: float = field(default_factory=time.monotonic)

    def messages(self):
        return [message.copy() for turn in self.turns for message in turn]

    def append(self, question: str, answer: str):
        self.turns.append(
            ({"role": "user", "content": question}, {"role": "assistant", "content": answer})
        )


class SessionStore:
    """Bounded in-process sessions; same-session turns serialize as a transaction."""

    def __init__(self, turns=6, capacity=256, ttl=3600, clock=time.monotonic):
        self.turns, self.capacity, self.ttl, self.clock = turns, capacity, ttl, clock
        self.sessions: dict[str, Session] = {}

    @asynccontextmanager
    async def acquire(self, session_id: str):
        now = self.clock()
        for key, value in list(self.sessions.items()):
            if not value.users and now - value.touched >= self.ttl:
                del self.sessions[key]
        if session_id not in self.sessions:
            if len(self.sessions) >= self.capacity:
                idle = [
                    (value.touched, key) for key, value in self.sessions.items() if value.users == 0
                ]
                if not idle:
                    raise RuntimeError("session_capacity")
                del self.sessions[min(idle)[1]]
            self.sessions[session_id] = Session(deque(maxlen=self.turns), touched=now)
        session = self.sessions[session_id]
        session.users += 1
        try:
            async with session.lock:
                yield session
        finally:
            session.users -= 1
            session.touched = self.clock()
