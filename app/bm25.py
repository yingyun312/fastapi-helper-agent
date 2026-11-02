import heapq
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

STOP_WORDS = set(
    "a an the is are was were of to for in on and or with how do does can i you "
    "what which it this that my me be as by from fastapi".split()
)


def tokenize(text: str) -> list[str]:
    """Keep code identifiers intact; split camelCase and Chinese characters too."""
    words = re.findall(r"[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[\u4e00-\u9fff]", text)
    tokens = []
    for word in words:
        lower = word.lower()
        if lower not in STOP_WORDS:
            tokens.append(lower)
        parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", word).replace("_", " ").lower().split()
        if len(parts) > 1:
            tokens.extend(part for part in parts if part not in STOP_WORDS)
    return tokens


class BM25Index:
    """Term -> {document id: frequency}; only matching postings are scored."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("Invalid BM25 parameters")
        self.k1, self.b = k1, b
        self.postings: dict[str, dict[str, int]] = {}
        self.lengths: dict[str, int] = {}
        self.average_length = 0.0

    def build(self, documents: dict[str, str]):
        postings = defaultdict(dict)
        self.lengths = {}
        for doc_id, text in documents.items():
            counts = Counter(tokenize(text))
            self.lengths[doc_id] = sum(counts.values())
            for term, frequency in counts.items():
                postings[term][doc_id] = frequency
        self.postings = dict(postings)
        self.average_length = sum(self.lengths.values()) / max(len(self.lengths), 1)
        return self

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        if top_k <= 0 or not self.average_length:
            return []
        scores = defaultdict(float)
        total = len(self.lengths)
        for term in set(tokenize(query)):
            posting = self.postings.get(term, {})
            frequency = len(posting)
            idf = math.log(1 + (total - frequency + 0.5) / (frequency + 0.5))
            for doc_id, count in posting.items():
                norm = 1 - self.b + self.b * self.lengths[doc_id] / self.average_length
                scores[doc_id] += idf * count * (self.k1 + 1) / (count + self.k1 * norm)
        return heapq.nsmallest(top_k, scores.items(), key=lambda pair: (-pair[1], pair[0]))

    def save(self, path: Path):
        path.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "k1": self.k1,
                    "b": self.b,
                    "postings": self.postings,
                    "lengths": self.lengths,
                    "average_length": self.average_length,
                }
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.pop("schema") != 1:
            raise ValueError("Unsupported BM25 schema")
        index = cls(data.pop("k1"), data.pop("b"))
        index.postings, index.lengths = data["postings"], data["lengths"]
        index.average_length = data["average_length"]
        return index
