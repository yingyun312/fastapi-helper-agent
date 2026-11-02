import pytest

from app.config import ROOT
from eval.run_eval import load_questions, retrieval_metrics


def test_metrics_with_multiple_relevant_pages_and_duplicate_chunks():
    values = retrieval_metrics(["wrong", "a", "a", "b", "other"], ["a", "b", "c"])
    assert values["recall_at_5"] == pytest.approx(2 / 3)
    assert values["mrr"] == 0.5
    assert retrieval_metrics(["x"], ["a"])["mrr"] == 0


def test_fifty_questions_with_explicit_pending_labels():
    questions = load_questions(ROOT / "eval/questions.jsonl")
    assert len(questions) == 50
    assert sum(item["kind"] == "docs" for item in questions) == 35
    assert sum(item["kind"] == "community" for item in questions) == 5
    assert sum(item["kind"] == "no_answer" for item in questions) == 10
    assert all(item["label_status"] == "pending_human_review" for item in questions)


async def test_unreviewed_labels_are_excluded_by_default(settings, small_index, tmp_path):
    from eval.run_eval import evaluate

    settings = settings.model_copy(update={"index_dir": small_index[1]})
    questions = load_questions(ROOT / "eval/questions.jsonl")
    report = await evaluate(settings, questions, tmp_path / "eval-output")
    assert report["selected_questions"] == 0
    assert report["excluded_unreviewed"] == 50
    assert report["retrieval"]["bm25"]["recall_at_5"] is None
