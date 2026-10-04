"""SQLite persistence for LifeSim worlds, traces and research snapshots."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .core import Simulation


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS experiments (
  experiment_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  town_name TEXT NOT NULL,
  seed INTEGER NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  current_minute INTEGER NOT NULL DEFAULT 0,
  config_json TEXT NOT NULL,
  summary_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS locations (
  experiment_id TEXT NOT NULL,
  location_id TEXT NOT NULL,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  x INTEGER NOT NULL,
  y INTEGER NOT NULL,
  capacity INTEGER NOT NULL,
  resource REAL NOT NULL,
  PRIMARY KEY (experiment_id, location_id),
  FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS agents (
  experiment_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  name TEXT NOT NULL,
  age_parameter INTEGER NOT NULL,
  home TEXT NOT NULL,
  job TEXT NOT NULL,
  money REAL NOT NULL,
  location TEXT NOT NULL,
  alive INTEGER NOT NULL,
  PRIMARY KEY (experiment_id, agent_id),
  FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS traits (
  experiment_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  json TEXT NOT NULL,
  PRIMARY KEY (experiment_id, agent_id),
  FOREIGN KEY (experiment_id, agent_id) REFERENCES agents(experiment_id, agent_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS needs (
  experiment_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  json TEXT NOT NULL,
  PRIMARY KEY (experiment_id, agent_id),
  FOREIGN KEY (experiment_id, agent_id) REFERENCES agents(experiment_id, agent_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS goals (
  experiment_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  goal_id TEXT NOT NULL,
  json TEXT NOT NULL,
  PRIMARY KEY (experiment_id, agent_id, goal_id),
  FOREIGN KEY (experiment_id, agent_id) REFERENCES agents(experiment_id, agent_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS memories (
  experiment_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  memory_id TEXT NOT NULL,
  layer TEXT NOT NULL,
  day INTEGER NOT NULL,
  importance REAL NOT NULL,
  retrieval_score REAL NOT NULL,
  json TEXT NOT NULL,
  PRIMARY KEY (experiment_id, agent_id, memory_id),
  FOREIGN KEY (experiment_id, agent_id) REFERENCES agents(experiment_id, agent_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS relationships (
  experiment_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  other_id TEXT NOT NULL,
  json TEXT NOT NULL,
  PRIMARY KEY (experiment_id, agent_id, other_id),
  FOREIGN KEY (experiment_id, agent_id) REFERENCES agents(experiment_id, agent_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS events (
  experiment_id TEXT NOT NULL,
  event_id TEXT NOT NULL,
  day INTEGER NOT NULL,
  minute INTEGER NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  json TEXT NOT NULL,
  PRIMARY KEY (experiment_id, event_id),
  FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS actions (
  experiment_id TEXT NOT NULL,
  row_id INTEGER PRIMARY KEY AUTOINCREMENT,
  minute INTEGER NOT NULL,
  day INTEGER NOT NULL,
  agent_id TEXT NOT NULL,
  action TEXT NOT NULL,
  location TEXT NOT NULL,
  score REAL NOT NULL,
  json TEXT NOT NULL,
  FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_actions_experiment_minute ON actions(experiment_id, minute);
CREATE TABLE IF NOT EXISTS snapshots (
  experiment_id TEXT NOT NULL,
  snapshot_label TEXT NOT NULL,
  minute INTEGER NOT NULL,
  state_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (experiment_id, snapshot_label),
  FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS reports (
  experiment_id TEXT NOT NULL,
  format TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (experiment_id, format),
  FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id) ON DELETE CASCADE
);
"""


class LifeSimDB:
    def __init__(self, path: str | os.PathLike[str] = "lifesim.sqlite3"):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        # Favor durable standalone research files over maximum write speed.
        # This also makes an interrupted GUI/CLI process recover cleanly from
        # the journal instead of leaving a half-written demo artifact.
        self.conn.execute("PRAGMA journal_mode=DELETE")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.commit()
        except sqlite3.Error:
            self.conn.rollback()
        self.conn.close()

    def save(self, sim: Simulation, *, name: Optional[str] = None, include_logs: bool = True) -> str:
        data = sim.to_dict(include_snapshots=False)
        eid = sim.experiment_id
        summary = sim.summary()
        name = name or f"{sim.config.town_name} seed {sim.seed}"
        with self.conn:
            self.conn.execute(
                "INSERT INTO experiments(experiment_id,name,town_name,seed,updated_at,current_minute,config_json,summary_json) VALUES(?,?,?,?,CURRENT_TIMESTAMP,?,?,?) "
                "ON CONFLICT(experiment_id) DO UPDATE SET name=excluded.name,updated_at=CURRENT_TIMESTAMP,current_minute=excluded.current_minute,config_json=excluded.config_json,summary_json=excluded.summary_json",
                (eid, name, sim.config.town_name, sim.seed, sim.minute, json.dumps(sim.config.__dict__, ensure_ascii=False), json.dumps(summary, ensure_ascii=False)),
            )
            self.conn.execute("DELETE FROM locations WHERE experiment_id=?", (eid,))
            for loc in sim.locations.values():
                self.conn.execute("INSERT INTO locations VALUES(?,?,?,?,?,?,?,?)", (eid, loc.id, loc.name, loc.kind, loc.x, loc.y, loc.capacity, loc.resource))
            self.conn.execute("DELETE FROM agents WHERE experiment_id=?", (eid,))
            for agent in sim.agents.values():
                self.conn.execute("INSERT INTO agents VALUES(?,?,?,?,?,?,?,?,?)", (eid, agent.id, agent.name, agent.age_parameter, agent.home, agent.job, agent.money, agent.location, int(agent.alive)))
                self.conn.execute("INSERT INTO traits VALUES(?,?,?)", (eid, agent.id, json.dumps(agent.traits.__dict__)))
                self.conn.execute("INSERT INTO needs VALUES(?,?,?)", (eid, agent.id, json.dumps(agent.needs.__dict__)))
                for goal in agent.goals:
                    self.conn.execute("INSERT INTO goals VALUES(?,?,?,?)", (eid, agent.id, goal.id, json.dumps(goal.__dict__)))
                for mem in agent.memories:
                    self.conn.execute("INSERT INTO memories VALUES(?,?,?,?,?,?,?,?)", (eid, agent.id, mem.id, mem.layer, mem.day, mem.importance, mem.retrieval_score, json.dumps(mem.__dict__, ensure_ascii=False)))
                for other, rel in agent.relationships.items():
                    self.conn.execute("INSERT INTO relationships VALUES(?,?,?,?)", (eid, agent.id, other, json.dumps(rel.__dict__)))
            self.conn.execute("DELETE FROM events WHERE experiment_id=?", (eid,))
            for event in sim.events:
                self.conn.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)", (eid, event.id, event.day, event.minute, event.kind, event.title, json.dumps(event.__dict__, ensure_ascii=False)))
            if include_logs:
                self.conn.execute("DELETE FROM actions WHERE experiment_id=?", (eid,))
                for row in sim.action_log:
                    self.conn.execute("INSERT INTO actions(experiment_id,minute,day,agent_id,action,location,score,json) VALUES(?,?,?,?,?,?,?,?)", (eid, row.get("minute", 0), row.get("day", 0), row.get("agent_id", ""), row.get("action", ""), row.get("location", ""), row.get("score", 0), json.dumps(row, ensure_ascii=False)))
            # Store one current state snapshot in addition to normalized tables.
            self.conn.execute("INSERT INTO snapshots(experiment_id,snapshot_label,minute,state_json) VALUES(?,?,?,?) ON CONFLICT(experiment_id,snapshot_label) DO UPDATE SET minute=excluded.minute,state_json=excluded.state_json,created_at=CURRENT_TIMESTAMP", (eid, "current", sim.minute, json.dumps(data, ensure_ascii=False)))
        return eid

    def save_snapshot(self, sim: Simulation, label: str | int) -> None:
        self.conn.execute("INSERT INTO snapshots(experiment_id,snapshot_label,minute,state_json) VALUES(?,?,?,?) ON CONFLICT(experiment_id,snapshot_label) DO UPDATE SET minute=excluded.minute,state_json=excluded.state_json,created_at=CURRENT_TIMESTAMP", (sim.experiment_id, str(label), sim.minute, json.dumps(sim.to_dict(include_snapshots=False, include_logs=False, include_history=False), ensure_ascii=False)))
        self.conn.commit()

    def load(self, experiment_id: Optional[str] = None, snapshot: str | int = "current") -> Simulation:
        if experiment_id is None:
            row = self.conn.execute("SELECT experiment_id FROM experiments ORDER BY updated_at DESC LIMIT 1").fetchone()
            if not row:
                raise FileNotFoundError("No LifeSim experiment in database")
            experiment_id = row[0]
        row = self.conn.execute("SELECT state_json FROM snapshots WHERE experiment_id=? AND snapshot_label=?", (experiment_id, str(snapshot))).fetchone()
        if not row:
            # Day snapshots are stored by save_snapshot below; try current normalized state.
            row = self.conn.execute("SELECT state_json FROM snapshots WHERE experiment_id=? ORDER BY created_at DESC LIMIT 1", (experiment_id,)).fetchone()
        if not row:
            raise FileNotFoundError(f"No snapshot for experiment {experiment_id}")
        sim = Simulation.from_dict(json.loads(row[0]))
        # Rehydrate named day checkpoints so the GUI timeline and headless
        # time-travel inspector can browse them after reopening the database.
        for snap in self.conn.execute("SELECT snapshot_label,state_json FROM snapshots WHERE experiment_id=? AND snapshot_label != 'current'", (experiment_id,)).fetchall():
            try:
                sim.snapshots[int(snap[0])] = json.loads(snap[1])
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return sim

    def list_experiments(self) -> list[Dict[str, Any]]:
        rows = self.conn.execute("SELECT experiment_id,name,town_name,seed,current_minute,summary_json,updated_at FROM experiments ORDER BY updated_at DESC").fetchall()
        out = []
        for row in rows:
            d = dict(row)
            d["summary"] = json.loads(d.pop("summary_json"))
            out.append(d)
        return out

    def list_snapshots(self, experiment_id: str) -> list[Dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT snapshot_label,minute,created_at FROM snapshots WHERE experiment_id=? ORDER BY minute", (experiment_id,)).fetchall()]

    def write_report(self, experiment_id: str, body: str, fmt: str = "markdown") -> None:
        self.conn.execute("INSERT INTO reports(experiment_id,format,body) VALUES(?,?,?) ON CONFLICT(experiment_id,format) DO UPDATE SET body=excluded.body,created_at=CURRENT_TIMESTAMP", (experiment_id, fmt, body))
        self.conn.commit()

    def read_report(self, experiment_id: str, fmt: str = "markdown") -> Optional[str]:
        row = self.conn.execute("SELECT body FROM reports WHERE experiment_id=? AND format=?", (experiment_id, fmt)).fetchone()
        return row[0] if row else None

    def action_rows(self, experiment_id: str, limit: int = 1000) -> list[Dict[str, Any]]:
        rows = self.conn.execute("SELECT json FROM actions WHERE experiment_id=? ORDER BY minute LIMIT ?", (experiment_id, int(limit))).fetchall()
        return [json.loads(r[0]) for r in rows]

    def integrity_check(self) -> str:
        """Return SQLite's built-in integrity status for release/QA checks."""
        row = self.conn.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "unknown"
