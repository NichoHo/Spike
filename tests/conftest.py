"""
Tests run against a throwaway copy of data/spike.db, so test rows never reach the real queue
(a running worker would otherwise pick them up and process them).
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.db as db

_test_db = Path(tempfile.mkdtemp(prefix="spike_test_")) / "spike.db"
if db.DB_PATH.exists():
    # backup() gives a consistent copy even while the real app has the DB open in WAL mode.
    with sqlite3.connect(db.DB_PATH) as src, sqlite3.connect(_test_db) as dst:
        src.backup(dst)
db.DB_PATH = _test_db
