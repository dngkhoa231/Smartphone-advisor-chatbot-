"""Read-only audit of a submission; does not read or print account records."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_vector_db import read_training
from answer_engine import normalize

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024), b''): h.update(block)
    return h.hexdigest()

def audit(base, hash_models=False):
    records, incomplete=read_training(base/'data/data1.xlsx')
    groups=defaultdict(list)
    for r in records: groups[normalize(r['question'])].append(r)
    duplicates=[{'rows':[r['row'] for r in v], 'conflict':len({normalize(r['answer']) for r in v})>1}
                for v in groups.values() if len(v)>1]
    forbidden=[]; candidates=[]
    for p in base.rglob('*'):
        if not p.is_file(): continue
        if any(part in {'.venv','venv','__pycache__','.git'} for part in p.relative_to(base).parts): continue
        rel=str(p.relative_to(base))
        if p.suffix in ['.db','.sqlite','.sqlite3'] or p.name.startswith('.env'):
            forbidden.append(rel)
        if p.suffix in ['.py','.txt','.md','.html','.json']:
            content=p.read_text(encoding='utf-8',errors='replace')
            if re.search(r'mongodb(?:\+srv)?://[^\s\"\']+:[^\s\"\']+@',content):candidates.append(rel)
    models=[]
    for name in ['all-MiniLM-L6-v2.gguf2.f16.gguf','vinallama-7b-chat_q5_0.gguf']:
        p=base/'model'/name
        models.append({'file':name,'present':p.is_file(),'bytes':p.stat().st_size if p.is_file() else 0,
                       'sha256':digest(p) if hash_models and p.is_file() else None})
    manifest=json.loads((base/'vectorstores/db_faiss/source.json').read_text(encoding='utf-8'))
    result={'complete_pairs':len(records),'incomplete_pairs':len(incomplete),
            'with_url':sum(bool(r['reference_url']) for r in records),
            'duplicate_groups':duplicates,'missing_answer_rows':[r['row'] for r in incomplete],
            'forbidden_submission_files':forbidden,'embedded_mongo_credentials':candidates,'models':models,
            'index_matches_excel':manifest['source_sha256']==digest(base/'data/data1.xlsx'),
            'index_document_count_matches':manifest['document_count']==len(records),
            'note':'URL presence is not factual verification. Pattern scanning is not a guarantee that every possible secret is absent.'}
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',nargs='?',default='.')
    parser.add_argument('--hash-models',action='store_true');args=parser.parse_args()
    result=audit(Path(args.folder).resolve(),args.hash_models)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    sys.exit(1 if result['forbidden_submission_files'] or result['embedded_mongo_credentials'] or
             not result['index_matches_excel'] or not result['index_document_count_matches'] or
             any(not m['present'] or not m['bytes'] for m in result['models']) or
             any(d['conflict'] for d in result['duplicate_groups']) else 0)
