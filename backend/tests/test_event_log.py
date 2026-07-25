import sqlite3

import pytest

from app.events.log import EventLog


class TestAppendOnly:
    def test_append_and_read(self, tmp_path):
        log = EventLog(tmp_path / "events.db")
        log.append("agent-x", "parsed", input_doc_ref="in.csv", output_ref="r1")
        log.append("agent-x", "recon_completed", output_ref="r1", actor="sanjay")
        trail = log.for_output("r1")
        assert [e["action"] for e in trail] == ["parsed", "recon_completed"]
        assert trail[0]["event_id"] < trail[1]["event_id"]

    def test_update_is_physically_blocked(self, tmp_path):
        db = tmp_path / "events.db"
        log = EventLog(db)
        log.append("a", "x")
        with sqlite3.connect(db) as conn, pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE agent_events SET action='tampered' WHERE event_id=1")

    def test_delete_is_physically_blocked(self, tmp_path):
        db = tmp_path / "events.db"
        log = EventLog(db)
        log.append("a", "x")
        with sqlite3.connect(db) as conn, pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM agent_events")
