import heapq
import json
from collections import defaultdict
from pathlib import Path

from app.bm25 import BM25Index
from app.models import Chunk, Hit
from app.vector_store import VectorStore


def reciprocal_rank_fusion(rankings: list[list[str]], top_k=5, constant=60):
    if constant <= 0:
        raise ValueError("RRF constant must be positive")
    scores = defaultdict(float)
    for ranking in rankings:
        seen = set()
        for rank, identity in enumerate(ranking, 1):
            if identity not in seen:
                scores[identity] += 1 / (constant + rank)
                seen.add(identity)
    return heapq.nsmallest(max(0, top_k), scores.items(), key=lambda pair: (-pair[1], pair[0]))


class Retriever:
    def __init__(self, index_dir: Path, embedder):
        pointer = json.loads((index_dir / "current.json").read_text(encoding="utf-8"))
        root = (index_dir / "generations" / pointer["generation"]).resolve()
        if not root.is_relative_to((index_dir / "generations").resolve()):
            raise ValueError("Invalid index generation")
        self.manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        if self.manifest["embedding_signature"] != embedder.signature:
            raise ValueError("Embedding configuration differs from index; run ingestion again")
        self.version = self.manifest["version"]
        self.chunks = {
            row["id"]: Chunk(**row)
            for row in json.loads((root / "chunks.json").read_text(encoding="utf-8"))
        }
        self.bm25 = BM25Index.load(root / "bm25.json")
        self.vector = VectorStore(root / "chroma")
        self.embedder = embedder
        if set(self.bm25.lengths) != set(self.chunks) or self.vector.collection.count() != len(
            self.chunks
        ):
            raise ValueError("Incomplete index generation")

    def search(self, query: str, mode="hybrid", top_k=5) -> tuple[list[Hit], list[str]]:
        if mode not in {"bm25", "vector", "hybrid"}:
            raise ValueError("Unknown retrieval mode")
        candidates = max(20, top_k * 4)
        lexical, semantic, warnings = [], [], []
        if mode != "vector":
            lexical = self.bm25.search(query, candidates)
        if mode != "bm25":
            try:
                semantic = self.vector.search(self.embedder.embed([query])[0], candidates)
            except Exception:
                if mode == "vector":
                    raise
                warnings.append("vector_unavailable_using_bm25")
        if mode == "hybrid":
            ranking = reciprocal_rank_fusion(
                [[key for key, _ in lexical], [key for key, _ in semantic]], top_k
            )
        else:
            ranking = (lexical if mode == "bm25" else semantic)[:top_k]
        lexical_scores, similarities = dict(lexical), dict(semantic)
        return [
            Hit(self.chunks[key], score, lexical_scores.get(key, 0), similarities.get(key))
            for key, score in ranking
        ], warnings
