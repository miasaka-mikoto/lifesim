"""Command-line entry points for LifeSim."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .core import Simulation, SimulationConfig, make_demo
from .persistence import LifeSimDB
from .report import dashboard_png, dashboard_svg, html_report, markdown_report, social_graph_svg


def _run(args: argparse.Namespace) -> int:
    config = SimulationConfig(seed=args.seed, agent_count=args.agents, days=args.days, town_name=args.town)
    sim = Simulation(config)
    started = time.perf_counter()
    last_day = sim.day

    def progress(s: Simulation) -> None:
        nonlocal last_day
        if args.progress and s.day != last_day:
            print(f"{s.time_label} · actions={len(s.action_log):,} · memories={s.summary()['memory_count']}")
            last_day = s.day

    # Coarse deterministic ticks keep large headless benchmarks practical;
    # minute-level precision remains the default for small experiments/GUI.
    benchmark = bool(getattr(args, "benchmark", False))
    use_fast = bool(getattr(args, "fast", False) or benchmark or (args.agents * args.days >= 3000))
    interval = int(getattr(args, "fast_interval", 120) or 120)
    if benchmark:
        # Performance mode intentionally avoids a minute-by-minute database;
        # one coarse decision interval per day is enough for throughput tests.
        interval = max(interval, 1440)
    sim.run(args.days, progress=progress, save_snapshots=not benchmark, fast=use_fast, fast_interval=interval)
    elapsed = time.perf_counter() - started
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = Path(args.db) if args.db else out_dir / "lifesim.sqlite3"
    db = None if benchmark else LifeSimDB(db_path)
    if db is not None:
        db.save(sim, name=args.name)
        for label, state in sim.snapshots.items():
            # Snapshot dictionaries are already compact immutable copies.
            db.conn.execute("INSERT INTO snapshots(experiment_id,snapshot_label,minute,state_json) VALUES(?,?,?,?) ON CONFLICT(experiment_id,snapshot_label) DO UPDATE SET minute=excluded.minute,state_json=excluded.state_json,created_at=CURRENT_TIMESTAMP", (sim.experiment_id, str(label), state.get("minute", 0), json.dumps(state, ensure_ascii=False)))
        db.conn.commit()
    md_path = out_dir / "simulation_report.md"
    html_path = out_dir / "simulation_report.html"
    svg_path = out_dir / "observatory_dashboard.svg"
    graph_path = out_dir / "social_graph.svg"
    png_path = out_dir / "observatory_dashboard.png"
    md_path.write_text(markdown_report(sim), encoding="utf-8")
    html_path.write_text(html_report(sim), encoding="utf-8")
    dashboard_svg(sim, svg_path)
    social_graph_svg(sim, graph_path)
    png_result = dashboard_png(sim, png_path)
    (out_dir / "summary.json").write_text(json.dumps(sim.headless_report(), ensure_ascii=False, indent=2), encoding="utf-8")
    if db is not None:
        db.write_report(sim.experiment_id, md_path.read_text(encoding="utf-8"), "markdown")
        db.write_report(sim.experiment_id, html_path.read_text(encoding="utf-8"), "html")
        db.close()
    print(json.dumps({"experiment_id": sim.experiment_id, "database": str(db_path) if db is not None else None, "report": str(md_path), "html": str(html_path), "dashboard_svg": str(svg_path), "social_graph_svg": str(graph_path), "dashboard_png": str(png_result) if png_result else None, "benchmark": benchmark, "elapsed_seconds": round(elapsed, 3), "state_hash": sim.state_hash(), "summary": sim.summary()}, ensure_ascii=False, indent=2))
    return 0


def _inspect(args: argparse.Namespace) -> int:
    db = LifeSimDB(args.db)
    sim = db.load(args.experiment, args.snapshot)
    if args.agent:
        agent = sim.agents.get(args.agent)
        if not agent:
            print(f"Unknown agent: {args.agent}", file=sys.stderr)
            return 2
        print(json.dumps({"id": agent.id, "name": agent.name, "location": agent.location, "needs": agent.needs.as_dict(), "traits": agent.traits.as_dict(), "money": agent.money, "action": agent.action.__dict__, "goals": [g.__dict__ for g in agent.goals], "relationships": {k: v.__dict__ for k, v in agent.relationships.items()}, "memories": [m.__dict__ for m in agent.memories[-20:]], "journal": agent.journal[-7:]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(sim.headless_report(), ensure_ascii=False, indent=2))
    db.close()
    return 0


def _compare(args: argparse.Namespace) -> int:
    db_a, db_b = LifeSimDB(args.db_a), LifeSimDB(args.db_b)
    a, b = db_a.load(args.experiment_a), db_b.load(args.experiment_b)
    print(json.dumps(a.compare(b), ensure_ascii=False, indent=2))
    db_a.close(); db_b.close()
    return 0


def _gui(args: argparse.Namespace) -> int:
    from .gui import run_gui
    run_gui(db_path=args.db)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lifesim", description="LifeSim — offline artificial-life simulation observatory")
    sub = p.add_subparsers(dest="command")
    run = sub.add_parser("run", help="run a deterministic headless simulation")
    run.add_argument("--days", type=int, default=30)
    run.add_argument("--agents", type=int, default=10)
    run.add_argument("--seed", type=int, default=20261004)
    run.add_argument("--town", default="Small Town 01")
    run.add_argument("--demo", nargs="?", const="small-town-01", default=None, help="select the bundled demo scenario")
    run.add_argument("--name", default=None)
    run.add_argument("--output", default="reports/demo")
    run.add_argument("--db", default=None)
    run.add_argument("--progress", action="store_true")
    run.add_argument("--fast", action="store_true", help="use coarse deterministic ticks for large benchmarks")
    run.add_argument("--fast-interval", type=int, default=120, help="minutes per coarse headless tick (default: 120)")
    run.add_argument("--benchmark", action="store_true", help="performance mode: coarse daily ticks without SQLite persistence")
    run.set_defaults(func=_run)
    # Friendly alias matching the requirement's executable invocation.
    head = sub.add_parser("headless", help="alias for run")
    head.add_argument("--days", type=int, default=30)
    head.add_argument("--agents", type=int, default=10)
    head.add_argument("--seed", type=int, default=20261004)
    head.add_argument("--town", default="Small Town 01")
    head.add_argument("--demo", nargs="?", const="small-town-01", default=None)
    head.add_argument("--name", default=None)
    head.add_argument("--output", default="reports/demo")
    head.add_argument("--db", default=None)
    head.add_argument("--progress", action="store_true")
    head.add_argument("--fast", action="store_true")
    head.add_argument("--fast-interval", type=int, default=120)
    head.add_argument("--benchmark", action="store_true")
    head.set_defaults(func=_run)
    ins = sub.add_parser("inspect", help="inspect a saved experiment or agent")
    ins.add_argument("--db", default="reports/demo/lifesim.sqlite3")
    ins.add_argument("--experiment", default=None)
    ins.add_argument("--snapshot", default="current")
    ins.add_argument("--agent", default=None)
    ins.set_defaults(func=_inspect)
    cmp = sub.add_parser("compare", help="compare two saved experiments")
    cmp.add_argument("--db-a", required=True); cmp.add_argument("--db-b", required=True)
    cmp.add_argument("--experiment-a", default=None); cmp.add_argument("--experiment-b", default=None)
    cmp.set_defaults(func=_compare)
    gui = sub.add_parser("gui", help="open the observatory GUI")
    gui.add_argument("--db", default="reports/demo/lifesim.sqlite3")
    gui.set_defaults(func=_gui)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    # Accept both explicit subcommands and the compact forms used in the
    # README/Windows launcher (``--headless --days 30`` and ``--demo``).
    if not argv:
        if os.name == "nt" or os.environ.get("DISPLAY"):
            return _gui(argparse.Namespace(db="reports/demo/lifesim.sqlite3"))
        argv = ["run"]
    elif argv[0] not in {"run", "headless", "inspect", "compare", "gui"}:
        if "--gui" in argv:
            argv = ["gui"] + [x for x in argv if x != "--gui"]
        else:
            # ``--headless`` is a mode flag, not a value-bearing option.
            argv = ["run"] + [x for x in argv if x != "--headless"]
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
