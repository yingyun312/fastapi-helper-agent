"""Download a small, versioned subset of the official FastAPI Markdown corpus."""

import argparse
import hashlib
import io
import json
import posixpath
import re
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import ROOT

PAGES = [
    "tutorial/first-steps.md",
    "tutorial/path-params.md",
    "tutorial/query-params.md",
    "tutorial/body.md",
    "tutorial/query-params-str-validations.md",
    "tutorial/path-params-numeric-validations.md",
    "tutorial/body-fields.md",
    "tutorial/response-model.md",
    "tutorial/response-status-code.md",
    "tutorial/handling-errors.md",
    "tutorial/dependencies/index.md",
    "tutorial/dependencies/dependencies-with-yield.md",
    "tutorial/background-tasks.md",
    "tutorial/cors.md",
    "tutorial/middleware.md",
    "tutorial/testing.md",
    "tutorial/request-files.md",
    "tutorial/request-forms.md",
    "tutorial/security/first-steps.md",
    "tutorial/bigger-applications.md",
    "advanced/events.md",
    "async.md",
    "tutorial/encoder.md",
    "tutorial/sql-databases.md",
]


def download(client, url, max_bytes=40_000_000):
    data = bytearray()
    with client.stream("GET", url) as response:
        response.raise_for_status()
        for block in response.iter_bytes():
            data.extend(block)
            if len(data) > max_bytes:
                raise ValueError("Download exceeds size limit")
    return bytes(data)


def expand_includes(text, read_file, commit):
    included = []

    def replace(match):
        path = match.group(1)
        if "docs_src/" not in path:
            return match.group(0)
        path = "docs_src/" + path.split("docs_src/", 1)[1]
        path = posixpath.normpath(path)
        if not path.startswith("docs_src/"):
            raise ValueError("Invalid code include")
        code = read_file(path).decode("utf-8")
        digest = hashlib.sha256(code.encode()).hexdigest()
        included.append({"path": path, "sha256": digest})
        fence = "`" * max(3, max((len(item) + 1 for item in re.findall(r"`+", code)), default=3))
        return (
            f"\nCode source: https://github.com/fastapi/fastapi/blob/{commit}/{path}\n\n"
            f"{fence}python\n{code.rstrip()}\n{fence}\n"
        )

    text = re.sub(r"\{\*\s*([^\s]+)(?:[^}]*?)\*\}", replace, text)
    text = re.sub(r'--8<--\s*["\']([^"\']+)["\']', replace, text)
    return text, included


def fetch(output: Path, ref="0.115.6", limit=24):
    if output.exists():
        raise ValueError("Output already exists; choose a new directory to preserve the snapshot")
    if not 1 <= limit <= len(PAGES):
        raise ValueError(f"Limit must be between 1 and {len(PAGES)}")
    with httpx.Client(
        timeout=60, follow_redirects=True, headers={"User-Agent": "fastapi-helper-agent"}
    ) as client:
        response = client.get(
            f"https://api.github.com/repos/fastapi/fastapi/commits/{quote(ref, safe='')}"
        )
        response.raise_for_status()
        commit = response.json()["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Invalid commit returned by GitHub")
        archive = download(client, f"https://codeload.github.com/fastapi/fastapi/tar.gz/{commit}")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        prefix = bundle.getmembers()[0].name.split("/")[0] + "/"

        def read_file(path):
            member = bundle.getmember(prefix + path)
            if not member.isfile() or member.size > 2_000_000:
                raise ValueError("Invalid source file")
            return bundle.extractfile(member).read()

        files = []
        prepared = {}
        for page in PAGES[:limit]:
            original = read_file("docs/en/docs/" + page)
            text, includes = expand_includes(original.decode("utf-8"), read_file, commit)
            prepared[page] = text
            files.append(
                {
                    "path": page,
                    "url": f"https://github.com/fastapi/fastapi/blob/{commit}/docs/en/docs/{page}",
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "original_sha256": hashlib.sha256(original).hexdigest(),
                    "includes": includes,
                }
            )
        license_text = read_file("LICENSE")
    output.mkdir(parents=True)
    for page, text in prepared.items():
        path = output / page
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (output / "LICENSE").write_bytes(license_text)
    manifest = {
        "repository": "https://github.com/fastapi/fastapi",
        "ref": ref,
        "commit": commit,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "license": "MIT",
        "preparation": "Official Markdown with docs_src code includes expanded; line numbers refer to prepared files",
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "files": files,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/official-sample")
    parser.add_argument("--ref", default="0.115.6")
    parser.add_argument("--limit", type=int, default=24)
    args = parser.parse_args()
    manifest = fetch(args.output, args.ref, args.limit)
    print(
        json.dumps(
            {
                "ref": manifest["ref"],
                "commit": manifest["commit"],
                "documents": len(manifest["files"]),
            }
        )
    )
