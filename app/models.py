from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Document:
    text: str
    source: str
    title: str
    url: str
    version: str


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str
    title: str
    heading: str
    url: str
    version: str
    start_line: int
    end_line: int

    def to_dict(self):
        return asdict(self)


@dataclass
class Hit:
    chunk: Chunk
    score: float
    bm25_score: float = 0.0
    similarity: float | None = None


@dataclass
class Evidence:
    id: str
    text: str
    source: str
    title: str
    url: str
    version: str
    kind: str = "document"
    heading: str = ""
    start_line: int = 0
    end_line: int = 0
    retrieved_at: str = ""
    score: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class ToolResult:
    evidence: list[Evidence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self):
        return asdict(self)
