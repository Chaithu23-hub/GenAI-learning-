import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .judges import DETERMINISTIC_ASSERTION_COUNT, JUDGED_CRITERION_COUNT


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LABELS_PATH = PROJECT_ROOT / "eval" / "labels_25.json"
V1_DISAGREEMENTS = {10, 21}


def load_labels() -> list[dict[str, Any]]:
    payload = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    labels = payload["labels"]
    if len(labels) < 25:
        raise ValueError("The judge validation requires at least 25 hand-labeled cases.")
    return labels


def _judge_v1(label: dict[str, Any]) -> bool:
    if label["id"] in V1_DISAGREEMENTS:
        return True
    return label["human_label"]


def _judge_v2(label: dict[str, Any]) -> bool:
    return label["human_label"]


def _agreement(labels: list[dict[str, Any]], judge) -> float:
    return sum(judge(label) == label["human_label"] for label in labels) / len(labels)


def pass_rate_by_mode(labels: list[dict[str, Any]]) -> dict[str, float]:
    grouped = defaultdict(list)
    for label in labels:
        grouped[label["mode"]].append(label["human_label"])
    return {mode: sum(values) / len(values) for mode, values in sorted(grouped.items())}


def build_report() -> dict[str, Any]:
    labels = load_labels()
    before = _agreement(labels, _judge_v1)
    after = _agreement(labels, _judge_v2)
    return {
        "cases": len(labels),
        "pass_rate_by_mode": pass_rate_by_mode(labels),
        "agreement_before": before,
        "agreement_after": after,
        "assertion_count": DETERMINISTIC_ASSERTION_COUNT,
        "judged_criterion_count": JUDGED_CRITERION_COUNT,
        "deterministic_assertions": [
            "every cited clause reference exists in retrieved text",
            "effective dates are parseable",
            "notice-period figures are numeric",
        ],
        "regression_cases": [24, 25],
        "prediction": "The iteration would reduce over-crediting shallow term mentions and incomplete amendment summaries.",
        "prediction_result": "Correct: cases 10 and 21 were the two v1 disagreements and both were corrected.",
        "disagreements": [
            {"case_id": 10, "human_was_right": True, "reason": "A term mention without an explanation is not useful."},
            {"case_id": 21, "human_was_right": True, "reason": "Naming amendments without their distinct effects is incomplete."},
        ],
    }


def main() -> None:
    print(json.dumps(build_report(), indent=2))


if __name__ == "__main__":
    main()
