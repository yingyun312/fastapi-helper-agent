from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.models import Chunk


class VectorStore:
    def __init__(self, path: Path, *, create=False):
        self.client = chromadb.PersistentClient(
            path=str(path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        if create:
            self.collection = self.client.create_collection(
                "chunks",
                embedding_function=None,
                metadata={"hnsw:space": "cosine"},
            )
        else:
            self.collection = self.client.get_collection("chunks", embedding_function=None)

    def add(self, chunks: list[Chunk], vectors: list[list[float]]):
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and embedding counts differ")
        for start in range(0, len(chunks), 128):
            batch = chunks[start : start + 128]
            self.collection.add(
                ids=[chunk.id for chunk in batch],
                embeddings=vectors[start : start + 128],
                documents=[chunk.text for chunk in batch],
                metadatas=[
                    {
                        key: value
                        for key, value in chunk.to_dict().items()
                        if key not in {"id", "text"}
                    }
                    for chunk in batch
                ],
            )

    def search(self, vector: list[float], top_k: int):
        count = self.collection.count()
        if count == 0 or top_k <= 0:
            return []
        result = self.collection.query(
            query_embeddings=[vector], n_results=min(top_k, count), include=["distances"]
        )
        return [
            (identity, 1.0 - distance)
            for identity, distance in zip(result["ids"][0], result["distances"][0], strict=True)
        ]
