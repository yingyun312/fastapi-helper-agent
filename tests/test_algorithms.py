import json
from dataclasses import replace

import pytest

from app.bm25 import BM25Index, tokenize
from app.cache import LRUCache
from app.chunker import chunk_document
from app.loader import load_documents
from app.retriever import reciprocal_rank_fusion
from scripts.fetch_docs import expand_includes


def test_chunk_empty_short_and_stable(document):
    assert chunk_document(replace(document, text="")) == []
    chunks = chunk_document(document)
    assert len(chunks) == 1
    assert chunks == chunk_document(document)
    assert chunks[0].source == document.source
    assert chunks[0].start_line == 1


def test_chunk_window_coverage_and_overlap(document):
    text = "abcdefghijklmnopqrstuvwxyz" * 10
    chunks = chunk_document(replace(document, text=text), size=50, overlap=10)
    assert all(len(chunk.text) <= 50 for chunk in chunks)
    reconstructed = chunks[0].text + "".join(chunk.text[10:] for chunk in chunks[1:])
    assert reconstructed == text


@pytest.mark.parametrize("fence", ["```", "~~~~"])
def test_chunk_code_is_atomic_and_headings_are_not_code(document, fence):
    code = fence + "python\n# Not a heading\n" + "print('x')\n" * 30 + fence + "\n"
    text = "# Heading\nIntro\n" + code + "\n## Next\nNext paragraph\n"
    chunks = chunk_document(replace(document, text=text), size=80, overlap=10)
    assert len(chunks) <= 4
    assert any(code in chunk.text for chunk in chunks)
    assert all("Not a heading" != chunk.heading for chunk in chunks)
    assert {chunk.heading for chunk in chunks} == {"Heading", "Next"}
    assert all(chunk.text.count(fence) in {0, 2} for chunk in chunks)


def test_unclosed_code_and_invalid_window(document):
    text = "# H\n```python\n" + "print(1)\n" * 40
    assert any(
        "print(1)\n" * 40 in chunk.text
        for chunk in chunk_document(replace(document, text=text), 50, 5)
    )
    with pytest.raises(ValueError):
        chunk_document(document, 20, 20)


def test_bm25_save_load_relevance_and_empty(tmp_path):
    index = BM25Index().build(
        {"a": "Depends dependency injection", "b": "CORS middleware", "c": ""}
    )
    assert index.search("Depends")[0][0] == "a"
    assert index.search("zzzzzz") == []
    index.save(tmp_path / "index.json")
    restored = BM25Index.load(tmp_path / "index.json")
    assert restored.postings["depends"] == {"a": 1}
    assert restored.search("dependency Depends") == index.search("dependency Depends")
    assert BM25Index().build({}).search("anything") == []
    assert index.search("Depends", 0) == []
    assert "response_model" in tokenize("response_model")
    assert "background" in tokenize("BackgroundTasks")


def test_rrf_duplicates_and_rank_positions():
    result = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], 2)
    assert result[0][0] == "b"
    assert result[0][1] == pytest.approx(1 / 62 + 1 / 61)
    assert reciprocal_rank_fusion([["a", "a"]])[0][1] == pytest.approx(1 / 61)
    assert reciprocal_rank_fusion([], 5) == []


def test_lru_eviction_update_expiration_and_zero_capacity():
    now = [0]
    cache = LRUCache(2, 10, clock=lambda: now[0])
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert cache.get("b") is None
    cache.put("a", 4)
    assert cache.get("a") == 4
    assert len(cache) == 2
    now[0] = 10
    assert cache.get("a") is None
    assert cache.head.next.previous is cache.head
    assert cache.tail.previous.next is cache.tail
    zero = LRUCache(0, 1)
    zero.put("a", 1)
    assert zero.get("a") is None


def test_loader_checks_provenance(small_index, tmp_path):
    raw, _ = small_index
    assert len(load_documents(raw)) == 2
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "commit": "x",
                "files": [
                    {"path": "../../outside.md", "sha256": "wrong", "url": "https://example.test"}
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="escapes"):
        load_documents(tmp_path)
    (tmp_path / "bad.md").write_text("modified")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "commit": "x",
                "files": [{"path": "bad.md", "sha256": "wrong", "url": "https://example.test"}],
            }
        )
    )
    with pytest.raises(ValueError, match="checksum"):
        load_documents(tmp_path)


def test_official_code_include_expansion():
    text = "{* ../../docs_src/path/tutorial.py hl[1:2] *}"
    expanded, sources = expand_includes(text, lambda path: b"print('hi')\n", "abc")
    assert "```python\nprint('hi')\n```" in expanded
    assert sources[0]["path"] == "docs_src/path/tutorial.py"
