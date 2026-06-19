"""
Generate an HTML event dashboard for the Autonomous Retail Pop-Up simulation.

Usage:
    python simulation/dashboard.py
    Then open dashboard.html in your browser.
"""

import sys
import os
import json
import contextlib
import io
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.message_bus import MessageBus
from simulation.shared_state import Blackboard
from simulation.orchestrator import Orchestrator
from agents.demand_agent import DemandAgent
from agents.inventory_agent import InventoryAgent
from agents.pricing_agent import PricingAgent
from agents.labor_agent import LaborAgent
from agents.cx_agent import CXAgent


# ── simulation runner ────────────────────────────────────────────────────────

def run_silent():
    """Run the full 4-scenario simulation silently and return captured data."""
    bb  = Blackboard()
    bus = MessageBus()
    orc = Orchestrator(bus, bb)

    demand    = DemandAgent(bus, bb)
    inventory = InventoryAgent(bus, bb, orc)
    pricing   = PricingAgent(bus, bb)
    labor     = LaborAgent(bus, bb)
    cx        = CXAgent(bus, bb)
    agents    = [demand, inventory, pricing, labor, cx]

    snapshots = []

    def snap(t, scenario):
        snapshots.append({
            "t":            t,
            "scenario":     scenario,
            "bev":          bb.stock["beverages"],
            "snacks":       bb.stock["snacks"],
            "merch":        bb.stock["merchandise"],
            "price_bev":    round(bb.prices["beverages"], 2),
            "price_snacks": round(bb.prices["snacks"], 2),
            "price_merch":  round(bb.prices["merchandise"], 2),
            "satisfaction": bb.satisfaction_score,
            "wait_time":    bb.wait_time,
            "staff":        bb.staff_count,
            "revenue":      round(bb.total_revenue, 2),
            "foot_traffic": bb.foot_traffic,
        })

    for t in range(0, 45):
        orc.accrue_labor()
        for a in agents: a.tick(t)
        if t % 5 == 0: snap(t, "Normal Operation")

    demand.apply_spike("beverages", 2.5)
    for t in range(45, 90):
        orc.accrue_labor()
        for a in agents: a.tick(t)
        if t % 5 == 0: snap(t, "Demand Spike")

    bb.stock["beverages"]       = 0
    bb.demand_rate["beverages"] = 8
    bb.foot_traffic             = 50
    for t in range(90, 150):
        orc.accrue_labor()
        for a in agents: a.tick(t)
        if t % 5 == 0: snap(t, "Stockout")

    for t in range(150, 180):
        orc.accrue_labor()
        if t == 150: inventory.initiate_clearance(t)
        if t == 165: inventory.initiate_clearance(t)
        for a in agents: a.tick(t)
        if t % 5 == 0: snap(t, "Clearance")

    inventory.record_waste()

    cogs         = sum(bb.units_sold[p] * bb.costs[p] for p in bb.units_sold)
    total_cost   = cogs + bb.total_labor_cost
    gross_margin = (bb.total_revenue - cogs) / bb.total_revenue * 100 if bb.total_revenue else 0

    summary = {
        "revenue":         round(bb.total_revenue, 2),
        "cogs":            round(cogs, 2),
        "labor_cost":      round(bb.total_labor_cost, 2),
        "total_cost":      round(total_cost, 2),
        "gross_margin":    round(gross_margin, 1),
        "satisfaction":    bb.satisfaction_score,
        "wait_time":       bb.wait_time,
        "global_reward":   orc.global_reward(),
        "units_sold":      dict(bb.units_sold),
        "units_wasted":    dict(bb.units_wasted),
        "escalations":     len(orc.human_escalations),
        "messages_logged": len(bus.log),
        "waste_value":     round(sum(bb.units_wasted[p] * bb.costs[p] for p in bb.units_wasted), 2),
        "staff_final":     bb.staff_count,
    }

    return snapshots, bus.log, summary


# ── HTML generation ──────────────────────────────────────────────────────────

def generate_html(snapshots, messages, summary):
    ts   = json.dumps(snapshots)
    msgs = json.dumps(messages)
    sm   = json.dumps(summary)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Retail Pop-Up · Event Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0f172a;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    padding: 28px;
    min-height: 100vh;
  }}

  /* ── header ── */
  .header {{ margin-bottom: 28px; }}
  .header h1 {{ font-size: 1.6rem; font-weight: 700; color: #f1f5f9; }}
  .header p  {{ font-size: 0.85rem; color: #94a3b8; margin-top: 4px; }}

  /* ── scenario legend ── */
  .legend {{
    display: flex; gap: 12px; flex-wrap: wrap;
    margin-bottom: 24px;
  }}
  .chip {{
    display: flex; align-items: center; gap: 6px;
    padding: 5px 12px; border-radius: 999px;
    font-size: 0.78rem; font-weight: 600;
    border: 1px solid rgba(255,255,255,0.1);
  }}
  .chip-dot {{ width: 8px; height: 8px; border-radius: 50%; }}

  /* ── KPI cards ── */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }}
  .kpi-card {{
    background: #1e293b;
    border-radius: 12px;
    padding: 20px;
    border: 1px solid #334155;
  }}
  .kpi-label {{ font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
  .kpi-value {{ font-size: 1.9rem; font-weight: 700; color: #f1f5f9; margin-top: 6px; }}
  .kpi-sub   {{ font-size: 0.75rem; color: #64748b; margin-top: 4px; }}
  .kpi-good  {{ color: #34d399; }}
  .kpi-warn  {{ color: #fbbf24; }}
  .kpi-bad   {{ color: #f87171; }}

  /* ── charts ── */
  .charts-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
    gap: 20px;
    margin-bottom: 28px;
  }}
  .chart-card {{
    background: #1e293b;
    border-radius: 12px;
    padding: 20px;
    border: 1px solid #334155;
  }}
  .chart-card h3 {{
    font-size: 0.85rem;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 16px;
  }}
  .chart-wrap {{ position: relative; height: 220px; }}

  /* ── summary table ── */
  .section {{ margin-bottom: 28px; }}
  .section h2 {{
    font-size: 0.85rem; font-weight: 600; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px;
  }}
  table {{
    width: 100%; border-collapse: collapse;
    background: #1e293b; border-radius: 12px; overflow: hidden;
    border: 1px solid #334155; font-size: 0.85rem;
  }}
  th {{
    background: #0f172a; color: #94a3b8;
    font-weight: 600; font-size: 0.75rem;
    text-transform: uppercase; letter-spacing: 0.05em;
    padding: 10px 16px; text-align: left;
  }}
  td {{ padding: 10px 16px; border-top: 1px solid #334155; color: #cbd5e1; }}
  tr:hover td {{ background: #273549; }}

  /* ── message log ── */
  .filter-bar {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }}
  .filter-btn {{
    padding: 4px 12px; border-radius: 6px; border: 1px solid #475569;
    background: transparent; color: #94a3b8; font-size: 0.75rem;
    cursor: pointer; transition: all 0.15s;
  }}
  .filter-btn:hover {{ border-color: #7c3aed; color: #c4b5fd; }}
  .filter-btn.active {{ background: #7c3aed; border-color: #7c3aed; color: #fff; }}

  .priority-normal   {{ color: #94a3b8; }}
  .priority-high     {{ color: #fbbf24; }}
  .priority-critical {{ color: #f87171; font-weight: 600; }}
  .msg-payload {{ font-family: monospace; font-size: 0.78rem; color: #7dd3fc; }}
  .scenario-badge {{
    font-size: 0.7rem; padding: 2px 8px; border-radius: 4px; font-weight: 600;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>Autonomous Retail Pop-Up — Event Dashboard</h1>
  <p>MGSC 697 · Assignment 3 · Multi-Agent System Simulation · Generated {generated_at}</p>
</div>

<!-- Scenario legend -->
<div class="legend">
  <div class="chip" style="background:rgba(59,130,246,0.15);border-color:#3b82f6">
    <div class="chip-dot" style="background:#3b82f6"></div> Normal Operation (t=0–44)
  </div>
  <div class="chip" style="background:rgba(245,158,11,0.15);border-color:#f59e0b">
    <div class="chip-dot" style="background:#f59e0b"></div> Demand Spike (t=45–89)
  </div>
  <div class="chip" style="background:rgba(239,68,68,0.15);border-color:#ef4444">
    <div class="chip-dot" style="background:#ef4444"></div> Stockout (t=90–149)
  </div>
  <div class="chip" style="background:rgba(16,185,129,0.15);border-color:#10b981">
    <div class="chip-dot" style="background:#10b981"></div> Clearance (t=150–179)
  </div>
</div>

<!-- KPI cards -->
<div class="kpi-grid" id="kpi-grid"></div>

<!-- Charts -->
<div class="charts-grid">
  <div class="chart-card">
    <h3>Cumulative Revenue ($)</h3>
    <div class="chart-wrap"><canvas id="chartRevenue"></canvas></div>
  </div>
  <div class="chart-card">
    <h3>Stock Levels (units)</h3>
    <div class="chart-wrap"><canvas id="chartStock"></canvas></div>
  </div>
  <div class="chart-card">
    <h3>Price Evolution ($)</h3>
    <div class="chart-wrap"><canvas id="chartPrices"></canvas></div>
  </div>
  <div class="chart-card">
    <h3>Satisfaction Score &amp; Wait Time</h3>
    <div class="chart-wrap"><canvas id="chartSat"></canvas></div>
  </div>
</div>

<!-- Units sold / wasted -->
<div class="section">
  <h2>Event Summary</h2>
  <table>
    <thead>
      <tr>
        <th>Product</th>
        <th>Units Sold</th>
        <th>Units Wasted</th>
        <th>Waste Cost</th>
      </tr>
    </thead>
    <tbody id="summary-body"></tbody>
  </table>
</div>

<!-- Message log -->
<div class="section">
  <h2>Agent Message Log (<span id="msg-count"></span> messages)</h2>
  <div class="filter-bar" id="filter-bar"></div>
  <table>
    <thead>
      <tr><th>Time</th><th>Type</th><th>From</th><th>Priority</th><th>Scenario</th><th>Payload</th></tr>
    </thead>
    <tbody id="msg-body"></tbody>
  </table>
</div>

<script>
const snapshots = {ts};
const messages  = {msgs};
const summary   = {sm};

// ── scenario color lookup ──────────────────────────────────────────────────
const SCEN_COLOR = {{
  "Normal Operation": "#3b82f6",
  "Demand Spike":     "#f59e0b",
  "Stockout":         "#ef4444",
  "Clearance":        "#10b981",
}};
const SCEN_BG = {{
  "Normal Operation": "rgba(59,130,246,0.12)",
  "Demand Spike":     "rgba(245,158,11,0.12)",
  "Stockout":         "rgba(239,68,68,0.12)",
  "Clearance":        "rgba(16,185,129,0.12)",
}};

function scenarioFor(t) {{
  if (t < 45)  return "Normal Operation";
  if (t < 90)  return "Demand Spike";
  if (t < 150) return "Stockout";
  return "Clearance";
}}

// ── KPI cards ──────────────────────────────────────────────────────────────
const kpis = [
  {{ label: "Total Revenue",  value: "$" + summary.revenue.toLocaleString(), sub: "3-hour event", cls: "kpi-good" }},
  {{ label: "Gross Margin",   value: summary.gross_margin + "%",
     sub: summary.gross_margin >= 35 ? "✓ above 35% floor" : "✗ below floor",
     cls: summary.gross_margin >= 35 ? "kpi-good" : "kpi-bad" }},
  {{ label: "Satisfaction",   value: summary.satisfaction + " / 5",
     sub: summary.satisfaction >= 4.0 ? "✓ above 4.0 floor" : "✗ below floor",
     cls: summary.satisfaction >= 4.0 ? "kpi-good" : "kpi-warn" }},
  {{ label: "Global Reward",  value: summary.global_reward, sub: "revenue × sat / cost", cls: "" }},
  {{ label: "Human Alerts",   value: summary.escalations, sub: "escalations triggered", cls: summary.escalations > 0 ? "kpi-warn" : "" }},
  {{ label: "Waste Value",    value: "$" + summary.waste_value, sub: "end-of-event stock cost", cls: summary.waste_value > 0 ? "kpi-warn" : "kpi-good" }},
  {{ label: "Messages",       value: summary.messages_logged, sub: "on the event bus", cls: "" }},
  {{ label: "Final Wait",     value: summary.wait_time + " min",
     sub: summary.wait_time <= 4 ? "✓ within 4 min SLA" : "✗ above SLA",
     cls: summary.wait_time <= 4 ? "kpi-good" : "kpi-bad" }},
];

const grid = document.getElementById("kpi-grid");
kpis.forEach(k => {{
  grid.innerHTML += `
    <div class="kpi-card">
      <div class="kpi-label">${{k.label}}</div>
      <div class="kpi-value ${{k.cls}}">${{k.value}}</div>
      <div class="kpi-sub">${{k.sub}}</div>
    </div>`;
}});

// ── chart defaults ─────────────────────────────────────────────────────────
Chart.defaults.color = "#64748b";
Chart.defaults.borderColor = "#1e293b";

const labels = snapshots.map(s => s.t);

// vertical scenario dividers plugin
const dividerPlugin = {{
  id: "dividers",
  afterDraw(chart) {{
    const ctx = chart.ctx;
    const xAxis = chart.scales.x;
    const yAxis = chart.scales.y || chart.scales.y1 || Object.values(chart.scales)[1];
    if (!xAxis || !yAxis) return;
    [45, 90, 150].forEach(t => {{
      const x = xAxis.getPixelForValue(t);
      if (!x) return;
      ctx.save();
      ctx.strokeStyle = "rgba(148,163,184,0.25)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(x, yAxis.top);
      ctx.lineTo(x, yAxis.bottom);
      ctx.stroke();
      ctx.restore();
    }});
  }}
}};

const baseOptions = {{
  responsive: true,
  maintainAspectRatio: false,
  plugins: {{
    legend: {{ labels: {{ color: "#94a3b8", boxWidth: 12, font: {{ size: 11 }} }} }},
    tooltip: {{
      backgroundColor: "#0f172a",
      borderColor: "#334155",
      borderWidth: 1,
      titleColor: "#f1f5f9",
      bodyColor: "#94a3b8",
      callbacks: {{
        title: items => "t = " + items[0].label + " min (" + scenarioFor(+items[0].label) + ")"
      }}
    }}
  }},
  scales: {{
    x: {{
      grid: {{ color: "rgba(51,65,85,0.6)" }},
      ticks: {{ maxTicksLimit: 10, color: "#475569" }}
    }},
    y: {{
      grid: {{ color: "rgba(51,65,85,0.6)" }},
      ticks: {{ color: "#475569" }}
    }}
  }}
}};

// ── Revenue chart ──────────────────────────────────────────────────────────
new Chart(document.getElementById("chartRevenue"), {{
  type: "line",
  plugins: [dividerPlugin],
  data: {{
    labels,
    datasets: [{{
      label: "Revenue ($)",
      data: snapshots.map(s => s.revenue),
      borderColor: "#7c3aed",
      backgroundColor: "rgba(124,58,237,0.1)",
      fill: true,
      tension: 0.3,
      pointRadius: 0,
      borderWidth: 2,
    }}]
  }},
  options: {{ ...baseOptions }}
}});

// ── Stock chart ────────────────────────────────────────────────────────────
new Chart(document.getElementById("chartStock"), {{
  type: "line",
  plugins: [dividerPlugin],
  data: {{
    labels,
    datasets: [
      {{ label: "Beverages", data: snapshots.map(s => s.bev),    borderColor: "#3b82f6", pointRadius: 0, tension: 0.3, borderWidth: 2 }},
      {{ label: "Snacks",    data: snapshots.map(s => s.snacks), borderColor: "#f59e0b", pointRadius: 0, tension: 0.3, borderWidth: 2 }},
      {{ label: "Merchandise", data: snapshots.map(s => s.merch),borderColor: "#10b981", pointRadius: 0, tension: 0.3, borderWidth: 2 }},
    ]
  }},
  options: {{ ...baseOptions }}
}});

// ── Price chart ────────────────────────────────────────────────────────────
new Chart(document.getElementById("chartPrices"), {{
  type: "line",
  plugins: [dividerPlugin],
  data: {{
    labels,
    datasets: [
      {{ label: "Beverages ($)", data: snapshots.map(s => s.price_bev),    borderColor: "#3b82f6", pointRadius: 0, tension: 0.2, borderWidth: 2 }},
      {{ label: "Snacks ($)",    data: snapshots.map(s => s.price_snacks), borderColor: "#f59e0b", pointRadius: 0, tension: 0.2, borderWidth: 2 }},
      {{ label: "Merchandise ($)", data: snapshots.map(s => s.price_merch),borderColor: "#10b981", pointRadius: 0, tension: 0.2, borderWidth: 2 }},
    ]
  }},
  options: {{ ...baseOptions }}
}});

// ── Satisfaction + Wait time (dual axis) ───────────────────────────────────
new Chart(document.getElementById("chartSat"), {{
  type: "line",
  plugins: [dividerPlugin],
  data: {{
    labels,
    datasets: [
      {{
        label: "Satisfaction (1–5)",
        data: snapshots.map(s => s.satisfaction),
        borderColor: "#34d399", pointRadius: 0, tension: 0.3, borderWidth: 2,
        yAxisID: "y",
      }},
      {{
        label: "Wait time (min)",
        data: snapshots.map(s => s.wait_time),
        borderColor: "#f87171", pointRadius: 0, tension: 0.3, borderWidth: 2,
        borderDash: [5, 3],
        yAxisID: "y1",
      }},
    ]
  }},
  options: {{
    ...baseOptions,
    scales: {{
      x: baseOptions.scales.x,
      y:  {{ ...baseOptions.scales.y, min: 0, max: 5.5, position: "left",  title: {{ display: true, text: "Satisfaction", color: "#34d399", font: {{ size: 10 }} }} }},
      y1: {{ ...baseOptions.scales.y, min: 0, max: 10,  position: "right", grid: {{ drawOnChartArea: false }}, title: {{ display: true, text: "Wait (min)", color: "#f87171", font: {{ size: 10 }} }} }},
    }}
  }}
}});

// ── Summary table ──────────────────────────────────────────────────────────
const costs = {{ beverages: 3, snacks: 2, merchandise: 15 }};
const tbody = document.getElementById("summary-body");
["beverages", "snacks", "merchandise"].forEach(p => {{
  const wv = (summary.units_wasted[p] * costs[p]).toFixed(2);
  tbody.innerHTML += `
    <tr>
      <td style="text-transform:capitalize">${{p}}</td>
      <td>${{summary.units_sold[p]}}</td>
      <td>${{summary.units_wasted[p]}}</td>
      <td>${{wv}}</td>
    </tr>`;
}});

// ── Message log ────────────────────────────────────────────────────────────
document.getElementById("msg-count").textContent = messages.length;

const allTypes = [...new Set(messages.map(m => m.type))];
let activeFilter = "ALL";

const filterBar = document.getElementById("filter-bar");
["ALL", ...allTypes].forEach(type => {{
  const btn = document.createElement("button");
  btn.className = "filter-btn" + (type === "ALL" ? " active" : "");
  btn.textContent = type;
  btn.onclick = () => {{
    activeFilter = type;
    document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderMessages();
  }};
  filterBar.appendChild(btn);
}});

function renderMessages() {{
  const filtered = activeFilter === "ALL" ? messages : messages.filter(m => m.type === activeFilter);
  const mb = document.getElementById("msg-body");
  mb.innerHTML = filtered.map(m => {{
    const scen = scenarioFor(m.t);
    const color = SCEN_COLOR[scen];
    return `<tr>
      <td>t=${{m.t}}m</td>
      <td><strong>${{m.type}}</strong></td>
      <td>${{m.from}}</td>
      <td class="priority-${{m.priority}}">${{m.priority}}</td>
      <td><span class="scenario-badge" style="background:${{SCEN_BG[scen]}};color:${{color}}">${{scen}}</span></td>
      <td class="msg-payload">${{JSON.stringify(m.payload)}}</td>
    </tr>`;
  }}).join("");
}}
renderMessages();
</script>
</body>
</html>"""


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Running simulation (silent)...")
    with contextlib.redirect_stdout(io.StringIO()):
        snapshots, messages, summary = run_silent()
    print(f"  {len(snapshots)} snapshots  |  {len(messages)} messages captured")

    html = generate_html(snapshots, messages, summary)

    out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dashboard.html"
    )
    with open(out, "w") as f:
        f.write(html)

    print(f"\nDashboard saved → {out}")
    print("Open dashboard.html in your browser.")


if __name__ == "__main__":
    main()
