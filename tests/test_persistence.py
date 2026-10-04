"""SQLite round-trip and report-storage tests for LifeSim."""

from __future__ import annotations

import json
import sqlite3

from lifesim.core import Simulation, SimulationConfig
from lifesim.persistence import LifeSimDB


def test_sqlite_save_load_and_indexes(tmp_path) -> None:
    db_path = tmp_path / "town.sqlite3"
    sim = Simulation(SimulationConfig(seed=77, agent_count=3))
    sim.run(1)

    db = LifeSimDB(db_path)
    experiment_id = db.save(sim, name="Persistence Fixture")
    assert experiment_id == sim.experiment_id
    assert db.list_experiments()[0]["name"] == "Persistence Fixture"
    assert db.action_rows(experiment_id, limit=5)
    assert db.integrity_check() == "ok"
    assert db.list_snapshots(experiment_id)[0]["snapshot_label"] == "current"

    restored = db.load(experiment_id)
    assert restored.state_hash() == sim.state_hash()

    db.write_report(experiment_id, "# report\n\nOK", "markdown")
    assert db.read_report(experiment_id, "markdown") == "# report\n\nOK"

    # A named snapshot can be read after the connection is reopened.
    sim.step(7)
    db.save_snapshot(sim, "after-seven")
    db.close()
    reopened = LifeSimDB(db_path)
    restored_named = reopened.load(experiment_id, "after-seven")
    assert restored_named.minute == sim.minute
    assert restored_named.seed == sim.seed
    reopened.close()


def test_daily_snapshot_can_be_loaded_from_database(tmp_path) -> None:
    db = LifeSimDB(tmp_path / "daily.sqlite3")
    sim = Simulation(SimulationConfig(seed=79, agent_count=2))
    sim.run(2)
    eid = db.save(sim)
    for label, state in sim.snapshots.items():
        db.conn.execute(
            "INSERT INTO snapshots(experiment_id,snapshot_label,minute,state_json) VALUES(?,?,?,?)",
            (eid, str(label), state["minute"], json.dumps(state)),
        )
    db.conn.commit()
    day_two = db.load(eid, "2")
    assert day_two.minute == 1440
    assert day_two.action_log == []
    db.close()


def test_sqlite_schema_contains_research_entities(tmp_path) -> None:
    db = LifeSimDB(tmp_path / "schema.sqlite3")
    rows = db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    tables = {row[0] for row in rows}
    assert {
        "experiments",
        "locations",
        "agents",
        "traits",
        "needs",
        "goals",
        "memories",
        "relationships",
        "events",
        "actions",
        "snapshots",
        "reports",
    } <= tables
    foreign_keys = db.conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert foreign_keys == 1
    db.close()


def test_save_is_upsert_and_does_not_duplicate_agents(tmp_path) -> None:
    db = LifeSimDB(tmp_path / "upsert.sqlite3")
    sim = Simulation(SimulationConfig(seed=88, agent_count=2))
    sim.run(1)
    eid = db.save(sim)
    sim.step(5)
    assert db.save(sim) == eid
    experiment_count = db.conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    agent_count = db.conn.execute("SELECT COUNT(*) FROM agents WHERE experiment_id=?", (eid,)).fetchone()[0]
    assert experiment_count == 1
    assert agent_count == 2
    db.close()
