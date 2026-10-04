# LifeSim Test Report

This is the acceptance record for the source checkout. It complements
`TESTING.md`, which describes the test strategy and release gates.

## Environment

- Date: 2026-10-04
- Runtime: Python 3.12+
- Network: not required; no model/API provider is contacted
- Default provider: `RuleBasedProvider`
- Optional provider: `MockLLMProvider`

## Automated checks

Run from the repository root:

```bash
python -m pytest -q LifeSim/tests -m 'not benchmark'
```

The suite covers:

- world locations and constrained perception;
- minute/hour/day/week clock and snapshots;
- collocated-agent decisions and interactions;
- Seed reproducibility and state hashes;
- serialization and non-destructive snapshot loading;
- events, three-layer memory, journals and bounded memory;
- SQLite normalized entities, reports, indexes and upserts;
- Markdown/HTML/SVG exports;
- `python -m lifesim` headless and inspect commands;
- the 10-agent × 30-day Small Town 01 acceptance run.

Observed result on 2026-10-04: **20 passed** in approximately 13 seconds for
the default smoke suite (`-m 'not benchmark'`); the optional benchmark adds
**1 passed** in approximately 23 seconds when run with `-m benchmark`.
A failure is a release blocker; do not ship a report that silently omits a
failed test.

## Manual smoke checks

```bash
python -m lifesim headless --days 30 --agents 10 --seed 20261004 \
  --output reports/demo
python -m lifesim inspect --db reports/demo/lifesim.sqlite3
python -m lifesim gui --db reports/demo/lifesim.sqlite3
```

Expected artifacts include `simulation_report.md`, `simulation_report.html`,
`observatory_dashboard.svg`, an optional PNG dashboard, `summary.json`, and a
SQLite database containing experiments, agents, traits, needs, memories,
relationships, events, actions and snapshots.

The latest offline Small Town 01 run (10 agents, 30 simulated days, seed
`20261004`) reached minute `43200` (start of Day 31), recorded 30 world events,
20,416 completed action rows (including 1,081 explicit Explore actions), 88
familiar relationship links, and 788 accessible memories. The figures are
sample simulation output, not empirical claims about people.

The delivered `reports/demo/lifesim.sqlite3` was reopened independently and
passed `PRAGMA integrity_check` (`ok`).

The larger benchmark (`--benchmark --days 365 --agents 100 --seed 42`) reached
minute `525600` (Day 366), produced 365 scheduled events and 36,400 coarse
action rows, and completed without creating a database. Benchmark mode is
intentionally coarse and is for throughput/long-run stability, not a substitute
for minute-level experiment data.

## Interpretation

Passing tests establish deterministic software behavior and data integrity;
they do not establish consciousness, human-like psychology, or empirical
validity of the simulated behavior. All values are parameters of an
agent-based research prototype.
