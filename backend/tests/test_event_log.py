import psycopg
import pytest

from app.events.log import EventLog


class TestAppendOnly:
    def test_append_and_read(self, db_conn, org):
        log = EventLog(db_conn, org)
        log.append("agent-x", "parsed", input_doc_ref="in.csv", output_ref="r1")
        log.append("agent-x", "recon_completed", output_ref="r1", actor="sanjay")
        trail = log.for_output("r1")
        assert [e["action"] for e in trail] == ["parsed", "recon_completed"]
        assert trail[0]["event_id"] < trail[1]["event_id"]

    def test_org_isolation(self, db_conn, org):
        other = str(
            db_conn.execute("INSERT INTO orgs (name) VALUES ('Other') RETURNING org_id").fetchone()["org_id"]
        )
        EventLog(db_conn, org).append("a", "x", output_ref="r1")
        EventLog(db_conn, other).append("a", "y", output_ref="r1")
        assert [e["action"] for e in EventLog(db_conn, org).for_output("r1")] == ["x"]
        assert [e["action"] for e in EventLog(db_conn, other).recent()] == ["y"]

    def test_update_is_physically_blocked(self, db_conn, org):
        log = EventLog(db_conn, org)
        event_id = log.append("a", "x")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            db_conn.execute("UPDATE agent_events SET action='tampered' WHERE event_id=%s", (event_id,))
        db_conn.rollback()

    def test_delete_is_physically_blocked(self, db_conn, org):
        log = EventLog(db_conn, org)
        log.append("a", "x")
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            db_conn.execute("DELETE FROM agent_events")
        db_conn.rollback()
