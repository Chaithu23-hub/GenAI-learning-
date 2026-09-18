import json

from legal_assistant.generation.pipeline import answer_question
from legal_assistant.evaluation.judges import score_answer_on_problem_type

PROBLEM1_TEST_CASES = [
    {
        "name": "Trace 2: Takings Clause",
        "question": "Can the government take my property?",
        "problem_type": "shallow_answer",
        "required_concepts": ["public", "compensation"],
    },
    {
        "name": "Trace 6: Right to Remain Silent",
        "question": "What is the right to remain silent?",
        "problem_type": "shallow_answer",
        "required_concepts": ["remain silent", "self-incrimination"],
    },
    {
        "name": "Trace 11: Reconstruction Amendments",
        "question": "What did the Reconstruction era amendments accomplish?",
        "problem_type": "shallow_answer",
        "required_concepts": ["13th", "14th", "15th"],
    },
    {
        "name": "Trace 14: Anti-Federalist Concerns",
        "question": "Why did Anti-Federalists demand the Bill of Rights?",
        "problem_type": "shallow_answer",
        "required_concepts": ["feared", "government"],
    },
    {
        "name": "Trace 15: Reserved Powers",
        "question": "What powers do states keep under the Constitution?",
        "problem_type": "shallow_answer",
        "required_concepts": ["reserved", "states"],
    },
    {
        "name": "Trace 17: Just Compensation",
        "question": "What's a 'just compensation' in the Takings Clause?",
        "problem_type": "shallow_answer",
        "required_concepts": ["compensation", "property"],
    },
]


def test_case(question, problem_type="shallow_answer"):
    payload = answer_question(question, backend="extractive")
    score_dict = score_answer_on_problem_type(payload, problem_type)
    return {
        "question": question,
        "answer_length": len(payload.get("answer", "")),
        "confidence": payload.get("confidence", "unknown"),
        "score": score_dict["score"],
        "sources": len(payload.get("sources", [])),
        "out_of_scope": payload.get("out_of_scope", False),
    }


def run_validation():
    print("\n" + "=" * 80)
    print("SHALLOW ANSWER VALIDATION")
    print("Fix target: Problem 1 - Shallow/Thin Answers")
    print("=" * 80)

    print("\nTesting 6 Problem 1 cases...")
    print("-" * 80)

    results = []
    for test_case_info in PROBLEM1_TEST_CASES:
        result = test_case(test_case_info["question"], test_case_info["problem_type"])
        results.append({"name": test_case_info["name"], **result})
        print(f"\n{test_case_info['name']}")
        print(f"  Question: {test_case_info['question'][:60]}...")
        print(
            f"  Score: {result['score']}/10  Confidence: {result['confidence']}  "
            f"Answer length: {result['answer_length']} chars"
        )

    average_score = sum(result["score"] for result in results) / len(results)
    print(f"\nAverage score: {average_score:.1f}/10")
    return results


if __name__ == "__main__":
    results = run_validation()
    print("\n" + json.dumps({
        "problem": "Problem 1: Shallow/Thin Answers",
        "test_cases": results,
        "metric": "Average confidence calibration and score distribution",
    }, indent=2))
