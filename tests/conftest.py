"""
Tests run against a throwaway copy of data/spike.db, so test rows never reach the real queue
(a running worker would otherwise pick them up and process them).
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import src.db as db

_test_db = Path(tempfile.mkdtemp(prefix="spike_test_")) / "spike.db"
if db.DB_PATH.exists():
    # backup() gives a consistent copy even while the real app has the DB open in WAL mode.
    with sqlite3.connect(db.DB_PATH) as src, sqlite3.connect(_test_db) as dst:
        src.backup(dst)
db.DB_PATH = _test_db
db.init_db()
db.set_setting("claude_help", "off")  # the judge pool never calls the real Claude CLI from a test


@pytest.fixture
def judge_by_window():
    """Stage 7 judges in parallel and in a shuffled order (src/judge_pool.py), so a fake call_llm_judge must answer by
    candidate window, not by call order. A window starts at peak - 90 s, and its first line's time picks the peak.
    make(peaks, answers, build) returns the fake; answers[i] belongs to peaks[i] and build(*answers[i]) makes it."""
    def make(peaks, answers, build):
        def fake(lines, comments, sigs, **kw):
            mm, ss = lines[0].split("[", 1)[1].split("]", 1)[0].split(":")
            t = int(mm) * 60 + float(ss)
            i = min(range(len(peaks)), key=lambda k: abs(max(0.0, peaks[k] - 90.0) - t))
            return build(*answers[i])
        return fake
    return make
