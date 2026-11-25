"""Consistent SQLite snapshots; destination must not already exist."""
import argparse
from pathlib import Path
import sqlite3

def snapshot(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_file():raise FileNotFoundError(source)
    if destination.exists():raise FileExistsError('Destination exists; refusing to overwrite')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive create prevents accidentally overwriting an existing backup.
    with destination.open('xb'):pass
    src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    dst=sqlite3.connect(destination)
    try:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('Integrity check failed')
    finally:dst.close();src.close()

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Backup or restore into a NEW SQLite file. Never include personal backups in submissions.')
    p.add_argument('source');p.add_argument('destination');a=p.parse_args();snapshot(a.source,a.destination)
    print('Snapshot completed; SQLite integrity check OK.')
