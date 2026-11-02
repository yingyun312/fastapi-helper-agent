import hashlib
import re

from app.models import Chunk, Document


def _sections(text: str):
    """Find headings outside fenced code; retain original line positions."""
    heading = "Introduction"
    lines = []
    first = 1
    fence = None
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
        match = re.match(r"^(#{1,6})\s+(.+)", line) if fence is None else None
        if match:
            if lines:
                yield heading, first, "".join(lines)
            heading, first, lines = match.group(2).strip(), number, []
        lines.append(line)
    if lines:
        yield heading, first, "".join(lines)


def fenced_code_spans(text: str):
    spans = []
    offset, start, fence = 0, 0, None
    for line in text.splitlines(keepends=True):
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            token = match.group(1)
            if fence is None:
                start, fence = offset, token
            elif token[0] == fence[0] and len(token) >= len(fence):
                spans.append((start, offset + len(line)))
                fence = None
        offset += len(line)
    if fence is not None:
        spans.append((start, len(text)))
    return spans


def chunk_document(document: Document, size: int = 1400, overlap: int = 200) -> list[Chunk]:
    """Slide within sections. Oversized fenced blocks stay whole (a soft size limit)."""
    if size < 1 or overlap < 0 or overlap >= size:
        raise ValueError("Require 0 <= overlap < size")
    chunks = []
    for heading, first, text in _sections(document.text):
        spans = fenced_code_spans(text)
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            for left, right in spans:
                if left < end < right:
                    end = left if left > start else right
                    break
            part = text[start:end]
            if part.strip():
                first_line = first + text[:start].count("\n")
                last_line = first + text[:end].rstrip("\n").count("\n")
                identity = f"{document.version}:{document.source}:{first}:{start}:{part}"
                chunks.append(
                    Chunk(
                        id=hashlib.sha256(identity.encode()).hexdigest()[:24],
                        text=part,
                        source=document.source,
                        title=document.title,
                        heading=heading,
                        url=document.url,
                        version=document.version,
                        start_line=first_line,
                        end_line=last_line,
                    )
                )
            if end == len(text):
                break
            next_start = end if end - start <= overlap else end - overlap
            for left, right in spans:
                if left < next_start < right:
                    next_start = left if left > start else right
                    break
            start = next_start
    return chunks
