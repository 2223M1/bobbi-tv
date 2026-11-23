"""The optional final-COMMIT gate does not alter ledger transaction semantics."""
import sqlite3

import pytest

from bobbi_core.ledger import Ledger


def test_gate_contains_only_final_commit_not_body(tmp_path):
    with Ledger(tmp_path / 'ledger.sqlite3') as ledger:
        inside, statements = [False], []
        ledger.db.set_trace_callback(lambda sql: statements.append((sql, inside[0])))
        def commit(operation):
            assert ledger.db.in_transaction
            inside[0] = True
            try:
                return operation()
            finally:
                inside[0] = False
        with ledger.transaction(commit=commit):
            ledger.db.execute("INSERT INTO settings VALUES('fixture','one')")
        assert [sql for sql, locked in statements if locked] == ['COMMIT']
        assert ledger.db.execute("SELECT value FROM settings WHERE key='fixture'").fetchone()[0] == 'one'


@pytest.mark.parametrize('gated', [False, True])
def test_nested_begin_rejection_keeps_outer_transaction_and_error_semantics(tmp_path, gated):
    calls = []
    with Ledger(tmp_path / 'ledger.sqlite3') as ledger:
        options = dict(commit=lambda operation: calls.append('commit') or operation()) if gated else {}
        with pytest.raises(sqlite3.OperationalError, match='within a transaction'):
            with ledger.transaction(**options):
                ledger.db.execute("INSERT INTO settings VALUES('fixture','one')")
                with ledger.transaction(**options):
                    pytest.fail('Nested BEGIN must not be silently converted into a savepoint')
        assert not ledger.db.in_transaction and not calls
        assert ledger.db.execute("SELECT 1 FROM settings WHERE key='fixture'").fetchone() is None


@pytest.mark.parametrize('gated', [False, True])
def test_explicit_savepoint_rollback_and_release_are_unchanged(tmp_path, gated):
    calls = []
    with Ledger(tmp_path / 'ledger.sqlite3') as ledger:
        options = dict(commit=lambda operation: calls.append('commit') or operation()) if gated else {}
        with ledger.transaction(**options):
            ledger.db.execute("INSERT INTO settings VALUES('fixture','one')")
            ledger.db.execute('SAVEPOINT fixture_savepoint')
            ledger.db.execute("UPDATE settings SET value='two' WHERE key='fixture'")
            ledger.db.execute('ROLLBACK TO fixture_savepoint')
            ledger.db.execute('RELEASE fixture_savepoint')
        assert calls == (['commit'] if gated else [])
        assert ledger.db.execute("SELECT value FROM settings WHERE key='fixture'").fetchone()[0] == 'one'


@pytest.mark.parametrize('stage', ['body', 'gate'])
def test_base_exception_rolls_back_without_committing(tmp_path, stage):
    class Rejected(BaseException):
        pass
    with Ledger(tmp_path / 'ledger.sqlite3') as ledger:
        def commit(operation):
            raise Rejected('gate rejected')
        with pytest.raises(Rejected, match=stage):
            with ledger.transaction(commit=commit):
                ledger.db.execute("INSERT INTO settings VALUES('fixture','one')")
                if stage == 'body':
                    raise Rejected('body rejected')
        assert not ledger.db.in_transaction
        assert ledger.db.execute("SELECT 1 FROM settings WHERE key='fixture'").fetchone() is None
