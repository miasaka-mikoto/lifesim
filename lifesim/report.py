"""Research reports and lightweight offline dashboard rendering."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Optional

from .core import Simulation


def markdown_report(sim: Simulation, *, title: Optional[str] = None) -> str:
    s = sim.headless_report()
    title = title or f"LifeSim — {sim.config.town_name}"
    lines = [
        f"# {title}",
        "",
        "> Artificial-life / agent simulation research prototype. This report describes rule-based simulated agents; it makes no claim about real consciousness or human psychology.",
        "",
        "## Reproducibility",
        "",
        f"- Experiment ID: `{sim.experiment_id}`",
        f"- Seed: `{sim.seed}`",
        f"- Simulation clock: Day {sim.day} ({sim.minute} minutes), week {sim.week}",
        f"- Population: {len(sim.agents)}",
        f"- State hash: `{sim.state_hash()}`",
        "",
        "## Research questions",
        "",
        "- Who explores most?",
        "- Who forms the most relationships?",
        "- Which places are popular?",
        "- Which routines become stable habits?",
        "- How does the social network evolve?",
        "",
        "## Summary",
        "",
        f"- Events: {s['events']}",
        f"- Relationship links with familiarity: {s['relationship_count']}",
        f"- Accessible memories: {s['memory_count']}",
        f"- Goal completion rate: {s['goal_completion']:.1%}",
        f"- Mean money: {s['average_money']:.2f}",
        "",
        "### Average needs",
        "",
        "| Need | Mean |\n|---|---:|",
    ]
    lines.extend(f"| {k.replace('_', ' ').title()} | {v:.2f} |" for k, v in s["average_needs"].items())
    lines += ["", "### Distribution statistics", "", "| Metric | Mean | Median | Std | P95 | 95% CI |", "|---|---:|---:|---:|---:|---:|"]
    for metric, vals in s.get("statistics", {}).items():
        lines.append(f"| {metric.replace('_', ' ').title()} | {vals.get('mean', 0):.2f} | {vals.get('median', 0):.2f} | {vals.get('std', 0):.2f} | {vals.get('p95', 0):.2f} | [{vals.get('ci_low', 0):.2f}, {vals.get('ci_high', 0):.2f}] |")
    lines += ["", "### Action frequency", "", "| Action | Count |\n|---|---:|"]
    lines.extend(f"| {k} | {v} |" for k, v in sorted(s["action_frequency"].items(), key=lambda x: (-x[1], x[0])))
    lines += ["", "### Popular places", "", "| Place | Visits / action completions |\n|---|---:|"]
    lines.extend(f"| {name} | {count} |" for name, count in s["popular_places"])
    lines += ["", "### Top explorers", "", "| Agent | Explore actions |\n|---|---:|"]
    lines.extend(f"| {name} | {count} |" for name, count in s["top_explorers"])
    lines += ["", "### Stable routines detected", ""]
    if s["fixed_habits"]:
        lines += ["| Agent | Hour | Action | Consistency |", "|---|---:|---|---:|"]
        lines.extend(f"| {h['agent']} | {h['hour']:02d}:00 | {h['action']} | {h['consistency']:.0%} |" for h in s["fixed_habits"][:30])
    else:
        lines.append("No routine crossed the 65% consistency threshold in this run.")
    lines += ["", "### Social graph edges", "", "| Source | Target | Familiarity | Trust | Affinity | Conflict |", "|---|---|---:|---:|---:|---:|"]
    for edge in s.get("social_graph_edges", [])[:40]:
        lines.append(f"| {edge['source_name']} | {edge['target_name']} | {edge['familiarity']:.1f} | {edge['trust']:.1f} | {edge['affinity']:.1f} | {edge['conflict']:.1f} |")
    if not s.get("social_graph_edges"):
        lines.append("| — | — | 0 | 0 | 0 | 0 |")
    lines += ["", "## Limitations", "", "- The default provider is a transparent rule system with template dialogue.", "- Need and relationship values are simulation parameters, not psychological diagnoses.", "- Results are illustrative and should not be interpreted as empirical human behavior.", "", "## Next experiment", "", "Change the seed, population or trait distribution and compare the resulting report with `Simulation.compare`. "]
    return "\n".join(lines) + "\n"


def html_report(sim: Simulation, *, title: Optional[str] = None) -> str:
    md = markdown_report(sim, title=title)
    # Keep a standalone HTML export without external dependencies.  Markdown is
    # intentionally preserved in a preformatted research-notebook view.
    safe = html.escape(md)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title or 'LifeSim Report')}</title><style>body{{background:#10141c;color:#e7edf5;font:15px system-ui;line-height:1.5;margin:40px auto;max-width:980px;padding:0 20px}}pre{{white-space:pre-wrap;background:#171d28;padding:24px;border-radius:12px;border:1px solid #2c3748}}h1{{color:#8ad7ff}}</style></head><body><pre>{safe}</pre></body></html>"


def dashboard_svg(sim: Simulation, path: str | Path, *, width: int = 1280, height: int = 760) -> Path:
    """Render a dependency-free dark observatory dashboard as SVG."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    s = sim.summary()
    bg, panel, text, muted, accent, accent2 = "#0f141c", "#18222e", "#e8f0f7", "#8aa0b3", "#6ed0ff", "#9cf3b1"
    esc = lambda v: html.escape(str(v))
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>", f"<rect width='100%' height='100%' fill='{bg}'/>"]
    out += [f"<text x='36' y='42' fill='{text}' font-size='26' font-family='system-ui' font-weight='700'>LifeSim · Simulation Observatory</text>", f"<text x='36' y='68' fill='{muted}' font-size='13' font-family='system-ui'>{esc(sim.config.town_name)} · seed {sim.seed} · {sim.time_label} · offline rule-based research prototype</text>"]
    cards = [(36, 92, 180, 76, "Population", len(sim.agents), accent), (230, 92, 180, 76, "Mean energy", f"{s['average_needs']['energy']:.1f}", accent2), (424, 92, 180, 76, "Mean money", f"{s['average_money']:.1f}", accent), (618, 92, 180, 76, "Relationships", s['relationship_count'], accent2), (812, 92, 180, 76, "Memories", s['memory_count'], accent)]
    for x, y, w, h, label, value, color in cards:
        out += [f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='10' fill='{panel}' stroke='#28394b'/>", f"<text x='{x+16}' y='{y+25}' fill='{muted}' font-size='12' font-family='system-ui'>{esc(label)}</text>", f"<text x='{x+16}' y='{y+57}' fill='{color}' font-size='25' font-family='system-ui' font-weight='700'>{esc(value)}</text>"]
    # World map
    out += [f"<rect x='36' y='190' width='570' height='520' rx='12' fill='{panel}' stroke='#28394b'/>", f"<text x='58' y='222' fill='{text}' font-size='17' font-family='system-ui' font-weight='600'>World</text>"]
    scale = 52
    for loc in sim.locations.values():
        x, y = 68 + loc.x * scale, 240 + loc.y * scale
        out += [f"<rect x='{x-20}' y='{y-14}' width='40' height='28' rx='5' fill='#243749' stroke='#42627c'/>", f"<text x='{x}' y='{y+3}' text-anchor='middle' fill='{text}' font-size='8' font-family='system-ui'>{esc(loc.name[:10])}</text>"]
    for idx, agent in enumerate(sorted(sim.agents.values(), key=lambda a: a.id)):
        loc = sim.locations[agent.location]
        # Avoid Python's process-randomized ``hash()`` so exported dashboards
        # are reproducible across runs and machines.
        x, y = 68 + loc.x * scale + ((idx * 11) % 18 - 9), 240 + loc.y * scale + ((idx * 7) % 18 - 9)
        out += [f"<circle cx='{x}' cy='{y}' r='6' fill='{accent2}' stroke='#0c1118' stroke-width='2'/>", f"<title>{esc(agent.name)} · {esc(agent.action.name)}</title>"]
    # Bars for needs
    out += [f"<rect x='626' y='190' width='618' height='250' rx='12' fill='{panel}' stroke='#28394b'/>", f"<text x='648' y='222' fill='{text}' font-size='17' font-family='system-ui' font-weight='600'>Population needs</text>"]
    keys = ["energy", "hunger", "health", "mood", "social_need", "curiosity", "stress"]
    for i, key in enumerate(keys):
        y = 255 + i * 25
        val = s["average_needs"].get(key, 0)
        out += [f"<text x='648' y='{y+4}' fill='{muted}' font-size='11' font-family='system-ui'>{esc(key.replace('_',' ').title())}</text>", f"<rect x='760' y='{y-8}' width='420' height='13' rx='6' fill='#24313d'/>", f"<rect x='760' y='{y-8}' width='{max(0,min(420,val*4.2)):.1f}' height='13' rx='6' fill='{accent}'/>", f"<text x='1190' y='{y+4}' text-anchor='end' fill='{text}' font-size='11' font-family='system-ui'>{val:.1f}</text>"]
    # Action bars
    out += [f"<rect x='626' y='462' width='618' height='248' rx='12' fill='{panel}' stroke='#28394b'/>", f"<text x='648' y='494' fill='{text}' font-size='17' font-family='system-ui' font-weight='600'>Action frequency</text>"]
    actions = list(sorted(s["action_frequency"].items(), key=lambda x: (-x[1], x[0])))[:8]
    mx = max([v for _, v in actions] or [1])
    for i, (name, count) in enumerate(actions):
        y = 522 + i * 22
        out += [f"<text x='648' y='{y+4}' fill='{muted}' font-size='11' font-family='system-ui'>{esc(name)}</text>", f"<rect x='760' y='{y-8}' width='{390*count/mx:.1f}' height='13' rx='6' fill='{accent2}'/>", f"<text x='1188' y='{y+4}' text-anchor='end' fill='{text}' font-size='11' font-family='system-ui'>{count}</text>"]
    out.append("</svg>")
    path.write_text("\n".join(out), encoding="utf-8")
    return path


def dashboard_png(sim: Simulation, path: str | Path) -> Optional[Path]:
    """Optional PNG export using matplotlib if installed; SVG remains canonical."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    s = sim.summary()
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), facecolor="#10141c")
    for ax in axes:
        ax.set_facecolor("#18222e")
        ax.tick_params(colors="#dce8f2")
        for spine in ax.spines.values(): spine.set_color("#35495d")
    needs = s["average_needs"]
    axes[0].bar(list(needs), list(needs.values()), color="#6ed0ff")
    axes[0].set_ylim(0, 100); axes[0].set_title("Population needs", color="white"); axes[0].tick_params(axis="x", rotation=45)
    acts = sorted(s["action_frequency"].items(), key=lambda x: -x[1])[:8]
    axes[1].bar([a for a, _ in acts], [v for _, v in acts], color="#9cf3b1")
    axes[1].set_title("Action frequency", color="white"); axes[1].tick_params(axis="x", rotation=45)
    fig.suptitle(f"LifeSim · {sim.config.town_name} · {sim.time_label}", color="white", fontsize=16)
    fig.tight_layout()
    fig.savefig(path, dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def social_graph_svg(sim: Simulation, path: str | Path, *, width: int = 900, height: int = 620) -> Path:
    """Render the relationship network as a standalone SVG artifact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    edges = sim.social_graph_edges(min_familiarity=0.1)
    nodes = sorted(sim.agents.values(), key=lambda a: a.id)
    import math
    cx, cy = width / 2, height / 2 + 20
    radius = min(width, height) * 0.34
    positions = {a.id: (cx + radius * math.cos(2 * math.pi * i / max(1, len(nodes)) - math.pi / 2), cy + radius * math.sin(2 * math.pi * i / max(1, len(nodes)) - math.pi / 2)) for i, a in enumerate(nodes)}
    esc = lambda v: html.escape(str(v))
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>", "<rect width='100%' height='100%' fill='#0f141c'/>", "<text x='28' y='38' fill='#e8f0f7' font-family='system-ui' font-size='24' font-weight='700'>LifeSim · Social Graph</text>", f"<text x='28' y='62' fill='#8aa0b3' font-family='system-ui' font-size='12'>Edges encode familiarity, trust, affinity and conflict · {esc(sim.time_label)}</text>"]
    for e in edges:
        x1, y1 = positions[e["source"]]; x2, y2 = positions[e["target"]]
        width_px = max(1, min(7, e["familiarity"] / 10))
        color = "#ff9f9f" if e["conflict"] > e["affinity"] else "#6ed0ff"
        out.append(f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' stroke='{color}' stroke-opacity='.65' stroke-width='{width_px:.1f}'><title>{esc(e['source_name'])} ↔ {esc(e['target_name'])}: familiarity {e['familiarity']:.1f}, trust {e['trust']:.1f}, affinity {e['affinity']:.1f}, conflict {e['conflict']:.1f}</title></line>")
    for a in nodes:
        x, y = positions[a.id]
        out += [f"<circle cx='{x:.1f}' cy='{y:.1f}' r='17' fill='#9cf3b1' stroke='#12202b' stroke-width='3'/>", f"<text x='{x:.1f}' y='{y+4:.1f}' text-anchor='middle' fill='#0f141c' font-family='system-ui' font-size='10' font-weight='700'>{esc(a.name[:8])}</text>"]
    out.append("</svg>")
    path.write_text("\n".join(out), encoding="utf-8")
    return path
