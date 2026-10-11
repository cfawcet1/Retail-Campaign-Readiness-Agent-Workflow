import os
import sqlite3

import pytest
import toml

from app.configure_openai import save_key
from app.workflow.service import WorkflowService


def test_key_configuration_preserves_other_settings_and_restricts_file_access(tmp_path):
    path = tmp_path / 'secrets.toml'
    path.write_text('setting = "preserved"\nOPENAI_API_KEY = "old-key"\n')
    save_key('new-test-key', path)
    settings = toml.loads(path.read_text())
    assert settings == {'setting': 'preserved', 'OPENAI_API_KEY': 'new-test-key'}
    if os.name == 'posix':
        assert path.stat().st_mode & 0o777 == 0o600


def test_empty_key_does_not_replace_existing_file(tmp_path):
    path = tmp_path / 'secrets.toml'
    path.write_text('setting = "preserved"\n')
    with pytest.raises(ValueError):
        save_key('', path)
    assert path.read_text() == 'setting = "preserved"\n'


def test_old_database_migration_preserves_history_without_inventing_provider(tmp_path):
    path = tmp_path / 'workflow.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE assessments ('
                   'id TEXT PRIMARY KEY,created_at TEXT NOT NULL,assessment_date TEXT NOT NULL,'
                   'source_fingerprint TEXT NOT NULL,context_json TEXT NOT NULL,model_json TEXT NOT NULL,'
                   'result_json TEXT NOT NULL)')
        db.execute('INSERT INTO assessments VALUES (?,?,?,?,?,?,?)',
                   ('old-record', '2026-08-08', '2026-08-08', 'old-fingerprint', '{}', '{}', '{}'))
    workflow = WorkflowService(path)
    assert workflow.get('old-record')['inference'] == {}
    assert WorkflowService(path).get('old-record')['source_fingerprint'] == 'old-fingerprint'
