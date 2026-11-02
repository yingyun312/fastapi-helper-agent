import json

import pytest

from app.embedder import HashEmbedder
from app.retriever import Retriever
from scripts.ingest import ingest


@pytest.mark.parametrize("mode", ["bm25", "vector", "hybrid"])
def test_real_chroma_roundtrip(retriever, mode):
    hits, warnings = retriever.search("path parameter braces", mode, 2)
    assert not warnings
    assert hits[0].chunk.source == "path.md"
    assert hits[0].chunk.version == "test-v1"


def test_embedding_mismatch_rejected(small_index):
    embedder = HashEmbedder()
    embedder.signature = "different-model"
    with pytest.raises(ValueError, match="differs"):
        Retriever(small_index[1], embedder)


def test_hybrid_degrades_but_vector_eval_fails(retriever, monkeypatch):
    def fail(text):
        raise RuntimeError("provider failed")

    monkeypatch.setattr(retriever.embedder, "embed", fail)
    hits, warnings = retriever.search("path parameter", "hybrid")
    assert hits
    assert warnings == ["vector_unavailable_using_bm25"]
    with pytest.raises(RuntimeError):
        retriever.search("path parameter", "vector")


def test_failed_ingestion_preserves_active_generation(small_index):
    raw, output = small_index
    before = json.loads((output / "current.json").read_text())

    class BrokenEmbedder(HashEmbedder):
        def embed(self, texts):
            raise RuntimeError("failed")

    with pytest.raises(RuntimeError):
        ingest(raw, output, BrokenEmbedder())
    assert json.loads((output / "current.json").read_text()) == before
