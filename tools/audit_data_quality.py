"""Reproducible coverage and provenance audit of the actual Excel dataset."""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from answer_engine import normalize, phones, topics
from prepare_vector_db import read_training, file_digest

CORE_TOPICS = ('giá', 'chip', 'RAM', 'bộ nhớ', 'màn hình', 'camera', 'pin')


def audit(source, output):
    records, incomplete = read_training(source)
    by_question = defaultdict(list)
    by_phone = defaultdict(list)
    issues = []
    for record in records:
        by_question[normalize(record['question'])].append(record)
        for phone in phones(record['question']):
            by_phone[phone].append(record)
        if not record['reference_url']:
            issues.append({'row': record['row'], 'issue': 'missing_reference', 'question': record['question']})
    for record in incomplete:
        issues.append({'row': record['row'], 'issue': 'missing_answer', 'question': record['question']})
    conflicts = []
    for group in by_question.values():
        if len({normalize(row['answer']) for row in group}) > 1:
            conflicts.append([row['row'] for row in group])
    coverage = []
    for phone, group in sorted(by_phone.items()):
        found = set().union(*(topics(row['question']) for row in group))
        sourced = set().union(*(topics(row['question']) for row in group if row['reference_url']))
        coverage.append({
            'phone': phone, 'faq_rows': len(group),
            'missing_topics': ' | '.join(topic for topic in CORE_TOPICS if topic not in found),
            'topics_without_reference': ' | '.join(topic for topic in CORE_TOPICS if topic not in sourced),
        })
    test_path = source.parent / 'test_cleaned.json'
    tests = json.loads(test_path.read_text(encoding='utf-8')) if test_path.is_file() else []
    overlap = [case['test_id'] for case in tests if normalize(case['question']) in by_question]
    summary = {
        'source_sha256': file_digest(source), 'complete_pairs': len(records),
        'incomplete_pairs': len(incomplete), 'rows_with_reference': sum(bool(r['reference_url']) for r in records),
        'rows_without_reference': sum(not r['reference_url'] for r in records),
        'recognized_phone_variants': len(by_phone), 'conflicting_duplicate_rows': conflicts,
        'phones_missing_core_topics': sum(bool(row['missing_topics']) for row in coverage),
        'test_questions': len(tests), 'test_exact_question_overlap': overlap,
        'interpretation': 'Topic coverage is detected from question text. A URL does not establish factual correctness or current pricing. Test overlap describes retrieval regression, not unseen-question accuracy.',
    }
    output.mkdir(parents=True, exist_ok=True)
    for name, rows, fields in (
        ('data_issues.csv', issues, ['row', 'issue', 'question']),
        ('phone_coverage.csv', coverage, ['phone', 'faq_rows', 'missing_topics', 'topics_without_reference']),
    ):
        with (output / name).open('w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    (output / 'data_quality.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=BASE / 'evaluation')
    args = parser.parse_args()
    print(json.dumps(audit(BASE / 'data/data1.xlsx', args.out), ensure_ascii=False, indent=2))
