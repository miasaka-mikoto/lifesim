# LifeSim Screenshots / Visual Artifacts

The headless renderer produces portable visual artifacts without a browser or
network connection:

- `reports/demo/observatory_dashboard.svg` — vector observatory dashboard;
- `reports/demo/social_graph.svg` — relationship network with familiarity,
  trust, affinity and conflict encoded in each edge;
- `reports/demo/observatory_dashboard.png` — optional raster dashboard when
  matplotlib is installed;
- the Tkinter `gui` command — interactive world map, agent inspector,
  decision-score bars, action log and timeline controls.

SVG is the canonical required artifact because it has no optional dependency.
The PNG is a convenience export and may be omitted in a minimal standard
library installation.
