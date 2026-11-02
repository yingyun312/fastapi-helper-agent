import hashlib
import math
from collections import Counter

from openai import OpenAI

from app.bm25 import tokenize
from app.config import Settings


class HashEmbedder:
    """Deterministic lexical test double. This is NOT a semantic embedding model."""

    signature = "demo-hash-v1-384"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 384
            for word, count in Counter(tokenize(text)).items():
                digest = hashlib.sha256(word.encode()).digest()
                bucket = int.from_bytes(digest[:4], "big") % len(vector)
                vector[bucket] += count * (1 if digest[4] % 2 else -1)
            length = math.sqrt(sum(value * value for value in vector)) or 1
            vectors.append([value / length for value in vector])
        return vectors

    def close(self):
        pass


class APIEmbedder:
    def __init__(self, settings: Settings, client=None):
        if client is None and not settings.embedding_api_key.get_secret_value():
            raise ValueError("EMBEDDING_API_KEY is required in live mode")
        self.client = client or OpenAI(
            api_key=settings.embedding_api_key.get_secret_value(),
            base_url=settings.embedding_base_url,
            timeout=settings.tool_timeout,
            max_retries=0,
        )
        self.model = settings.embedding_model
        identity = f"{settings.embedding_base_url.rstrip('/')}:{self.model}"
        self.signature = "api-v1-" + hashlib.sha256(identity.encode()).hexdigest()[:20]

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for start in range(0, len(texts), 32):
            batch = texts[start : start + 32]
            result = self.client.embeddings.create(model=self.model, input=batch)
            rows = sorted(result.data, key=lambda row: row.index)
            if [row.index for row in rows] != list(range(len(batch))):
                raise ValueError("Embedding response has missing or duplicate rows")
            vectors.extend(row.embedding for row in rows)
        if vectors:
            dimension = len(vectors[0])
            if not dimension or any(
                len(vector) != dimension or not all(math.isfinite(value) for value in vector)
                for vector in vectors
            ):
                raise ValueError("Embedding response has invalid vectors")
        return vectors

    def close(self):
        self.client.close()


def make_embedder(settings: Settings):
    return HashEmbedder() if settings.app_mode == "demo" else APIEmbedder(settings)
