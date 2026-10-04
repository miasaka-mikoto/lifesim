"""Tkinter-based LifeSim simulation observatory.

The GUI is deliberately a research instrument rather than a game HUD: it
surfaces state, decision scores, memory layers, relationships and trace rows.
It remains fully usable offline with the bundled rule engine.
"""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional

from .core import Simulation, SimulationConfig
from .persistence import LifeSimDB
from .report import html_report, markdown_report


BG = "#0f141c"
PANEL = "#18222e"
PANEL_2 = "#202d3a"
TEXT = "#e8f0f7"
MUTED = "#90a7ba"
ACCENT = "#6ed0ff"
GREEN = "#9cf3b1"
ORANGE = "#ffcb8a"


class LifeSimApp:
    def __init__(self, root: tk.Tk, *, db_path: str = "reports/demo/lifesim.sqlite3"):
        self.root = root
        self.root.title("LifeSim · 数字生命沙盒 · Simulation Observatory")
        self.root.geometry("1450x900")
        self.root.configure(bg=BG)
        self.db_path = db_path
        self.db: Optional[LifeSimDB] = None
        try:
            if Path(db_path).exists():
                self.db = LifeSimDB(db_path)
                self.sim = self.db.load()
            else:
                self.sim = Simulation(SimulationConfig(seed=20261004, agent_count=10, days=30))
        except Exception:
            self.sim = Simulation(SimulationConfig(seed=20261004, agent_count=10, days=30))
        self.running = False
        self.speed = 1
        self.selected_agent: Optional[str] = None
        self._build_style()
        self._build_layout()
        self.refresh()

    def _build_style(self) -> None:
        style = ttk.Style()
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 18, "bold"))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("PanelTitle.TLabel", background=PANEL, foreground=ACCENT, font=("Segoe UI", 11, "bold"))
        style.configure("TButton", background=PANEL_2, foreground=TEXT, borderwidth=0, padding=(8, 5))
        style.map("TButton", background=[("active", "#304657")])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, borderwidth=0, rowheight=24)
        style.configure("Treeview.Heading", background=PANEL_2, foreground=ACCENT)
        style.map("Treeview", background=[("selected", "#31506b")])

    def _build_layout(self) -> None:
        top = ttk.Frame(self.root); top.pack(fill="x", padx=18, pady=(15, 6))
        ttk.Label(top, text="LifeSim", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="  数字生命沙盒 · Artificial-life research prototype", style="Muted.TLabel").pack(side="left", pady=6)
        self.clock_var = tk.StringVar(); ttk.Label(top, textvariable=self.clock_var, foreground=ACCENT, background=BG, font=("Segoe UI", 12, "bold")).pack(side="right")
        controls = ttk.Frame(self.root); controls.pack(fill="x", padx=18, pady=(0, 8))
        self.run_button = ttk.Button(controls, text="▶ Run", command=self.toggle_run); self.run_button.pack(side="left", padx=(0, 5))
        ttk.Button(controls, text="Step", command=lambda: self.advance(1)).pack(side="left", padx=2)
        for label, speed in [("1×", 1), ("5×", 5), ("20×", 20), ("100×", 100)]:
            ttk.Button(controls, text=label, command=lambda s=speed: self.set_speed(s)).pack(side="left", padx=2)
        ttk.Button(controls, text="Save", command=self.save).pack(side="left", padx=(18, 2))
        ttk.Button(controls, text="Export Report", command=self.export_report).pack(side="left", padx=2)
        ttk.Label(controls, text="  RuleBasedProvider · offline · no API keys", style="Muted.TLabel").pack(side="right")

        body = ttk.Frame(self.root); body.pack(fill="both", expand=True, padx=18, pady=5)
        left = ttk.Frame(body, style="Panel.TFrame", width=245); left.pack(side="left", fill="y", padx=(0, 8)); left.pack_propagate(False)
        center = ttk.Frame(body, style="Panel.TFrame"); center.pack(side="left", fill="both", expand=True, padx=4)
        right = ttk.Frame(body, style="Panel.TFrame", width=350); right.pack(side="left", fill="y", padx=(8, 0)); right.pack_propagate(False)
        self._build_left(left); self._build_center(center); self._build_right(right)
        self.log = tk.Text(self.root, height=8, bg="#111a24", fg=MUTED, insertbackground=TEXT, relief="flat", font=("Consolas", 9))
        self.log.pack(fill="x", padx=18, pady=(8, 14))

    def _build_left(self, frame: ttk.Frame) -> None:
        ttk.Label(frame, text="AGENTS", style="PanelTitle.TLabel").pack(anchor="w", padx=12, pady=(12, 5))
        self.agent_tree = ttk.Treeview(frame, show="tree", height=16); self.agent_tree.pack(fill="x", padx=8)
        self.agent_tree.bind("<<TreeviewSelect>>", self.on_agent_select)
        ttk.Label(frame, text="LOCATIONS", style="PanelTitle.TLabel").pack(anchor="w", padx=12, pady=(14, 5))
        self.loc_tree = ttk.Treeview(frame, columns=("count",), show="tree headings", height=11); self.loc_tree.heading("#0", text="Place"); self.loc_tree.heading("count", text="Agents"); self.loc_tree.column("#0", width=145); self.loc_tree.column("count", width=50, anchor="center"); self.loc_tree.pack(fill="x", padx=8)
        ttk.Label(frame, text="EXPERIMENT", style="PanelTitle.TLabel").pack(anchor="w", padx=12, pady=(14, 4))
        self.exp_var = tk.StringVar(value=self.sim.experiment_id)
        ttk.Label(frame, textvariable=self.exp_var, style="Panel.TLabel", wraplength=210).pack(anchor="w", padx=12)
        ttk.Label(frame, text="Seeded, replayable, no hidden chain-of-thought.", style="Panel.TLabel", wraplength=210).pack(anchor="w", padx=12, pady=8)
        ttk.Label(frame, text="TIMELINE / SNAPSHOTS", style="PanelTitle.TLabel").pack(anchor="w", padx=12, pady=(8, 4))
        self.timeline_tree = ttk.Treeview(frame, show="tree", height=6)
        self.timeline_tree.pack(fill="x", padx=8, pady=(0, 8))
        self.timeline_tree.bind("<<TreeviewSelect>>", self.on_snapshot_select)

    def _build_center(self, frame: ttk.Frame) -> None:
        ttk.Label(frame, text="WORLD OBSERVATORY", style="PanelTitle.TLabel").pack(anchor="w", padx=14, pady=(12, 2))
        self.world = tk.Canvas(frame, bg="#111a24", highlightthickness=0, height=510)
        self.world.pack(fill="both", expand=True, padx=10, pady=8)
        self.world.bind("<Button-1>", self.on_world_click)
        self.stats = tk.Text(frame, height=8, bg=PANEL, fg=MUTED, relief="flat", font=("Consolas", 9), state="disabled")
        self.stats.pack(fill="x", padx=10, pady=(0, 10))

    def _build_right(self, frame: ttk.Frame) -> None:
        ttk.Label(frame, text="INSPECTOR", style="PanelTitle.TLabel").pack(anchor="w", padx=12, pady=(12, 5))
        self.inspector = tk.Text(frame, bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Consolas", 9), wrap="word")
        self.inspector.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        ttk.Label(frame, text="DECISION SCORES", style="PanelTitle.TLabel").pack(anchor="w", padx=12, pady=(3, 2))
        self.score_canvas = tk.Canvas(frame, height=190, bg=PANEL, highlightthickness=0); self.score_canvas.pack(fill="x", padx=8, pady=(0, 10))

    def set_speed(self, speed: int) -> None:
        self.speed = speed
        self.running = True
        self.run_button.configure(text=f"❚❚ Pause · {speed}×")
        self._loop()

    def toggle_run(self) -> None:
        self.running = not self.running
        self.run_button.configure(text="❚❚ Pause" if self.running else "▶ Run")
        if self.running: self._loop()

    def advance(self, minutes: int) -> None:
        self.sim.step(minutes)
        self.refresh()

    def _loop(self) -> None:
        if not self.running: return
        self.sim.step(max(1, self.speed * 5), save_snapshot=False)
        self.refresh()
        self.root.after(90 if self.speed >= 20 else 180, self._loop)

    def on_agent_select(self, _event=None) -> None:
        selected = self.agent_tree.selection()
        if selected:
            self.selected_agent = selected[0]
            self.refresh_inspector()

    def on_snapshot_select(self, _event=None) -> None:
        selected = self.timeline_tree.selection()
        if not selected:
            return
        try:
            label = int(selected[0].replace("snapshot_", ""))
            snap = self.sim.snapshot_view(label)
            if snap is None:
                return
            summary = snap.summary()
            self._set_text(self.inspector, f"TIME TRAVEL VIEW · Day {label}\n\nDetached read-only snapshot\nClock: {snap.time_label}\nPopulation: {summary['population']}\nMean money: {summary['average_money']:.2f}\nRelationships: {summary['relationship_count']}\nMemories: {summary['memory_count']}\n\nStepping this view cannot mutate the live simulation.\nSelect the current experiment again to return to the live inspector.")
        except (TypeError, ValueError):
            return

    def on_world_click(self, event) -> None:
        # Select closest marker from canvas click.
        if not self.sim.agents: return
        best = None; best_d = 10**9
        for a in self.sim.agents.values():
            loc = self.sim.locations[a.location]
            x = 45 + loc.x * 65; y = 45 + loc.y * 65
            d = (x - event.x) ** 2 + (y - event.y) ** 2
            if d < best_d: best_d, best = d, a
        if best and best_d < 80**2:
            self.selected_agent = best.id
            self.agent_tree.selection_set(best.id)
            self.refresh_inspector()

    def refresh(self) -> None:
        self.clock_var.set(f"{self.sim.time_label} · Week {self.sim.week} · {self.sim.weather.title()}")
        self.exp_var.set(f"{self.sim.experiment_id}\nseed={self.sim.seed} · population={len(self.sim.agents)}")
        self.agent_tree.delete(*self.agent_tree.get_children())
        for a in sorted(self.sim.agents.values(), key=lambda x: x.id):
            self.agent_tree.insert("", "end", iid=a.id, text=f"{a.name}  ·  {a.action.name}")
        self.loc_tree.delete(*self.loc_tree.get_children())
        for loc in sorted(self.sim.locations.values(), key=lambda x: x.id):
            count = sum(a.location == loc.id for a in self.sim.agents.values())
            self.loc_tree.insert("", "end", iid=loc.id, text=loc.name, values=(count,))
        self.timeline_tree.delete(*self.timeline_tree.get_children())
        for label in sorted(self.sim.snapshots):
            self.timeline_tree.insert("", "end", iid=f"snapshot_{label}", text=f"Day {label}")
        self.draw_world(); self.refresh_stats(); self.refresh_inspector(); self.refresh_scores()
        recent = self.sim.action_log[-5:]
        if recent:
            self.log.configure(state="normal")
            self.log.insert("end", "\n".join(f"{r['day']:02d} {r['agent']} → {r['action']} @ {r['location']}" for r in recent) + "\n")
            self.log.see("end"); self.log.configure(state="disabled")

    def draw_world(self) -> None:
        c = self.world; c.delete("all")
        c.create_text(16, 14, anchor="nw", text="Agents are simulated parameters, not diagnoses", fill=MUTED, font=("Segoe UI", 9))
        for loc in self.sim.locations.values():
            x, y = 45 + loc.x * 65, 45 + loc.y * 65
            c.create_rectangle(x - 30, y - 20, x + 30, y + 20, fill="#243749", outline="#43637d", width=1)
            c.create_text(x, y, text=loc.name[:14], fill=TEXT, font=("Segoe UI", 8))
        for i, a in enumerate(sorted(self.sim.agents.values(), key=lambda x: x.id)):
            loc = self.sim.locations[a.location]; x, y = 45 + loc.x * 65 + ((i * 13) % 20 - 10), 45 + loc.y * 65 + ((i * 7) % 18 - 9)
            color = GREEN if a.id == self.selected_agent else ACCENT
            c.create_oval(x - 7, y - 7, x + 7, y + 7, fill=color, outline="#0c1118", width=2)
            c.create_text(x + 10, y, text=a.name, anchor="w", fill=TEXT, font=("Segoe UI", 8))

    def refresh_stats(self) -> None:
        s = self.sim.summary()
        lines = [f"Population {s['population']}   Mean money {s['average_money']:.1f}   Relationships {s['relationship_count']}   Memories {s['memory_count']}", f"Events {s['events']}   Goal completion {s['goal_completion']:.1%}", "", "Average needs: " + " · ".join(f"{k} {v:.1f}" for k, v in s["average_needs"].items())]
        self.stats.configure(state="normal"); self.stats.delete("1.0", "end"); self.stats.insert("end", "\n".join(lines)); self.stats.configure(state="disabled")

    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal"); widget.delete("1.0", "end"); widget.insert("end", text); widget.configure(state="normal")

    def refresh_inspector(self) -> None:
        if not self.selected_agent or self.selected_agent not in self.sim.agents:
            self._set_text(self.inspector, "Select an agent from the left or the map.\n\nThe inspector exposes needs, traits, goals, relationships, memory layers, history and the current action.")
            return
        a = self.sim.agents[self.selected_agent]
        rel = sorted(a.relationships.values(), key=lambda r: (-r.familiarity, r.other_id))[:6]
        lines = [f"{a.name}  [{a.id}]", f"Location: {self.sim.locations[a.location].name}", f"Job: {a.job}   Money: {a.money:.2f}", f"Action: {a.action.name} ({a.action.remaining} min)", "", "NEEDS"]
        lines.extend(f"  {k:14} {v:6.1f}" for k, v in a.needs.as_dict().items())
        lines.append("\nTRAITS"); lines.extend(f"  {k:20} {v:5.1f}" for k, v in a.traits.as_dict().items())
        lines.append("\nGOALS"); lines.extend(f"  {'✓' if g.status == 'completed' else '·'} {g.title}: {g.progress:.1f}/{g.target:.1f}" for g in a.goals)
        lines.append("\nRELATIONSHIPS"); lines.extend(f"  {r.other_id}: fam {r.familiarity:.0f} · trust {r.trust:.0f} · aff {r.affinity:.1f} · conflict {r.conflict:.1f}" for r in rel)
        lines.append("\nMEMORY (accessible, no hidden chain-of-thought)"); lines.extend(f"  [{m.layer}] {m.content[:80]}" for m in sorted(a.memories, key=lambda m: (-m.retrieval_score, m.id))[:8])
        self._set_text(self.inspector, "\n".join(lines))

    def refresh_scores(self) -> None:
        c = self.score_canvas; c.delete("all")
        if not self.selected_agent or self.selected_agent not in self.sim.agents: return
        scores = self.sim.decision_scores(self.selected_agent)
        top = sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:8]
        mx = max([x[1] for x in top] or [1])
        for i, (name, value) in enumerate(top):
            y = 15 + i * 21; width = max(0, min(220, value / max(mx, 0.1) * 220))
            c.create_text(4, y + 6, anchor="w", text=name, fill=MUTED, font=("Consolas", 9)); c.create_rectangle(78, y, 78 + width, y + 12, fill=ACCENT if i == 0 else "#466b82", outline=""); c.create_text(305, y + 6, text=f"{value:.2f}", fill=TEXT, font=("Consolas", 9))

    def save(self) -> None:
        try:
            self.db = self.db or LifeSimDB(self.db_path)
            self.db.save(self.sim, name=f"GUI {self.sim.config.town_name}")
            for label, state in self.sim.snapshots.items(): self.db.save_snapshot(Simulation.from_dict(state), label)
            self.log.configure(state="normal"); self.log.insert("end", f"Saved {self.sim.experiment_id} to {self.db_path}\n"); self.log.configure(state="disabled")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def export_report(self) -> None:
        out = Path(self.db_path).parent; out.mkdir(parents=True, exist_ok=True)
        (out / "gui_report.md").write_text(markdown_report(self.sim), encoding="utf-8")
        (out / "gui_report.html").write_text(html_report(self.sim), encoding="utf-8")
        messagebox.showinfo("Report exported", f"Wrote reports to {out}")


def run_gui(*, db_path: str = "reports/demo/lifesim.sqlite3") -> None:
    root = tk.Tk()
    app = LifeSimApp(root, db_path=db_path)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.save(), root.destroy()))
    root.mainloop()
