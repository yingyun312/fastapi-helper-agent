"""Build an immutable generation, then atomically publish its pointer."""

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.bm25 import BM25Index
from app.chunker import chunk_document
from app.config import ROOT, Settings
from app.embedder import make_embedder
from app.loader import load_documents
from app.vector_store import VectorStore


def ingest(raw: Path, output: Path, embedder, size=1400, overlap=200):
    documents = load_documents(raw)
    chunks = [chunk for document in documents for chunk in chunk_document(document, size, overlap)]
    if not chunks:
        raise ValueError("No chunks to index")
    payload = json.dumps([chunk.to_dict() for chunk in chunks], ensure_ascii=False, sort_keys=True)
    version = hashlib.sha256(("pipeline-v1:" + embedder.signature + payload).encode()).hexdigest()
    generation = version[:16] + "-" + uuid4().hex[:8]
    directory = output / "generations" / generation
    directory.mkdir(parents=True)
    (directory / "chunks.json").write_text(payload, encoding="utf-8")
    BM25Index().build({chunk.id: chunk.heading + "\n" + chunk.text for chunk in chunks}).save(
        directory / "bm25.json"
    )
    store = VectorStore(directory / "chroma", create=True)
    for start in range(0, len(chunks), 32):
        batch = chunks[start : start + 32]
        store.add(batch, embedder.embed([chunk.heading + "\n" + chunk.text for chunk in batch]))
    manifest = {
        "version": version,
        "embedding_signature": embedder.signature,
        "documents": len(documents),
        "chunks": len(chunks),
        "chunk_size": size,
        "overlap": overlap,
        "created_at": datetime.now(UTC).isoformat(),
        "corpus": json.loads((raw / "manifest.json").read_text(encoding="utf-8")),
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    pointer = output / f".current-{uuid4().hex}.json"
    pointer.write_text(json.dumps({"generation": generation}), encoding="utf-8")
    os.replace(pointer, output / "current.json")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data/official-sample")
    parser.add_argument("--mode", choices=["demo", "live"], default=None)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--size", type=int, default=1400)
    parser.add_argument("--overlap", type=int, default=200)
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.mode:
        settings = settings.model_copy(update={"app_mode": args.mode})
    output = args.output or (
        ROOT / f"data/index-{settings.app_mode}" if args.mode else settings.index_dir
    )
    embedder = make_embedder(settings)
    try:
        result = ingest(args.raw, output, embedder, args.size, args.overlap)
    finally:
        embedder.close()
    print(
        json.dumps(
            {key: result[key] for key in ["version", "documents", "chunks", "embedding_signature"]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
