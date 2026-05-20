"""Prediction history persistence via stdlib sqlite3 (no new dependencies).

Stores one summary row per prediction run, plus JSON blobs for the per-category
and per-severity counts so the history page can render trend charts.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join('data', 'history.db')


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                filename TEXT,
                total INTEGER NOT NULL,
                attacks INTEGER NOT NULL,
                normal INTEGER NOT NULL,
                attack_rate REAL NOT NULL,
                avg_confidence REAL NOT NULL,
                category_counts TEXT NOT NULL,
                severity_counts TEXT NOT NULL
            )
        """)
        conn.commit()


def save_prediction(summary: dict, filename: Optional[str] = None) -> Optional[int]:
    """Persist a prediction summary. Returns the new row id, or None on failure."""
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO predictions
                  (timestamp, filename, total, attacks, normal, attack_rate,
                   avg_confidence, category_counts, severity_counts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(timespec='seconds') + 'Z',
                    filename or '',
                    int(summary.get('total', 0)),
                    int(summary.get('attacks', 0)),
                    int(summary.get('normal', 0)),
                    float(summary.get('attack_rate', 0.0)),
                    float(summary.get('avg_confidence', 0.0)),
                    json.dumps(summary.get('category_counts', {})),
                    json.dumps(summary.get('severity_counts', {})),
                ),
            )
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        print(f"[db] save_prediction failed: {e}")
        return None


def recent_predictions(limit: int = 50) -> list:
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM predictions ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        result = []
        for r in rows:
            result.append({
                'id': r['id'],
                'timestamp': r['timestamp'],
                'filename': r['filename'],
                'total': r['total'],
                'attacks': r['attacks'],
                'normal': r['normal'],
                'attack_rate': r['attack_rate'],
                'avg_confidence': r['avg_confidence'],
                'category_counts': json.loads(r['category_counts'] or '{}'),
                'severity_counts': json.loads(r['severity_counts'] or '{}'),
            })
        return result
    except Exception as e:
        print(f"[db] recent_predictions failed: {e}")
        return []
