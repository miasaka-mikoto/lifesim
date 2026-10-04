"""LifeSim deterministic rule-based artificial-life simulation engine.

The engine is intentionally offline and explainable.  It models a small town
with agents whose needs, traits, goals, memories and relationships evolve over
time.  No language model is required; the CognitiveProvider protocol is a
future extension point and the bundled providers are deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple
import copy
import hashlib
import json
import math
import random
import statistics
import time
import uuid

from .stats import summarize


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


@dataclass
class Location:
    id: str
    name: str
    kind: str
    x: int
    y: int
    capacity: int = 30
    resource: float = 100.0
    open_hour: int = 0
    close_hour: int = 24


@dataclass
class Traits:
    sociability: float = 50.0
    curiosity: float = 50.0
    risk_tolerance: float = 50.0
    patience: float = 50.0
    discipline: float = 50.0
    generosity: float = 50.0
    independence: float = 50.0
    emotion_reactivity: float = 50.0

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class Needs:
    energy: float = 78.0
    hunger: float = 25.0
    health: float = 90.0
    mood: float = 65.0
    curiosity: float = 35.0
    social_need: float = 30.0
    stress: float = 15.0
    safety: float = 85.0
    achievement: float = 30.0

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class Goal:
    id: str
    kind: str
    title: str
    target: float = 1.0
    progress: float = 0.0
    horizon: str = "short"
    priority: float = 50.0
    status: str = "active"

    def advance(self, amount: float) -> None:
        if self.status != "active":
            return
        self.progress = min(self.target, self.progress + amount)
        if self.progress >= self.target:
            self.status = "completed"


@dataclass
class Memory:
    id: str
    layer: str  # working, episodic, semantic
    content: str
    day: int
    importance: float = 0.5
    recency: float = 1.0
    relevance: float = 0.5
    participants: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    @property
    def retrieval_score(self) -> float:
        return 0.5 * self.importance + 0.3 * self.recency + 0.2 * self.relevance


@dataclass
class Relationship:
    other_id: str
    familiarity: float = 0.0
    trust: float = 50.0
    affinity: float = 0.0
    conflict: float = 0.0
    last_interaction: int = 0
    interactions: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActionState:
    name: str = "Wait"
    target_location: Optional[str] = None
    target_agent: Optional[str] = None
    remaining: int = 0
    started_minute: int = 0
    reason: str = ""
    score: float = 0.0
    intent: Optional[str] = None


@dataclass
class Agent:
    id: str
    name: str
    age_parameter: int
    home: str
    job: str
    money: float = 100.0
    needs: Needs = field(default_factory=Needs)
    traits: Traits = field(default_factory=Traits)
    location: str = "town_square"
    goals: List[Goal] = field(default_factory=list)
    relationships: Dict[str, Relationship] = field(default_factory=dict)
    memories: List[Memory] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    journal: List[Dict[str, Any]] = field(default_factory=list)
    action: ActionState = field(default_factory=ActionState)
    current_goal_id: Optional[str] = None
    memory_counter: int = 0
    skills: Dict[str, float] = field(default_factory=lambda: {"work": 50.0, "reading": 20.0, "social": 20.0})
    alive: bool = True

    def active_goal(self) -> Optional[Goal]:
        if self.current_goal_id:
            for goal in self.goals:
                if goal.id == self.current_goal_id and goal.status == "active":
                    return goal
        for goal in sorted(self.goals, key=lambda g: (-g.priority, g.id)):
            if goal.status == "active":
                self.current_goal_id = goal.id
                return goal
        return None


@dataclass
class WorldEvent:
    id: str
    day: int
    minute: int
    kind: str
    title: str
    description: str
    effects: Dict[str, float] = field(default_factory=dict)
    active_until: int = 0


@dataclass
class JournalEntry:
    day: int
    main_actions: List[str]
    important_events: List[str]
    people_met: List[str]
    relationship_changes: List[str]
    goal_changes: List[str]
    important_memories: List[str]


@dataclass
class SimulationConfig:
    seed: int = 20261004
    agent_count: int = 10
    days: int = 30
    tick_minutes: int = 1
    town_name: str = "Small Town 01"


class CognitiveProvider(Protocol):
    def plan(self, observation: Dict[str, Any], actions: List[str]) -> Dict[str, float]: ...
    def reflect(self, history: List[Dict[str, Any]]) -> str: ...
    def summarize_memory(self, memories: List[Memory]) -> str: ...
    def dialogue(self, speaker: Agent, listener: Agent, intent: str) -> str: ...


class RuleBasedProvider:
    """Explainable provider used by default; no network or API calls."""

    def plan(self, observation: Dict[str, Any], actions: List[str]) -> Dict[str, float]:
        needs = observation.get("needs", {})
        return {a: 0.0 for a in actions} | {
            "Eat": needs.get("hunger", 0) / 100,
            "Sleep": (100 - needs.get("energy", 100)) / 100,
            "Talk": needs.get("social_need", 0) / 100,
            "Explore": needs.get("curiosity", 0) / 100,
        }

    def reflect(self, history: List[Dict[str, Any]]) -> str:
        if not history:
            return "A quiet day."
        counts: Dict[str, int] = {}
        for item in history:
            action = str(item.get("action", "Wait"))
            counts[action] = counts.get(action, 0) + 1
        top = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[0]
        return f"Mostly {top[0].lower()} ({top[1]} times); the day left a trace of ordinary life."

    def summarize_memory(self, memories: List[Memory]) -> str:
        if not memories:
            return "No lasting memory."
        return memories[0].content

    def dialogue(self, speaker: Agent, listener: Agent, intent: str) -> str:
        templates = {
            "Greeting": f"{speaker.name} greeted {listener.name}.",
            "Ask": f"{speaker.name} asked {listener.name} about the town.",
            "Share": f"{speaker.name} shared a small observation with {listener.name}.",
            "Invite": f"{speaker.name} invited {listener.name} to meet again.",
            "Disagree": f"{speaker.name} and {listener.name} saw things differently.",
            "Help": f"{speaker.name} offered help to {listener.name}.",
        }
        return templates.get(intent, templates["Greeting"])


class MockLLMProvider(RuleBasedProvider):
    """Offline deterministic stand-in for future LLM integration."""

    pass


DEFAULT_LOCATIONS: List[Location] = [
    Location("home_alex", "Alex's Home", "home", 1, 1),
    Location("home_bella", "Bella's Home", "home", 1, 5),
    Location("home_casey", "Casey's Home", "home", 8, 1),
    Location("home_drew", "Drew's Home", "home", 8, 5),
    Location("food_shop", "Food Shop", "shop", 4, 1, resource=1000.0),
    Location("park", "Park", "park", 2, 3),
    Location("library", "Library", "library", 6, 3),
    Location("workplace", "Workplace", "work", 4, 5),
    Location("hospital", "Hospital", "hospital", 7, 5),
    Location("cafe", "Cafe", "cafe", 3, 3, resource=500.0),
    Location("town_square", "Town Square", "square", 5, 3),
]

NAMES = ["Alex", "Bella", "Casey", "Drew", "Emi", "Finn", "Grace", "Haru", "Iris", "Jun", "Kai", "Lena", "Mika", "Noah", "Owen"]


class Simulation:
    """A deterministic minute-based agent simulation."""

    ACTIONS = ["Move", "Eat", "Sleep", "Work", "Rest", "Read", "Talk", "Buy", "Explore", "Help", "Avoid", "Visit", "Wait"]

    def __init__(self, config: Optional[SimulationConfig] = None, *, provider: Optional[CognitiveProvider] = None):
        self.config = config or SimulationConfig()
        self.seed = int(self.config.seed)
        self.rng = random.Random(self.seed)
        self.provider: CognitiveProvider = provider or RuleBasedProvider()
        self.minute = 0
        self.weather = "clear"
        self.locations: Dict[str, Location] = {}
        self.agents: Dict[str, Agent] = {}
        self.events: List[WorldEvent] = []
        self.event_log: List[Dict[str, Any]] = []
        self.action_log: List[Dict[str, Any]] = []
        self.snapshots: Dict[int, Dict[str, Any]] = {}
        self.experiment_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"lifesim:{self.seed}:{self.config.town_name}").hex[:12]
        self._day_action_buffer: Dict[str, List[str]] = {}
        self._day_people_buffer: Dict[str, List[str]] = {}
        self._day_relationship_buffer: Dict[str, List[str]] = {}
        self._location_agent_ids: Dict[str, List[str]] = {}
        self._build_world()

    @property
    def day(self) -> int:
        return self.minute // 1440 + 1

    @property
    def hour(self) -> int:
        return (self.minute // 60) % 24

    @property
    def minute_of_hour(self) -> int:
        return self.minute % 60

    @property
    def week(self) -> int:
        return (self.day - 1) // 7 + 1

    @property
    def time_label(self) -> str:
        return f"Day {self.day}, {self.hour:02d}:{self.minute_of_hour:02d}"

    def _build_world(self) -> None:
        self.locations = {loc.id: copy.deepcopy(loc) for loc in DEFAULT_LOCATIONS}
        # Use per-agent homes for arbitrary population while retaining a clear town map.
        homes = ["home_alex", "home_bella", "home_casey", "home_drew"]
        for i in range(self.config.agent_count):
            name = NAMES[i % len(NAMES)] if i < len(NAMES) else f"Resident {i+1}"
            aid = f"agent_{i+1:03d}"
            home = homes[i % len(homes)]
            traits = Traits(
                sociability=self.rng.randint(25, 85),
                curiosity=self.rng.randint(25, 85),
                risk_tolerance=self.rng.randint(25, 75),
                patience=self.rng.randint(25, 80),
                discipline=self.rng.randint(25, 85),
                generosity=self.rng.randint(20, 80),
                independence=self.rng.randint(25, 85),
                emotion_reactivity=self.rng.randint(20, 80),
            )
            needs = Needs(
                energy=self.rng.randint(65, 90),
                hunger=self.rng.randint(15, 35),
                health=self.rng.randint(75, 100),
                mood=self.rng.randint(50, 80),
                curiosity=self.rng.randint(20, 55),
                social_need=self.rng.randint(15, 45),
                stress=self.rng.randint(5, 30),
                safety=self.rng.randint(70, 95),
                achievement=self.rng.randint(15, 45),
            )
            job = ["shopkeeper", "librarian", "builder", "nurse", "teacher"][i % 5]
            goals = [
                Goal(f"{aid}_eat", "survival", "Eat regularly", 8, 0, "short", 86),
                Goal(f"{aid}_social", "social", "Meet someone new", 3, 0, "medium", 45 + traits.sociability * 0.4),
                Goal(f"{aid}_learn", "knowledge", "Read or explore", 4, 0, "medium", 35 + traits.curiosity * 0.5),
                Goal(f"{aid}_save", "economy", "Save money", 150, 0, "long", 25 + traits.discipline * 0.4),
            ]
            agent = Agent(aid, name, self.rng.randint(20, 50), home, job, self.rng.randint(80, 160), needs, traits, home, goals=goals)
            agent.memories.append(Memory(f"{aid}_birth", "semantic", f"{name} lives in {self.locations[home].name}.", 1, 0.8, 1.0, 0.8, tags=["identity"]))
            self.agents[aid] = agent
            self._day_action_buffer[aid] = []
            self._day_people_buffer[aid] = []
            self._day_relationship_buffer[aid] = []
        # Relationships start sparse; all agents can meet and create links.
        for aid, agent in self.agents.items():
            for other in self.agents:
                if aid != other:
                    agent.relationships[other] = Relationship(other)
        self._rebuild_location_index()

    def _rebuild_location_index(self) -> None:
        self._location_agent_ids = {}
        for agent in self.agents.values():
            if agent.alive:
                self._location_agent_ids.setdefault(agent.location, []).append(agent.id)
        for ids in self._location_agent_ids.values():
            ids.sort()

    def _agents_at(self, location_id: str, *, exclude: Optional[str] = None) -> List[Agent]:
        ids = self._location_agent_ids.get(location_id)
        if ids is None:
            ids = [a.id for a in self.agents.values() if a.alive and a.location == location_id]
        return [self.agents[i] for i in ids if i != exclude and i in self.agents and self.agents[i].alive]

    def world_config(self) -> Dict[str, Any]:
        return {"seed": self.seed, "agent_count": len(self.agents), "town_name": self.config.town_name, "locations": [asdict(x) for x in self.locations.values()]}

    def observation(self, agent: Agent) -> Dict[str, Any]:
        loc = self.locations[agent.location]
        nearby = [a.name for a in self._agents_at(agent.location, exclude=agent.id)]
        nearby_resources = {"food": self.locations["food_shop"].resource, "cafe": self.locations["cafe"].resource}
        recent = [e["title"] for e in self.event_log[-5:] if self.minute - int(e.get("minute", 0)) < 360]
        return {
            "time": {"minute": self.minute, "day": self.day, "hour": self.hour, "week": self.week},
            "location": {"id": loc.id, "name": loc.name, "kind": loc.kind},
            "nearby_agents": nearby,
            "nearby_resources": nearby_resources,
            "weather": self.weather,
            "recent_events": recent,
            "needs": agent.needs.as_dict(),
            "goals": [asdict(g) for g in agent.goals if g.status == "active"],
        }

    def _is_open(self, loc: Location) -> bool:
        if loc.open_hour == loc.close_hour:
            return True
        return loc.open_hour <= self.hour < loc.close_hour

    def _score_actions(self, agent: Agent) -> Dict[str, float]:
        n, t = agent.needs, agent.traits
        scores = {a: -10.0 for a in self.ACTIONS}
        at_home = agent.location == agent.home
        kind = self.locations[agent.location].kind
        # Baseline scores, scaled to a transparent 0..1-ish range.
        scores["Wait"] = 0.05 + t.patience / 500
        scores["Sleep"] = (100 - n.energy) / 55 + (0.18 if at_home else 0.0)
        scores["Eat"] = n.hunger / 45 + (0.12 if kind in {"shop", "cafe", "home"} else 0.0)
        scores["Work"] = (0.35 + n.achievement / 160 + t.discipline / 250) if 8 <= self.hour < 18 else -0.1
        scores["Talk"] = n.social_need / 42 + t.sociability / 220
        scores["Read"] = n.curiosity / 120 + t.curiosity / 300
        scores["Explore"] = n.curiosity / 80 + t.curiosity / 190 + 0.12
        if t.curiosity >= 65 and n.curiosity >= 25:
            # High-curiosity personalities should visibly leave routine routes,
            # making exploration an observable emergent dimension rather than a
            # permanently dominated fallback action.
            scores["Explore"] += 0.55
        scores["Rest"] = (100 - n.energy) / 110 + n.stress / 180
        scores["Help"] = t.generosity / 300 + n.social_need / 300
        scores["Avoid"] = n.stress / 75 + (100 - t.risk_tolerance) / 400
        scores["Buy"] = n.hunger / 130 + (0.2 if agent.money > 12 else -0.3)
        # Health and safety override social goals.
        if n.health < 45:
            scores["Visit"] = 1.4
        else:
            scores["Visit"] = 0.05
        # Homes are useful when depleted; workplace during workday.
        if at_home:
            scores["Sleep"] += 0.15
        if kind == "library":
            scores["Read"] += 0.28
        if kind in {"park", "cafe", "square"}:
            scores["Talk"] += 0.18
        if kind == "work":
            scores["Work"] += 0.35
        # Weather influences outdoor decisions.
        if self.weather == "rain":
            scores["Explore"] -= 0.3
            scores["Read"] += 0.15
        # Active goals contribute explainable utility.
        goal = agent.active_goal()
        if goal:
            if goal.kind == "survival":
                scores["Eat"] += 0.25 * (1 - goal.progress / max(goal.target, 1))
            elif goal.kind == "social":
                scores["Talk"] += 0.2
            elif goal.kind == "knowledge":
                scores["Read"] += 0.2
            elif goal.kind == "economy":
                scores["Work"] += 0.14
        return scores

    def decision_scores(self, agent_id: str) -> Dict[str, float]:
        return self._score_actions(self.agents[agent_id])

    def _nearest(self, agent: Agent, location_ids: Iterable[str]) -> str:
        # Deterministic Manhattan distance tie-broken by id.
        a = self.locations[agent.location]
        return min(location_ids, key=lambda lid: (abs(a.x - self.locations[lid].x) + abs(a.y - self.locations[lid].y), lid))

    def _select_action(self, agent: Agent) -> ActionState:
        scores = self._score_actions(agent)
        # Provider is advisory; rule scores remain authoritative and inspectable.
        try:
            advice = self.provider.plan(self.observation(agent), self.ACTIONS)
            for name, value in advice.items():
                if name in scores:
                    scores[name] += float(value) * 0.05
        except Exception:
            pass
        # If target is not local, convert the highest utility into a visit/move.
        best = max(self.ACTIONS, key=lambda a: (round(scores[a], 8), -self.ACTIONS.index(a)))
        target: Optional[str] = None
        if best in {"Sleep"} and agent.location != agent.home:
            target = agent.home
        elif best in {"Eat", "Buy"} and self.locations[agent.location].kind not in {"shop", "cafe", "home"}:
            target = self._nearest(agent, ["food_shop", "cafe"])
        elif best == "Work" and self.locations[agent.location].kind != "work":
            target = "workplace"
        elif best == "Read" and self.locations[agent.location].kind != "library":
            target = "library"
        elif best in {"Talk", "Help"} and not self._agents_at(agent.location, exclude=agent.id):
            target = self._nearest(agent, ["park", "cafe", "town_square"])
        elif best == "Visit" and agent.needs.health < 45:
            target = "hospital"
        elif best in {"Explore", "Visit"}:
            choices = [x for x in self.locations if x != agent.location and self.locations[x].kind != "home"]
            target = self.rng.choice(sorted(choices)) if choices else agent.home
        if target and target != agent.location:
            dist = abs(self.locations[agent.location].x - self.locations[target].x) + abs(self.locations[agent.location].y - self.locations[target].y)
            return ActionState("Move", target, None, max(3, dist * 4), self.minute, f"{best} utility {scores[best]:.2f}", scores[best], best)
        durations = {"Sleep": 30, "Eat": 15, "Work": 45, "Rest": 20, "Read": 30, "Talk": 12, "Buy": 8, "Explore": 25, "Help": 15, "Avoid": 10, "Visit": 15, "Wait": 10}
        target_agent = None
        if best in {"Talk", "Help", "Avoid"}:
            candidates = self._agents_at(agent.location, exclude=agent.id)
            if candidates:
                target_agent = candidates[0].id
        return ActionState(best, None, target_agent, durations.get(best, 10), self.minute, f"score {scores[best]:.2f}", scores[best])

    def _add_memory(self, agent: Agent, content: str, *, importance: float = 0.5, relevance: float = 0.5, participants: Optional[List[str]] = None, tags: Optional[List[str]] = None) -> None:
        # A monotonic counter is required because bounded working memory can
        # remove entries while new memories continue to arrive.  Reusing
        # ``len(memories)`` would create duplicate primary keys in SQLite.
        agent.memory_counter += 1
        mid = f"{agent.id}_m{agent.memory_counter:07d}"
        agent.memories.append(Memory(mid, "working", content, self.day, importance, 1.0, relevance, participants or [], tags or []))
        # Working memory is intentionally bounded.
        working = [m for m in agent.memories if m.layer == "working"]
        if len(working) > 12:
            oldest = min(working, key=lambda m: (m.importance, m.day, m.id))
            agent.memories.remove(oldest)

    def _interact(self, agent: Agent, other: Agent, intent: str = "Greeting") -> None:
        rel = agent.relationships[other.id]
        rel.familiarity = clamp(rel.familiarity + 3)
        rel.last_interaction = self.day
        rel.interactions += 1
        delta = 1.5 + agent.traits.sociability / 120
        if intent == "Help":
            delta += agent.traits.generosity / 100
        if intent == "Disagree":
            rel.conflict = clamp(rel.conflict + 3)
            rel.affinity = clamp(rel.affinity - 1)
            rel.trust = clamp(rel.trust - 1)
        else:
            rel.affinity = clamp(rel.affinity + delta, -100, 100)
            rel.trust = clamp(rel.trust + 0.7)
        back = other.relationships[agent.id]
        back.familiarity = clamp(back.familiarity + 2)
        back.last_interaction = self.day
        back.interactions += 1
        back.affinity = clamp(back.affinity + delta * 0.65, -100, 100)
        back.trust = clamp(back.trust + 0.4)
        agent.needs.social_need = clamp(agent.needs.social_need - 18)
        other.needs.social_need = clamp(other.needs.social_need - 12)
        agent.needs.mood = clamp(agent.needs.mood + 3)
        other.needs.mood = clamp(other.needs.mood + 2)
        line = self.provider.dialogue(agent, other, intent)
        self._add_memory(agent, line, importance=0.55, relevance=0.8, participants=[other.id], tags=["social"])
        self._add_memory(other, line, importance=0.45, relevance=0.8, participants=[agent.id], tags=["social"])
        self._day_people_buffer[agent.id].append(other.name)
        self._day_people_buffer[other.id].append(agent.name)
        self._day_relationship_buffer[agent.id].append(f"{other.name}: affinity {rel.affinity:+.1f}")
        self._day_relationship_buffer[other.id].append(f"{agent.name}: affinity {back.affinity:+.1f}")

    def _complete_action(self, agent: Agent) -> None:
        original_action = agent.action.name
        action = original_action
        target = agent.action.target_location
        if action == "Move" and target:
            agent.location = target
            self._rebuild_location_index()
            self._add_memory(agent, f"Moved to {self.locations[target].name}.", importance=0.25, relevance=0.4, tags=["travel"])
            # A planned intent (Explore, Work, Read, …) is carried through the
            # travel action so arriving at a location produces its intended
            # consequence instead of silently becoming an unproductive move.
            if agent.action.intent:
                action = agent.action.intent
        if action in {"Eat", "Buy"}:
            if agent.money >= 5 and self.locations[agent.location].kind in {"shop", "cafe"} and self.locations[agent.location].resource > 0:
                # Shop Discount is a world event; otherwise meals cost five
                # simulation currency units.
                discount = 1.0
                for event in reversed(self.events):
                    if event.kind == "Shop Discount" and event.active_until >= self.minute:
                        discount = event.effects.get("food_cost_multiplier", 1.0)
                        break
                agent.money -= 5 * discount
                self.locations[agent.location].resource = max(0, self.locations[agent.location].resource - 1)
                agent.needs.hunger = clamp(agent.needs.hunger - 45)
                agent.needs.mood = clamp(agent.needs.mood + 4)
                agent.needs.health = clamp(agent.needs.health + 0.5)
                self._add_memory(agent, f"Bought a meal at {self.locations[agent.location].name}.", importance=0.4, relevance=0.8, tags=["economy", "food"])
                if agent.active_goal() and agent.active_goal().kind == "survival":
                    agent.active_goal().advance(1)
            elif agent.location == agent.home:
                agent.needs.hunger = clamp(agent.needs.hunger - 35)
                agent.needs.mood = clamp(agent.needs.mood + 2)
                if agent.active_goal() and agent.active_goal().kind == "survival":
                    agent.active_goal().advance(1)
            else:
                agent.needs.hunger = clamp(agent.needs.hunger + 3)
        elif action == "Sleep":
            agent.needs.energy = clamp(agent.needs.energy + 38)
            agent.needs.stress = clamp(agent.needs.stress - 8)
            agent.needs.health = clamp(agent.needs.health + 0.8)
            agent.needs.achievement = clamp(agent.needs.achievement - 3)
        elif action == "Work":
            wage = 12 + agent.traits.discipline / 20
            agent.money += wage
            agent.skills["work"] = min(100, agent.skills.get("work", 50) + 0.4)
            agent.needs.energy = clamp(agent.needs.energy - 16)
            agent.needs.hunger = clamp(agent.needs.hunger + 8)
            agent.needs.achievement = clamp(agent.needs.achievement - 20)
            agent.needs.mood = clamp(agent.needs.mood + (2 if agent.traits.discipline > 55 else -1))
            if agent.active_goal() and agent.active_goal().kind == "economy":
                agent.active_goal().advance(wage)
            self._add_memory(agent, f"Worked as a {agent.job}.", importance=0.45, relevance=0.75, tags=["work"])
        elif action == "Read":
            agent.skills["reading"] = min(100, agent.skills.get("reading", 20) + 1)
            agent.needs.curiosity = clamp(agent.needs.curiosity - 28)
            agent.needs.achievement = clamp(agent.needs.achievement - 8)
            agent.needs.mood = clamp(agent.needs.mood + 3)
            if agent.active_goal() and agent.active_goal().kind == "knowledge":
                agent.active_goal().advance(1)
            self._add_memory(agent, "Read something that widened a question.", importance=0.5, relevance=0.9, tags=["knowledge"])
        elif action == "Talk":
            others = self._agents_at(agent.location, exclude=agent.id)
            if others:
                self._interact(agent, others[0], "Greeting" if self.rng.random() > 0.15 else "Share")
                if agent.active_goal() and agent.active_goal().kind == "social":
                    agent.active_goal().advance(1)
        elif action == "Help":
            others = self._agents_at(agent.location, exclude=agent.id)
            if others:
                other = others[0]
                amount = min(5, agent.money)
                agent.money -= amount
                other.money += amount
                self._interact(agent, other, "Help")
                agent.needs.mood = clamp(agent.needs.mood + 4)
        elif action == "Explore":
            agent.needs.curiosity = clamp(agent.needs.curiosity - 24)
            agent.needs.mood = clamp(agent.needs.mood + 2)
            agent.needs.safety = clamp(agent.needs.safety - (2 if self.weather == "rain" else 0))
            self._add_memory(agent, f"Explored around {self.locations[agent.location].name}.", importance=0.5, relevance=0.9, tags=["exploration"])
            if agent.active_goal() and agent.active_goal().kind == "knowledge":
                agent.active_goal().advance(0.5)
        elif action == "Rest":
            agent.needs.energy = clamp(agent.needs.energy + 12)
            agent.needs.stress = clamp(agent.needs.stress - 5)
            agent.needs.mood = clamp(agent.needs.mood + 1)
        elif action == "Avoid":
            agent.needs.social_need = clamp(agent.needs.social_need + 3)
            agent.needs.stress = clamp(agent.needs.stress - 3)
        elif action == "Visit":
            if self.locations[agent.location].kind == "hospital":
                agent.needs.health = clamp(agent.needs.health + 15)
                agent.needs.safety = clamp(agent.needs.safety + 5)
            else:
                agent.needs.mood = clamp(agent.needs.mood + 1)
        elif action == "Wait":
            agent.needs.energy = clamp(agent.needs.energy + 1)
        agent.history.append({"minute": self.minute, "day": self.day, "action": action, "location": agent.location, "score": agent.action.score, "reason": agent.action.reason, "movement": original_action == "Move"})
        self.action_log.append({"minute": self.minute, "day": self.day, "agent_id": agent.id, "agent": agent.name, "action": action, "location": agent.location, "score": round(agent.action.score, 4), "reason": agent.action.reason, "movement": original_action == "Move"})
        self._day_action_buffer[agent.id].append(action)
        # Keep agent history bounded in memory; complete event log remains available.
        if len(agent.history) > 5000:
            del agent.history[:-5000]

    def _apply_needs(self, minutes: int = 1) -> None:
        scale = max(1, int(minutes))
        for agent in self.agents.values():
            if not agent.alive:
                continue
            # Rates are per minute; they create meaningful pressure over a day.
            agent.needs.hunger = clamp(agent.needs.hunger + 0.018 * scale)
            agent.needs.energy = clamp(agent.needs.energy - (0.010 * scale if agent.action.name not in {"Sleep", "Rest"} else -0.008 * scale))
            agent.needs.social_need = clamp(agent.needs.social_need + (0.006 * scale if agent.action.name != "Talk" else -0.04 * scale))
            agent.needs.curiosity = clamp(agent.needs.curiosity + 0.004 * scale)
            if agent.needs.hunger > 82:
                agent.needs.health = clamp(agent.needs.health - 0.015 * scale)
                agent.needs.stress = clamp(agent.needs.stress + 0.012 * scale)
            if agent.needs.energy < 18:
                agent.needs.stress = clamp(agent.needs.stress + 0.018 * scale)
            agent.needs.mood = clamp(agent.needs.mood + (0.004 * scale if agent.needs.hunger < 55 and agent.needs.energy > 35 else -0.006 * scale))
            # Slowly cool relationship conflict and memory recency.
            for rel in agent.relationships.values():
                rel.conflict = clamp(rel.conflict - 0.0005)
            for mem in agent.memories:
                mem.recency = max(0.05, mem.recency * 0.9995)

    def _generate_event(self) -> Optional[WorldEvent]:
        # At most one scheduled event per day, chosen deterministically from seed.
        if self.hour != 8 or self.minute_of_hour != 0:
            return None
        cycle = ["Rain", "Festival", "Shop Discount", "Job Opportunity", "Library Event", "Power Outage", "Illness Event"]
        kind = cycle[(self.day - 1 + self.seed) % len(cycle)]
        descriptions = {
            "Rain": "A steady rain makes outdoor routes less appealing.",
            "Festival": "The town square fills with music and food stalls.",
            "Shop Discount": "Food is cheaper today.",
            "Job Opportunity": "The workplace offers extra shifts.",
            "Library Event": "A reading circle draws curious residents.",
            "Power Outage": "Indoor places are dim; agents prefer the square.",
            "Illness Event": "A seasonal illness lowers health for a few residents.",
        }
        event = WorldEvent(f"event_{self.day:03d}", self.day, self.minute, kind, kind, descriptions[kind], active_until=self.minute + 720)
        self.events.append(event)
        self.event_log.append({"id": event.id, "day": event.day, "minute": event.minute, "kind": event.kind, "title": event.title, "description": event.description})
        self.weather = "rain" if kind == "Rain" else "clear"
        if kind == "Shop Discount":
            event.effects["food_cost_multiplier"] = 0.6
        elif kind == "Illness Event":
            for agent in sorted(self.agents.values(), key=lambda a: a.id)[: max(1, len(self.agents)//4)]:
                agent.needs.health = clamp(agent.needs.health - 8)
                self._add_memory(agent, "Felt unwell during a seasonal illness.", importance=0.7, relevance=0.9, tags=["health"])
        elif kind == "Festival":
            for loc in self.locations.values():
                if loc.kind == "square":
                    loc.resource += 50
        return event

    def _consolidate_memories(self) -> None:
        for agent in self.agents.values():
            # Promote salient working memories and produce a compact semantic fact.
            working = [m for m in agent.memories if m.layer == "working"]
            for mem in working:
                if mem.importance >= 0.65 or mem.relevance >= 0.85:
                    mem.layer = "episodic"
            # Even an ordinary social day leaves one durable episode.  This
            # prevents a low-salience routine from collapsing into semantic
            # identity facts only, while still bounding memory growth below.
            if working and not any(m.layer == "episodic" for m in agent.memories):
                top_working = max(working, key=lambda m: (m.retrieval_score, m.id))
                top_working.layer = "episodic"
            episodic = [m for m in agent.memories if m.layer == "episodic"]
            if episodic:
                top = sorted(episodic, key=lambda m: (-m.retrieval_score, m.id))[0]
                summary = f"Day {self.day}: {top.content}"
                # avoid duplicate summaries on repeated calls
                if not any(m.layer == "semantic" and m.content == summary for m in agent.memories):
                    agent.memories.append(Memory(f"{agent.id}_s{self.day:04d}", "semantic", summary, self.day, 0.55, 1.0, 0.8, top.participants, ["daily-summary"]))
            # Keep accessible memory bounded while preserving semantic facts.
            semantic = [m for m in agent.memories if m.layer == "semantic"]
            episodic = sorted([m for m in agent.memories if m.layer == "episodic"], key=lambda m: (-m.retrieval_score, m.id))
            keep_ids = {m.id for m in semantic} | {m.id for m in episodic[:80]}
            agent.memories = [m for m in agent.memories if m.id in keep_ids]

    def _write_journals(self) -> None:
        for agent in self.agents.values():
            # A small daily rent and household upkeep create a real economic
            # constraint.  The value is a simulation parameter, not a model of
            # any real housing market.
            rent = 9.0 + (agent.age_parameter % 4)
            agent.money = max(0.0, agent.money - rent)
            if agent.money <= 0.01:
                agent.needs.stress = clamp(agent.needs.stress + 3)
            self.locations["food_shop"].resource = min(1000.0, self.locations["food_shop"].resource + 35.0)
            self.locations["cafe"].resource = min(500.0, self.locations["cafe"].resource + 20.0)
            actions = self._day_action_buffer[agent.id]
            counts: Dict[str, int] = {}
            for a in actions:
                counts[a] = counts.get(a, 0) + 1
            main = [f"{k} × {v}" for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:4]]
            entry = JournalEntry(
                self.day - 1,
                main,
                [e["title"] for e in self.event_log if e.get("day") == self.day - 1],
                sorted(set(self._day_people_buffer[agent.id])),
                self._day_relationship_buffer[agent.id][-8:],
                [f"{g.title}: {g.status} ({g.progress:.0f}/{g.target:.0f})" for g in agent.goals],
                [m.content for m in sorted(agent.memories, key=lambda m: (-m.retrieval_score, m.id))[:3]],
            )
            agent.journal.append(asdict(entry))
            if len(agent.journal) > 365:
                del agent.journal[:-365]
            self._day_action_buffer[agent.id] = []
            self._day_people_buffer[agent.id] = []
            self._day_relationship_buffer[agent.id] = []

    def step(self, minutes: int = 1, *, save_snapshot: bool = True) -> None:
        """Advance simulation by a number of minutes."""
        for _ in range(max(0, int(minutes))):
            self._generate_event()
            self._apply_needs(1)
            for agent in sorted(self.agents.values(), key=lambda a: a.id):
                if not agent.alive:
                    continue
                if agent.action.remaining > 0:
                    agent.action.remaining -= 1
                    continue
                if agent.action.name != "Wait":
                    self._complete_action(agent)
                agent.action = self._select_action(agent)
            self.minute += 1
            # A day boundary occurs when the *next* minute is day start.
            if self.minute % 1440 == 0:
                self._consolidate_memories()
                self._write_journals()
                if save_snapshot:
                    self.save_snapshot(self.day)

    def _fast_step(self, minutes: int = 10, *, save_snapshot: bool = True) -> None:
        """Advance a coarse headless tick.

        Long benchmark runs (100 agents × 365 days) do not need a UI frame for
        every minute.  This path preserves event/day boundaries and all state
        invariants while evaluating each agent once per coarse interval.
        The regular ``step`` method remains the precise minute-level path used
        by the GUI and reproducibility tests.
        """
        span = max(1, int(minutes))
        start = self.minute
        target = start + span
        # Trigger scheduled events whose exact minute lies inside the interval.
        first_day = start // 1440
        last_day = (target - 1) // 1440
        for day_index in range(first_day, last_day + 1):
            event_minute = day_index * 1440 + 480
            if start <= event_minute < target:
                previous = self.minute
                self.minute = event_minute
                self._generate_event()
                self.minute = previous
        self._apply_needs(span)
        self._rebuild_location_index()
        for agent in sorted(self.agents.values(), key=lambda a: a.id):
            if not agent.alive:
                continue
            if agent.action.remaining > span:
                agent.action.remaining -= span
                continue
            if agent.action.name != "Wait":
                self._complete_action(agent)
            agent.action = self._select_action(agent)
        # Preserve daily consolidation and snapshots at every crossed boundary.
        boundary = ((start // 1440) + 1) * 1440
        while boundary <= target:
            self.minute = boundary
            self._consolidate_memories()
            self._write_journals()
            if save_snapshot:
                self.save_snapshot(self.day)
            boundary += 1440
        self.minute = target

    def run(self, days: int, *, progress: Optional[Any] = None, save_snapshots: bool = True, fast: bool = False, fast_interval: int = 30) -> Dict[str, Any]:
        target = self.minute + max(0, int(days)) * 1440
        while self.minute < target:
            if fast:
                self._fast_step(min(max(1, int(fast_interval)), target - self.minute), save_snapshot=save_snapshots)
            else:
                self.step(min(10, target - self.minute), save_snapshot=save_snapshots)
            if progress:
                progress(self)
        return self.summary()

    def run_until_day(self, day: int, *, progress: Optional[Any] = None) -> Dict[str, Any]:
        return self.run(max(0, int(day) - self.day), progress=progress)

    def save_snapshot(self, label: Optional[int] = None) -> None:
        key = int(label if label is not None else self.day)
        # Daily checkpoints contain state, not a duplicate copy of the full
        # append-only action/event traces.  SQLite stores those traces in
        # normalized tables; omitting them here keeps a 30-day database small.
        self.snapshots[key] = self.to_dict(include_snapshots=False, include_logs=False, include_history=False)

    def load_snapshot(self, label: int) -> bool:
        data = self.snapshots.get(int(label))
        if not data:
            return False
        restored = type(self).from_dict(copy.deepcopy(data), provider=self.provider)
        self.__dict__.update(restored.__dict__)
        return True

    def snapshot_view(self, label: int) -> Optional["Simulation"]:
        """Open a read-only-style copy of a snapshot for time-travel debugging.

        The returned object is detached; stepping it never mutates the source
        simulation or its original event/action logs.
        """
        data = self.snapshots.get(int(label))
        if not data:
            return None
        return Simulation.from_dict(copy.deepcopy(data), provider=self.provider)

    def summary(self) -> Dict[str, Any]:
        agents = list(self.agents.values())
        action_counts: Dict[str, int] = {}
        for row in self.action_log:
            action_counts[row["action"]] = action_counts.get(row["action"], 0) + 1
        visits: Dict[str, int] = {}
        for row in self.action_log:
            visits[row["location"]] = visits.get(row["location"], 0) + 1
        avg = lambda key: round(statistics.mean(getattr(a.needs, key) for a in agents), 3) if agents else 0.0
        stats = {
            "money": summarize([a.money for a in agents]),
            "energy": summarize([a.needs.energy for a in agents]),
            "health": summarize([a.needs.health for a in agents]),
            "goal_success": summarize([1.0 if g.status == "completed" else 0.0 for a in agents for g in a.goals], success=[g.status == "completed" for a in agents for g in a.goals]),
        }
        return {
            "experiment_id": self.experiment_id,
            "town_name": self.config.town_name,
            "seed": self.seed,
            "minute": self.minute,
            "day": self.day,
            "week": self.week,
            "population": len(agents),
            "average_needs": {k: avg(k) for k in ["energy", "hunger", "health", "mood", "social_need", "curiosity", "stress"]},
            "average_money": round(statistics.mean(a.money for a in agents), 3) if agents else 0.0,
            "action_frequency": action_counts,
            "popular_places": sorted(((self.locations[k].name, v) for k, v in visits.items()), key=lambda x: (-x[1], x[0])),
            "relationship_count": sum(1 for a in agents for r in a.relationships.values() if r.familiarity > 0),
            "memory_count": sum(len(a.memories) for a in agents),
            "goal_completion": round(sum(sum(g.status == "completed" for g in a.goals) for a in agents) / max(1, sum(len(a.goals) for a in agents)), 4),
            "events": len(self.event_log),
            "action_log_rows": len(self.action_log),
            "statistics": stats,
        }

    def social_graph_edges(self, *, min_familiarity: float = 0.0) -> List[Dict[str, Any]]:
        """Return unique undirected relationship edges for graph renderers."""
        edges: List[Dict[str, Any]] = []
        seen: set[Tuple[str, str]] = set()
        for aid, agent in sorted(self.agents.items()):
            for bid, rel in sorted(agent.relationships.items()):
                key = tuple(sorted((aid, bid)))
                if key in seen or rel.familiarity < min_familiarity:
                    continue
                seen.add(key)
                other = self.agents.get(bid)
                reverse = other.relationships.get(aid) if other else None
                edges.append({
                    "source": aid,
                    "target": bid,
                    "source_name": agent.name,
                    "target_name": other.name if other else bid,
                    "familiarity": round((rel.familiarity + (reverse.familiarity if reverse else rel.familiarity)) / (2 if reverse else 1), 3),
                    "trust": round((rel.trust + (reverse.trust if reverse else rel.trust)) / (2 if reverse else 1), 3),
                    "affinity": round((rel.affinity + (reverse.affinity if reverse else rel.affinity)) / (2 if reverse else 1), 3),
                    "conflict": round((rel.conflict + (reverse.conflict if reverse else rel.conflict)) / (2 if reverse else 1), 3),
                    "interactions": (rel.interactions + (reverse.interactions if reverse else 0)),
                })
        return sorted(edges, key=lambda e: (-e["familiarity"], e["source"], e["target"]))

    def popular_places(self, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        counts: Dict[str, int] = {lid: 0 for lid in self.locations}
        for row in self.action_log:
            lid = row.get("location")
            if lid in counts:
                counts[lid] += 1
        # Include current occupancy so a newly started experiment has useful data.
        for agent in self.agents.values():
            if agent.location in counts:
                counts[agent.location] += 1
        rows = [{"location_id": lid, "name": self.locations[lid].name, "visits": count} for lid, count in counts.items()]
        rows.sort(key=lambda x: (-x["visits"], x["name"]))
        return rows[:limit] if limit else rows

    def metrics_timeseries(self) -> List[Dict[str, Any]]:
        """Daily aggregate metrics suitable for line charts and comparisons."""
        buckets: Dict[int, Dict[str, int]] = {}
        for row in self.action_log:
            day = int(row.get("day", 1))
            bucket = buckets.setdefault(day, {"actions": 0, "exploration": 0, "movement": 0, "talk": 0})
            bucket["actions"] += 1
            if row.get("action") == "Explore": bucket["exploration"] += 1
            if row.get("action") == "Move" or row.get("movement"): bucket["movement"] += 1
            if row.get("action") == "Talk": bucket["talk"] += 1
        max_day = max(list(buckets) + [self.day])
        # State-level means are a useful deterministic fallback when a caller
        # did not retain per-tick snapshots; action counts remain day-specific.
        mean_energy = round(statistics.mean(a.needs.energy for a in self.agents.values()), 3) if self.agents else 0.0
        mean_money = round(statistics.mean(a.money for a in self.agents.values()), 3) if self.agents else 0.0
        return [{"day": day, **buckets.get(day, {"actions": 0, "exploration": 0, "movement": 0, "talk": 0}), "mean_energy": mean_energy, "mean_money": mean_money} for day in range(1, max_day + 1)]

    def compare(self, other: "Simulation") -> Dict[str, Any]:
        a, b = self.summary(), other.summary()
        keys = ["average_money", "relationship_count", "memory_count", "goal_completion", "events"]
        result = {k: {"a": a[k], "b": b[k], "difference": round(float(b[k]) - float(a[k]), 4)} for k in keys}
        for label, sim_a, sim_b in [("exploration", self, other), ("movement", self, other), ("knowledge", self, other)]:
            def total(sim: "Simulation") -> int:
                wanted = {"exploration": "Explore", "movement": "Move", "knowledge": "Read"}[label]
                return sum(row.get("action") == wanted for row in sim.action_log)
            av, bv = total(sim_a), total(sim_b)
            result[label] = {"a": av, "b": bv, "difference": bv - av}
        return result

    def to_dict(
        self,
        *,
        include_snapshots: bool = True,
        include_logs: bool = True,
        include_history: bool = True,
    ) -> Dict[str, Any]:
        def agent_dict(agent: Agent) -> Dict[str, Any]:
            d = asdict(agent)
            # asdict includes nested dataclasses and is JSON-safe.
            if not include_history:
                # Append-only action/journal history is stored in normalized
                # SQLite tables.  Do not duplicate it in every daily state
                # checkpoint, or long runs grow quadratically on disk.
                d["history"] = []
                d["journal"] = []
            return d
        data = {
            "schema_version": 1,
            "config": asdict(self.config),
            "seed": self.seed,
            "minute": self.minute,
            "weather": self.weather,
            "experiment_id": self.experiment_id,
            # JSON-compatible encoding of the PRNG state makes Save/Load
            # continuation deterministic, not merely state-equivalent at the
            # instant of loading.
            "rng_state": json.loads(json.dumps(self.rng.getstate())),
            "locations": [asdict(x) for x in self.locations.values()],
            "agents": [agent_dict(a) for a in self.agents.values()],
            "events": [asdict(x) for x in self.events],
            "event_log": self.event_log if include_logs else [],
            "action_log": self.action_log if include_logs else [],
        }
        if include_snapshots:
            data["snapshots"] = {str(k): v for k, v in self.snapshots.items()}
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, provider: Optional[CognitiveProvider] = None) -> "Simulation":
        cfg = SimulationConfig(**data.get("config", {}))
        obj = cls(cfg, provider=provider)
        obj.seed = int(data.get("seed", cfg.seed))
        obj.rng = random.Random(obj.seed)
        rng_state = data.get("rng_state")
        if rng_state is not None:
            def _tupleify(value: Any) -> Any:
                return tuple(_tupleify(v) for v in value) if isinstance(value, list) else value
            try:
                obj.rng.setstate(_tupleify(rng_state))
            except (TypeError, ValueError):
                obj.rng = random.Random(obj.seed)
        obj.minute = int(data.get("minute", 0))
        obj.weather = data.get("weather", "clear")
        obj.experiment_id = data.get("experiment_id", obj.experiment_id)
        obj.locations = {d["id"]: Location(**d) for d in data.get("locations", [])}
        obj.agents = {}
        for raw in data.get("agents", []):
            d = copy.deepcopy(raw)
            needs = Needs(**d.pop("needs"))
            traits = Traits(**d.pop("traits"))
            goals = [Goal(**g) for g in d.pop("goals", [])]
            rels = {k: Relationship(**v) for k, v in d.pop("relationships", {}).items()}
            mems = [Memory(**m) for m in d.pop("memories", [])]
            act = ActionState(**d.pop("action", {}))
            agent = Agent(needs=needs, traits=traits, goals=goals, relationships=rels, memories=mems, action=act, **d)
            obj.agents[agent.id] = agent
        obj.events = [WorldEvent(**e) for e in data.get("events", [])]
        obj.event_log = list(data.get("event_log", []))
        obj.action_log = list(data.get("action_log", []))
        obj.snapshots = {int(k): v for k, v in data.get("snapshots", {}).items()}
        obj._day_action_buffer = {a.id: [] for a in obj.agents.values()}
        obj._day_people_buffer = {a.id: [] for a in obj.agents.values()}
        obj._day_relationship_buffer = {a.id: [] for a in obj.agents.values()}
        obj._rebuild_location_index()
        return obj

    def state_hash(self) -> str:
        data = self.to_dict(include_snapshots=False)
        # action log can be huge; state hash should capture deterministic state and history summaries.
        payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return hashlib.sha256(payload).hexdigest()

    def headless_report(self) -> Dict[str, Any]:
        summary = self.summary()
        summary["top_explorers"] = sorted(((a.name, sum(x.get("action") == "Explore" for x in a.history)) for a in self.agents.values()), key=lambda x: (-x[1], x[0]))[:5]
        summary["top_social"] = sorted(((a.name, sum(r.familiarity for r in a.relationships.values())) for a in self.agents.values()), key=lambda x: (-x[1], x[0]))[:5]
        summary["fixed_habits"] = self.detect_habits()
        summary["social_graph_edges"] = self.social_graph_edges(min_familiarity=1.0)
        summary["place_ranking"] = self.popular_places()
        summary["metrics_timeseries"] = self.metrics_timeseries()
        return summary

    def detect_habits(self) -> List[Dict[str, Any]]:
        habits: List[Dict[str, Any]] = []
        for agent in self.agents.values():
            by_hour: Dict[int, Dict[str, int]] = {}
            for row in agent.history:
                h = (int(row["minute"]) // 60) % 24
                by_hour.setdefault(h, {})[row["action"]] = by_hour.setdefault(h, {}).get(row["action"], 0) + 1
            for h, counts in by_hour.items():
                action, n = max(counts.items(), key=lambda x: (x[1], x[0]))
                total = sum(counts.values())
                if total >= 4 and n / total >= 0.65:
                    habits.append({"agent": agent.name, "hour": h, "action": action, "consistency": round(n / total, 3)})
        return sorted(habits, key=lambda x: (x["agent"], x["hour"]))


def make_demo(days: int = 30, seed: int = 20261004) -> Simulation:
    sim = Simulation(SimulationConfig(seed=seed, agent_count=10, days=days, town_name="Small Town 01"))
    sim.run(days)
    return sim
