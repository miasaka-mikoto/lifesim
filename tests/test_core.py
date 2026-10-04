"""Acceptance-oriented tests for the offline LifeSim simulation engine."""

from __future__ import annotations

import copy
import json
import math

import pytest

from lifesim.core import (
    ActionState,
    MockLLMProvider,
    Needs,
    Simulation,
    SimulationConfig,
    make_demo,
)


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _assert_invariants(sim: Simulation) -> None:
    assert sim.minute >= 0
    assert sim.day >= 1
    assert sim.week >= 1
    for location in sim.locations.values():
        assert _finite(location.resource), (location.id, location.resource)
        assert location.resource >= 0
        assert location.capacity > 0
    for agent in sim.agents.values():
        for value in vars(agent.needs).values():
            assert _finite(value), (agent.id, value)
            assert 0 <= float(value) <= 100, (agent.id, value)
        for value in vars(agent.traits).values():
            assert _finite(value), (agent.id, value)
            assert 0 <= float(value) <= 100, (agent.id, value)
        assert _finite(agent.money)
        assert agent.money >= 0
        assert agent.action.remaining >= 0
        assert agent.location in sim.locations
        for relation in agent.relationships.values():
            assert relation.other_id in sim.agents
            for value in (
                relation.familiarity,
                relation.trust,
                relation.affinity,
                relation.conflict,
            ):
                assert _finite(value)


def test_default_world_has_required_places_and_limited_observation() -> None:
    sim = Simulation(SimulationConfig(seed=7, agent_count=4))

    # The product requirement names eight places; homes are separate useful
    # locations, so the default scenario intentionally contains more than 8.
    kinds = {location.kind for location in sim.locations.values()}
    assert {"home", "shop", "park", "library", "work", "hospital", "cafe", "square"} <= kinds

    agent = sim.agents["agent_001"]
    observation = sim.observation(agent)
    assert {
        "time",
        "location",
        "nearby_agents",
        "nearby_resources",
        "weather",
        "recent_events",
        "needs",
        "goals",
    } <= observation.keys()
    # A constrained Observation must not leak the complete world or another
    # Agent's private memories/relationships.
    assert "event_log" not in observation
    assert "agents" not in observation
    assert "memories" not in observation
    assert "relationships" not in observation


def test_clock_advances_and_day_boundary_writes_snapshot() -> None:
    sim = Simulation(SimulationConfig(seed=8, agent_count=2))
    sim.step(61)
    assert (sim.minute, sim.day, sim.hour, sim.minute_of_hour) == (61, 1, 1, 1)

    sim.step(1379)
    assert sim.minute == 1440
    assert sim.day == 2
    assert sim.week == 1
    assert 2 in sim.snapshots
    assert sim.snapshots[2]["minute"] == 1440
    assert sim.time_label == "Day 2, 00:00"


def test_collocated_agents_can_decide_and_interact() -> None:
    """A common town-square case must not depend on dataclass ordering."""

    sim = Simulation(SimulationConfig(seed=9, agent_count=3))
    first, second, third = list(sim.agents.values())
    for agent in (first, second, third):
        agent.location = "town_square"
        agent.needs = Needs(
            energy=90,
            hunger=5,
            health=90,
            mood=60,
            curiosity=5,
            social_need=100,
            stress=5,
            safety=90,
            achievement=5,
        )
        agent.traits.sociability = 100
        agent.traits.patience = 1

    # This calls the same public engine path used by a normal tick.  It should
    # return a deterministic action even when multiple Agents share a place.
    action = sim._select_action(first)
    assert action.name in sim.ACTIONS
    first.action = ActionState("Talk", target_agent=second.id, remaining=0)
    sim._complete_action(first)
    assert first.relationships[second.id].familiarity > 0
    assert second.relationships[first.id].familiarity > 0


def test_same_seed_and_config_are_reproducible() -> None:
    config = SimulationConfig(seed=1234, agent_count=3)
    left = Simulation(config)
    right = Simulation(copy.deepcopy(config))
    left.run(2)
    right.run(2)
    assert left.state_hash() == right.state_hash()
    assert left.headless_report() == right.headless_report()


def test_snapshot_round_trip_preserves_state() -> None:
    sim = Simulation(SimulationConfig(seed=21, agent_count=3))
    sim.run(1)
    before = sim.state_hash()
    payload = sim.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False)
    restored = Simulation.from_dict(json.loads(encoded), provider=MockLLMProvider())
    assert restored.state_hash() == before
    assert restored.minute == sim.minute
    assert restored.seed == sim.seed
    assert len(restored.agents) == len(sim.agents)

    # Snapshot restore is deterministic and does not erase the original data.
    restored.step(3)
    assert restored.minute == sim.minute + 3
    assert sim.minute == payload["minute"]

    # PRNG state is part of reproducibility metadata: continuing a restored
    # world produces the same branch as continuing the original.
    left = Simulation.from_dict(payload)
    right = Simulation.from_dict(payload)
    left.step(17)
    right.step(17)
    assert left.state_hash() == right.state_hash()


def test_time_travel_snapshot_view_is_detached_and_trace_safe() -> None:
    sim = Simulation(SimulationConfig(seed=23, agent_count=2))
    sim.run(1)
    assert 2 in sim.snapshots
    snapshot = sim.snapshot_view(2)
    assert snapshot is not None
    assert snapshot.minute == 1440
    # Daily state checkpoints intentionally omit append-only traces; SQLite's
    # actions/events tables remain the canonical research log.
    assert snapshot.action_log == []
    before = sim.state_hash()
    snapshot.step(3)
    assert snapshot.minute == 1443
    assert sim.state_hash() == before


def test_from_dict_does_not_consume_snapshot_payload() -> None:
    sim = Simulation(SimulationConfig(seed=22, agent_count=2))
    sim.step(4)
    payload = sim.to_dict()
    before = copy.deepcopy(payload)
    first = Simulation.from_dict(payload)
    second = Simulation.from_dict(payload)
    assert first.state_hash() == second.state_hash()
    assert payload == before


def test_events_memory_consolidation_and_journals() -> None:
    sim = Simulation(SimulationConfig(seed=20261004, agent_count=4))
    # Seed one salient event so the test exercises the episodic promotion path
    # regardless of which actions the deterministic population happens to pick.
    sim._add_memory(
        sim.agents["agent_001"],
        "A salient research event worth remembering.",
        importance=0.9,
        relevance=0.95,
        tags=["test", "salient"],
    )
    sim.run(3)
    assert sim.event_log
    assert all("title" in event and "minute" in event for event in sim.event_log)
    assert all(agent.journal for agent in sim.agents.values())
    layers = {memory.layer for agent in sim.agents.values() for memory in agent.memories}
    assert "semantic" in layers
    assert "episodic" in layers
    assert all(len(agent.memories) <= 100 for agent in sim.agents.values())
    _assert_invariants(sim)


def test_headless_report_exposes_research_questions() -> None:
    sim = Simulation(SimulationConfig(seed=44, agent_count=4))
    sim.run(2)
    report = sim.headless_report()
    assert report["population"] == 4
    assert isinstance(report["top_explorers"], list)
    assert isinstance(report["top_social"], list)
    assert isinstance(report["fixed_habits"], list)
    assert report["action_log_rows"] > 0
    assert "action_frequency" in report
    assert report["social_graph_edges"]
    assert report["place_ranking"]
    assert report["metrics_timeseries"]
    assert all("day" in row and "actions" in row for row in report["metrics_timeseries"])


def test_experiment_comparison_reports_behavior_dimensions() -> None:
    high = Simulation(SimulationConfig(seed=55, agent_count=3, town_name="High Curiosity"))
    low = Simulation(SimulationConfig(seed=55, agent_count=3, town_name="Low Curiosity"))
    for agent in high.agents.values():
        agent.traits.curiosity = 95
        agent.needs.curiosity = 95
    for agent in low.agents.values():
        agent.traits.curiosity = 5
        agent.needs.curiosity = 5
    high.run(1)
    low.run(1)
    comparison = high.compare(low)
    assert {"exploration", "movement", "knowledge", "average_money", "relationship_count"} <= comparison.keys()
    for metric in comparison.values():
        assert {"a", "b", "difference"} <= metric.keys()


@pytest.mark.longrun
def test_small_town_30_day_acceptance_run() -> None:
    """The shipped demo must survive the requested 10-agent/30-day run."""

    sim = make_demo(days=30, seed=20261004)
    assert sim.day == 31  # minute 43200 is the start of Day 31
    assert sim.minute == 30 * 1440
    assert len(sim.agents) == 10
    assert len(sim.action_log) > 10 * 30
    assert len(sim.event_log) >= 30
    _assert_invariants(sim)
