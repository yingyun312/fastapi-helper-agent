import hashlib
import json
import re
from pathlib import Path

from app.models import Document


def load_documents(root: Path) -> list[Document]:
    """Load only files declared in a provenance manifest, checking their hashes."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    documents = []
    for entry in manifest["files"]:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Document path escapes corpus directory")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError(f"Document checksum mismatch: {entry['path']}")
        text = raw.decode("utf-8")
        title = re.search(r"^#\s+(.+)", text, flags=re.MULTILINE)
        documents.append(
            Document(
                text=text,
                source=entry["path"],
                title=title.group(1) if title else path.stem,
                url=entry["url"],
                version=manifest["commit"],
            )
        )
    if not documents:
        raise ValueError("The corpus contains no documents")
    return documents
