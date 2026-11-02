import hashlib
import json

import pytest

from app.config import Settings
from app.embedder import HashEmbedder
from app.models import Document, Evidence, ToolResult
from app.retriever import Retriever
from scripts.ingest import ingest


@pytest.fixture
def settings(tmp_path):
    return Settings(index_dir=tmp_path / "index", min_bm25_score=0.1)


@pytest.fixture
def document():
    return Document(
        "# Path parameters\nDeclare a path parameter using braces and Python type annotations.\n",
        "tutorial/path-params.md",
        "Path parameters",
        "https://example.test/path",
        "test-v1",
    )


@pytest.fixture
def evidence():
    return Evidence(
        "Dabc",
        "Declare a path parameter using braces and Python type annotations.",
        "tutorial/path-params.md",
        "Path parameters",
        "https://example.test/path",
        "test-v1",
    )


class FakeRetriever:
    version = "index-v1"


class FakeTools:
    def __init__(self, evidence=None, result=None):
        self.retriever = FakeRetriever()
        self.evidence = evidence
        self.result = result
        self.calls = []

    async def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return (
            self.result
            if self.result is not None
            else ToolResult(evidence=[self.evidence] if self.evidence else [])
        )


class FakeModel:
    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    async def complete(self, messages, tools):
        self.calls.append(messages.copy())
        item = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(scope="session")
def small_index(tmp_path_factory):
    root = tmp_path_factory.mktemp("corpus")
    raw, output = root / "raw", root / "index"
    raw.mkdir()
    texts = {
        "path.md": "# Path parameters\nDeclare a path parameter using braces and Python type annotations.\n",
        "cors.md": "# CORS\nConfigure allowed origins with CORSMiddleware.\n",
    }
    files = []
    for name, text in texts.items():
        (raw / name).write_text(text)
        files.append(
            {
                "path": name,
                "url": "https://example.test/" + name,
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
        )
    (raw / "manifest.json").write_text(json.dumps({"commit": "test-v1", "files": files}))
    ingest(raw, output, HashEmbedder())
    return raw, output


@pytest.fixture
def retriever(small_index):
    return Retriever(small_index[1], HashEmbedder())
