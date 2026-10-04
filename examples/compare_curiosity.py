"""Run a small controlled comparison without any model API."""
from lifesim.core import Simulation, SimulationConfig


def main() -> None:
    high = Simulation(SimulationConfig(seed=7, agent_count=10, town_name="High Curiosity"))
    low = Simulation(SimulationConfig(seed=7, agent_count=10, town_name="Low Curiosity"))
    for agent in high.agents.values():
        agent.traits.curiosity = 90
    for agent in low.agents.values():
        agent.traits.curiosity = 10
    high.run(30)
    low.run(30)
    print(high.compare(low))


if __name__ == "__main__":
    main()
