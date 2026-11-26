"""Measured, reproducible audit; does not label lexical similarity as accuracy."""
import csv
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from answer_engine import normalize
from prepare_vector_db import DATA_FILE, read_training

parser = argparse.ArgumentParser()
parser.add_argument('--out', default='evaluation')
args = parser.parse_args()
OUT = BASE / args.out
OUT.mkdir(parents=True, exist_ok=True)

import app  # noqa: E402: data paths and runtime are initialized by the app
model_requests = [0]
original_get_model = app.get_model
def measured_get_model():
    model_requests[0] += 1
    return original_get_model()
app.get_model = measured_get_model

records, incomplete = read_training(DATA_FILE)
known = {record["row"]: record for record in records}
tests = json.loads((BASE / "data" / "test_cleaned.json").read_text(encoding="utf-8"))
measured = []
for case in tests:
    start = time.perf_counter()
    calls_before = model_requests[0]
    try:
        answer, rows = app.answer_question(case["question"])
        error = ""
    except Exception as exc:
        answer, rows, error = "", [], type(exc).__name__
    seconds = round(time.perf_counter() - start, 3)
    references = [known[row]["reference_url"] for row in rows if row in known and known[row].get("reference_url")]
    measured.append({
        "test_id": case["test_id"], "question": case["question"],
        "expected_answer": case["expected_answer"], "actual_answer": answer,
        "source_rows": ",".join(map(str, rows)),
        "reference_urls": " | ".join(dict.fromkeys(references)),
        "duration_seconds": seconds, "error": error,
        "requested_llm": model_requests[0] > calls_before,
        "exact_text_match": bool(answer and normalize(answer) == normalize(case["expected_answer"])),
    })
    print(f"{len(measured)}/{len(tests)} test_id={case['test_id']} {seconds:.3f}s rows={len(rows)}", flush=True)

with (OUT / "test_33_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(measured[0]))
    writer.writeheader()
    writer.writerows(measured)

source_count = sum(bool(record.get("reference_url")) for record in records)
summary = {
    "training_complete": len(records),
    "training_incomplete": len(incomplete),
    "training_rows_with_reference_url": source_count,
    "training_rows_without_reference_url": len(records) - source_count,
    "test_questions": len(tests),
    "test_errors": sum(bool(item["error"]) for item in measured),
    "test_answers_with_internal_source_rows": sum(bool(item["source_rows"]) for item in measured),
    "test_answers_with_external_reference_url": sum(bool(item["reference_urls"]) for item in measured),
    "test_exact_text_matches": sum(item["exact_text_match"] for item in measured),
    "test_questions_requesting_llm": sum(item["requested_llm"] for item in measured),
    "response_median_seconds": round(statistics.median(item["duration_seconds"] for item in measured), 3),
    "response_p95_seconds": round(sorted(item["duration_seconds"] for item in measured)[min(len(measured)-1, int(len(measured)*.95))], 3),
    "note": "Exact text match is not factual accuracy. This is a regression set used during development, not an independent benchmark. Some expected answers remain unverified; manual fact review is required. Timing covers answer_question only, not browser, HTTP or database persistence.",
}
(OUT / "evaluation_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
