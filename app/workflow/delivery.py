"""Approved follow-up tasks with a durable outbox and idempotent demo receiver."""
import hashlib
import json
import sqlite3
from typing import Protocol

from app.workflow.service import WorkflowError, WorkflowService, timestamp


class TaskConnector(Protocol):
    # A connector must deduplicate by key, including after an ambiguous timeout.
    def create_task(self, key: str, payload: dict) -> str: ...


class LocalTaskInbox:
    """Separate downstream store; no remote service or authenticated identity."""
    def __init__(self, db_path='task_inbox.sqlite3'):
        self.db_path = str(db_path)
        with sqlite3.connect(self.db_path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks ('
                       'id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)')

    def create_task(self, key, payload):
        encoded = json.dumps(payload, sort_keys=True)
        with sqlite3.connect(self.db_path) as db:
            db.execute('INSERT OR IGNORE INTO tasks VALUES (?,?,?)', (key, encoded, timestamp()))
            existing = db.execute('SELECT payload_json FROM tasks WHERE id=?', (key,)).fetchone()
            if existing[0] != encoded:
                raise WorkflowError('Delivery key already exists with a different payload.')
        return key

    def tasks(self):
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT * FROM tasks ORDER BY created_at, id').fetchall()
        return [dict(row, payload=json.loads(row['payload_json'])) for row in rows]


class DeliveryService:
    def __init__(self, workflow: WorkflowService):
        self.workflow = workflow
        with workflow.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS deliveries (
                    id TEXT PRIMARY KEY,
                    assessment_id TEXT NOT NULL UNIQUE REFERENCES assessments(id),
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('pending','failed','delivered','cancelled')),
                    created_at TEXT NOT NULL, receipt TEXT
                );
                CREATE TABLE IF NOT EXISTS delivery_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    delivery_id TEXT NOT NULL REFERENCES deliveries(id),
                    attempted_at TEXT NOT NULL, outcome TEXT NOT NULL, error_type TEXT
                );
            ''')

    def _approved(self, identifier, data_dir, as_of):
        record = self.workflow.get(identifier, data_dir, as_of)
        if record['review_state'] != 'approved':
            raise WorkflowError('A current approved assessment is required for delivery.')
        return record

    def enqueue(self, identifier, data_dir, as_of=None):
        record = self._approved(identifier, data_dir, as_of)
        key = hashlib.sha256(f'readiness-follow-up-v1:{identifier}'.encode()).hexdigest()
        # The application constructs the operation. Model text cannot select tools or destinations.
        payload = {
            'assessment_id': identifier,
            'source_fingerprint': record['source_fingerprint'],
            'title': f"Follow up on reviewed assessment: {record['context']['launch_name']}",
            'readiness_status': record['result']['overall_status'],
            'review': record['review'],
            'recommended_actions': record['result'].get('recommended_actions', []),
            'purpose': 'Coordinate assessment follow-up; this task does not authorize launch.',
        }
        with self.workflow.connect() as db:
            db.execute('INSERT OR IGNORE INTO deliveries VALUES (?,?,?,?,?,?)', (
                key, identifier, json.dumps(payload), 'pending', timestamp(), None))
        return self.get(key)

    def get(self, key):
        with self.workflow.connect() as db:
            row = db.execute('SELECT * FROM deliveries WHERE id=?', (key,)).fetchone()
            attempts = db.execute('SELECT * FROM delivery_attempts WHERE delivery_id=? ORDER BY id', (key,)).fetchall()
        if row is None:
            raise WorkflowError('Delivery not found.')
        result = dict(row)
        result['payload'] = json.loads(result.pop('payload_json'))
        result['attempts'] = [dict(attempt) for attempt in attempts]
        return result

    def history(self):
        with self.workflow.connect() as db:
            keys = [row['id'] for row in db.execute('SELECT id FROM deliveries ORDER BY created_at, id')]
        return [self.get(key) for key in keys]

    def dispatch(self, key, data_dir, connector: TaskConnector, as_of=None):
        # Serialize workers in this local demo. A remote connector needs bounded request timeouts.
        # If a process dies after receiver acceptance, rollback leaves the intent retryable.
        with self.workflow.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM deliveries WHERE id=?', (key,)).fetchone()
            if row is None:
                raise WorkflowError('Delivery not found.')
            if row['state'] in ('delivered', 'cancelled'):
                pass
            else:
                try:
                    self._approved(row['assessment_id'], data_dir, as_of)
                except WorkflowError:
                    db.execute("UPDATE deliveries SET state='cancelled' WHERE id=?", (key,))
                    db.execute('INSERT INTO delivery_attempts (delivery_id,attempted_at,outcome,error_type) '
                               'VALUES (?,?,?,?)', (key, timestamp(), 'cancelled', 'SnapshotNotApproved'))
                else:
                    try:
                        receipt = connector.create_task(key, json.loads(row['payload_json']))
                        if not isinstance(receipt, str) or not receipt.strip():
                            raise WorkflowError('Connector returned an invalid receipt.')
                    except Exception as exc:
                        # Record type only: exception strings can contain credentials or sensitive bodies.
                        db.execute("UPDATE deliveries SET state='failed' WHERE id=?", (key,))
                        db.execute('INSERT INTO delivery_attempts (delivery_id,attempted_at,outcome,error_type) '
                                   'VALUES (?,?,?,?)', (key, timestamp(), 'failed', type(exc).__name__))
                    else:
                        db.execute("UPDATE deliveries SET state='delivered', receipt=? WHERE id=?", (receipt, key))
                        db.execute('INSERT INTO delivery_attempts (delivery_id,attempted_at,outcome) '
                                   'VALUES (?,?,?)', (key, timestamp(), 'delivered'))
        return self.get(key)
