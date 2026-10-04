"""Offline report/export checks."""

from __future__ import annotations

from lifesim.core import Simulation, SimulationConfig
from lifesim.report import dashboard_svg, html_report, markdown_report, social_graph_svg


def test_markdown_and_html_report_contain_reproducibility_metadata() -> None:
    sim = Simulation(SimulationConfig(seed=314, agent_count=3))
    sim.run(1)
    markdown = markdown_report(sim)
    html = html_report(sim)
    assert "Artificial-life / agent simulation research prototype" in markdown
    assert f"`{sim.seed}`" in markdown
    assert sim.experiment_id in markdown
    assert "Reproducibility" in html
    assert "<!doctype html>" in html
    assert "makes no claim about real consciousness" in markdown


def test_dashboard_svg_is_standalone_and_escapes_text(tmp_path) -> None:
    sim = Simulation(SimulationConfig(seed=315, agent_count=2, town_name="Research & Demo"))
    sim.run(1)
    path = dashboard_svg(sim, tmp_path / "dashboard.svg")
    body = path.read_text(encoding="utf-8")
    assert body.startswith("<svg ")
    assert "Simulation Observatory" in body
    assert "Research &amp; Demo" in body
    assert body.endswith("</svg>")


def test_social_graph_svg_contains_relationship_dimensions(tmp_path) -> None:
    sim = Simulation(SimulationConfig(seed=316, agent_count=3))
    sim.run(2)
    path = social_graph_svg(sim, tmp_path / "social.svg")
    body = path.read_text(encoding="utf-8")
    assert "Social Graph" in body
    assert "familiarity" in body
    assert "trust" in body
    assert "affinity" in body
    assert "conflict" in body
