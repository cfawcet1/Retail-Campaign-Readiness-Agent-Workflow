"""Durable snapshot-based assessment and review services for CLI and UI."""
import hashlib
import json
import sqlite3
from dataclasses import asdict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

from app.analyzers.data_quality_analyzer import SOURCES
from app.orchestrator.pipeline import run_pipeline
from app.policy.readiness import enforce_readiness


class WorkflowError(ValueError):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f'Unsupported snapshot type: {type(value).__name__}')


def fingerprint(data_dir):
    digest = hashlib.sha256()
    for name in (*SOURCES, 'source_metadata.json'):
        path = Path(data_dir) / name
        try:
            content = path.read_bytes() if path.exists() else None
        except OSError as exc:
            raise WorkflowError(f'Cannot read source snapshot: {name}') from exc
        digest.update(json.dumps([name, content.hex() if content is not None else None]).encode())
    return digest.hexdigest()


class WorkflowService:
    def __init__(self, db_path='readiness.sqlite3'):
        self.db_path = str(db_path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS assessments (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    assessment_date TEXT NOT NULL, source_fingerprint TEXT NOT NULL,
                    context_json TEXT NOT NULL, model_json TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    assessment_id TEXT PRIMARY KEY REFERENCES assessments(id),
                    reviewer TEXT NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('approve','reject')),
                    reason TEXT NOT NULL, reviewed_at TEXT NOT NULL
                );
            ''')
            db.execute('BEGIN IMMEDIATE')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(assessments)')}
            if 'inference_json' not in columns:
                db.execute("ALTER TABLE assessments ADD COLUMN inference_json TEXT NOT NULL DEFAULT '{}'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def assess(self, data_dir, client, as_of=None):
        as_of = as_of or date.today()
        before = fingerprint(data_dir)
        context = run_pipeline(str(data_dir), as_of=as_of)
        model = client.generate(context)
        result = enforce_readiness(context, model)
        if fingerprint(data_dir) != before:
            raise WorkflowError('Sources changed during assessment; rerun assessment.')
        identifier = str(uuid4())
        with self.connect() as db:
            db.execute('INSERT INTO assessments '
                       '(id,created_at,assessment_date,source_fingerprint,context_json,model_json,result_json,inference_json) '
                       'VALUES (?,?,?,?,?,?,?,?)', (
                identifier, timestamp(), as_of.isoformat(), before,
                json.dumps(asdict(context), default=encode),
                json.dumps(model, default=encode), json.dumps(result),
                json.dumps(getattr(client, 'metadata', {})),
            ))
        return self.get(identifier, data_dir, as_of)

    def get(self, identifier, data_dir=None, as_of=None):
        with self.connect() as db:
            row = db.execute('SELECT * FROM assessments WHERE id=?', (identifier,)).fetchone()
            review = db.execute('SELECT * FROM reviews WHERE assessment_id=?', (identifier,)).fetchone()
        if row is None:
            raise WorkflowError('Assessment not found.')
        record = dict(row)
        for name in ('context', 'model', 'result'):
            record[name] = json.loads(record.pop(name + '_json'))
        record['inference'] = json.loads(record.pop('inference_json'))
        record['review'] = dict(review) if review else None
        record['review_state'] = ('approved' if review['decision'] == 'approve' else 'rejected') if review else 'pending_review'
        record['snapshot_current'] = None
        if data_dir is not None:
            current = (record['source_fingerprint'] == fingerprint(data_dir)
                       and record['assessment_date'] == (as_of or date.today()).isoformat())
            record['snapshot_current'] = current
            if not current:
                record['review_state'] = 'reassessment_required'
        return record

    def history(self, data_dir=None, as_of=None):
        with self.connect() as db:
            ids = [row['id'] for row in db.execute('SELECT id FROM assessments ORDER BY created_at DESC, id')]
        return [self.get(identifier, data_dir, as_of) for identifier in ids]

    def review(self, identifier, data_dir, reviewer, decision, reason, as_of=None):
        if decision not in ('approve', 'reject'):
            raise WorkflowError('Decision must be approve or reject.')
        if not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(reason, str) or not reason.strip():
            raise WorkflowError('Reviewer and reason are required.')
        # Serialize competing reviews so the first recorded decision cannot be overwritten.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM assessments WHERE id=?', (identifier,)).fetchone()
            if row is None:
                raise WorkflowError('Assessment not found.')
            if db.execute('SELECT 1 FROM reviews WHERE assessment_id=?', (identifier,)).fetchone():
                raise WorkflowError('Decision already recorded; create a new assessment to review again.')
            if row['source_fingerprint'] != fingerprint(data_dir) or row['assessment_date'] != (as_of or date.today()).isoformat():
                raise WorkflowError('Sources or assessment date changed; reassessment required.')
            result = json.loads(row['result_json'])
            if decision == 'approve' and result['overall_status'] not in ('Ready', 'At Risk'):
                raise WorkflowError('Cannot approve a blocked or unavailable assessment.')
            db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)', (
                identifier, reviewer.strip(), decision, reason.strip(), timestamp(),
            ))
        return self.get(identifier, data_dir, as_of)
