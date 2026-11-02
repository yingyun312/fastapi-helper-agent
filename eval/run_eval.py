"""Evaluate retrieval separately from community questions and answer grounding review."""

import argparse
import asyncio
import csv
import hashlib
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.config import ROOT, Settings
from app.service import build_service


def retrieval_metrics(ranked_sources, relevant_sources):
    relevant = set(relevant_sources)
    if not relevant:
        raise ValueError("Retrieval labels must contain at least one relevant source")
    recall = len(set(ranked_sources[:5]) & relevant) / len(relevant)
    reciprocal_rank = next(
        (1 / rank for rank, source in enumerate(ranked_sources, 1) if source in relevant), 0.0
    )
    return {"recall_at_5": recall, "mrr": reciprocal_rank}


def load_questions(path):
    questions = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    ids = [item["id"] for item in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate evaluation IDs")
    for item in questions:
        if item["kind"] not in {"docs", "community", "no_answer"}:
            raise ValueError("Invalid evaluation category")
        if item["label_status"] not in {"pending_human_review", "human_verified"}:
            raise ValueError("Invalid label status")
        if item["kind"] == "docs" and not item["expected_sources"]:
            raise ValueError("Document questions need source labels")
        if item["label_status"] == "human_verified" and not (
            item.get("reviewer") and item.get("reviewed_at")
        ):
            raise ValueError("Verified labels require reviewer and reviewed_at")
    return questions


async def evaluate(
    settings, questions, output, include_unreviewed=False, answers=False, modes=None
):
    service = build_service(settings)
    selected = [
        item for item in questions if include_unreviewed or item["label_status"] == "human_verified"
    ]
    provisional = any(item["label_status"] != "human_verified" for item in selected)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "app_mode": settings.app_mode,
        "embedding_signature": service.agent.tools.retriever.embedder.signature,
        "index_version": service.agent.tools.retriever.version,
        "configuration": settings.model_dump(
            exclude={"deepseek_api_key", "embedding_api_key", "github_token"}, mode="json"
        ),
        "question_set_sha256": hashlib.sha256(
            json.dumps(questions, sort_keys=True).encode()
        ).hexdigest(),
        "implementation_sha256": hashlib.sha256(
            b"".join(
                path.read_bytes()
                for folder in (ROOT / "app", ROOT / "eval")
                for path in sorted(folder.glob("*.py"))
            )
        ).hexdigest(),
        "corpus_ref": service.agent.tools.retriever.manifest["corpus"].get("ref", "test"),
        "label_scope": "provisional_ai_labels" if provisional else "human_verified_only",
        "selected_questions": len(selected),
        "excluded_unreviewed": len(questions) - len(selected),
        "retrieval": {},
        "answers": [],
        "retrieval_rows": [],
        "grounding_review": "pending_human_review",
        "limitations": [
            "Demo vectors are lexical hashes, not semantic embeddings.",
            "Source-page retrieval is measured at chunk rank; duplicate pages consume ranks.",
            "MRR is truncated at the 20 retrieved chunks (MRR@20).",
            "Citation/quote validation does not prove semantic entailment.",
            "Community questions are excluded from offline retrieval metrics.",
        ],
    }
    try:
        for mode in modes or ["vector", "bm25", "hybrid"]:
            rows = []
            for question in selected:
                if question["kind"] != "docs":
                    continue
                start = time.perf_counter()
                row = {"id": question["id"], "mode": mode, "label_status": question["label_status"]}
                try:
                    hits, warnings = await asyncio.to_thread(
                        service.agent.tools.retriever.search, question["question"], mode, 20
                    )
                    ranked = [hit.chunk.source for hit in hits]
                    row.update(retrieval_metrics(ranked, question["expected_sources"]))
                    row.update({"sources": ranked, "warnings": warnings, "error": None})
                except Exception:
                    row.update(
                        {
                            "recall_at_5": 0,
                            "mrr": 0,
                            "sources": [],
                            "warnings": [],
                            "error": "retrieval_unavailable",
                        }
                    )
                row["elapsed_ms"] = (time.perf_counter() - start) * 1000
                rows.append(row)
            report["retrieval"][mode] = {
                "questions": len(rows),
                "failed": sum(bool(row["error"]) for row in rows),
                "degraded": sum(bool(row["warnings"]) for row in rows),
                "recall_at_5": statistics.mean(row["recall_at_5"] for row in rows)
                if rows
                else None,
                "mrr_at_20": statistics.mean(row["mrr"] for row in rows) if rows else None,
                "mean_ms": statistics.mean(row["elapsed_ms"] for row in rows) if rows else None,
            }
            report["retrieval_rows"].extend(rows)
        if answers:
            for question in selected:
                identity = "eval-" + question["id"]
                row = {**question, "human_grounding": "pending", "human_notes": ""}
                try:
                    async with asyncio.timeout(settings.request_timeout):
                        events = [
                            item
                            async for item in service.agent.run(question["question"], [], identity)
                        ]
                    result = events[-1][1]
                    row.update(result)
                    row["steps"] = [data for event, data in events if event == "step"]
                    # Same question, history, and session, without advancing conversation.
                    async with asyncio.timeout(settings.request_timeout):
                        warm = [
                            item
                            async for item in service.agent.run(question["question"], [], identity)
                        ]
                    row["repeat_ms"] = warm[-1][1]["elapsed_ms"]
                    row["repeat_cache_hit"] = warm[-1][1]["cache_hit"]
                except Exception:
                    row.update(
                        {
                            "answer": "",
                            "sources": [],
                            "error": "answer_unavailable",
                            "abstained": None,
                            "repeat_cache_hit": False,
                        }
                    )
                report["answers"].append(row)
            no_answer = [row for row in report["answers"] if row["kind"] == "no_answer"]
            docs = [row for row in report["answers"] if row["kind"] == "docs"]
            report["refusal"] = {
                "no_answer_questions": len(no_answer),
                "refusal_rate": sum(row.get("abstained") is True for row in no_answer)
                / len(no_answer)
                if no_answer
                else None,
                "docs_refusal_rate": sum(row.get("abstained") is True for row in docs) / len(docs)
                if docs
                else None,
                "answer_errors": sum(bool(row.get("error")) for row in report["answers"]),
                "meaning": "Exploratory only until labels and semantic adequacy are reviewed.",
            }
        output.mkdir(parents=True, exist_ok=False)
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with (output / "human_review.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            fields = [
                "id",
                "kind",
                "label_status",
                "question",
                "answer",
                "abstained",
                "sources",
                "human_grounding",
                "human_notes",
            ]
            writer = csv.DictWriter(handle, fields)
            writer.writeheader()
            for row in report["answers"]:
                writer.writerow(
                    {
                        key: json.dumps(row.get(key), ensure_ascii=False)
                        if key == "sources"
                        else row.get(key, "")
                        for key in fields
                    }
                )
    finally:
        await service.close()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=ROOT / "eval/questions.jsonl")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=["demo", "live"])
    parser.add_argument("--index", type=Path)
    parser.add_argument("--include-unreviewed", action="store_true")
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retrieval-modes", nargs="+", choices=["vector", "bm25", "hybrid"])
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    settings = Settings.from_env()
    changes = {}
    if args.mode:
        changes.update(app_mode=args.mode, index_dir=ROOT / f"data/index-{args.mode}")
    if args.index:
        changes["index_dir"] = args.index.resolve()
    settings = settings.model_copy(update=changes)
    questions = load_questions(args.questions)
    if args.limit:
        questions = questions[: args.limit]
    output = args.output or ROOT / "eval/results" / (
        datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    )
    report = asyncio.run(
        evaluate(
            settings, questions, output, args.include_unreviewed, args.answers, args.retrieval_modes
        )
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "mode": report["app_mode"],
                "label_scope": report["label_scope"],
                "retrieval": report["retrieval"],
                "refusal": report.get("refusal"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
