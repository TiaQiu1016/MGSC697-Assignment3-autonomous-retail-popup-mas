# Autonomous Retail Pop-Up Multi-Agent System

> MGSC 697 — Assignment 3 | Designing & Building Agentic AI Systems

---

## Table of Contents

1. [System Brief](#1-system-brief)
2. [Agent Roster](#2-agent-roster)
3. [Architecture Diagram](#3-architecture-diagram)
4. [Communication Contract](#4-communication-contract)
5. [Coordination Mechanism](#5-coordination-mechanism)
6. [Incentive Analysis](#6-incentive-analysis)
7. [Prototype / Simulation](#7-prototype--simulation)
8. [Evaluation Plan](#8-evaluation-plan)
9. [Safety & Governance Plan](#9-safety--governance-plan)
10. [MARL Bridge](#10-marl-bridge)

---

## 1. System Brief

**Use case:** A time-limited retail pop-up store (3–8 hour event) that operates autonomously across demand forecasting, inventory management, dynamic pricing, labor scheduling, and customer experience — with a human manager as the final escalation layer.

**Stakeholders:**
- Pop-up organizer (revenue and brand outcomes)
- Shoppers (price fairness, experience quality)
- On-site staff (workload and scheduling)
- Suppliers (order fulfillment, lead times)

**Objective:** Maximize `(total_revenue × avg_satisfaction_score) / total_cost` within the pop-up window while maintaining a gross margin floor of 35% and a customer satisfaction floor of 4.0/5.0.

**Failure stakes:** Stockouts leave revenue on the table; overstocking wastes capital; bad dynamic pricing alienates customers and triggers social backlash; understaffing creates long queues; a runaway markdown cascade collapses margin.

---

## 2. Agent Roster

| Agent | Role | Tools | Memory | Permissions |
|---|---|---|---|---|
| **Demand Agent** | Forecast product demand every 5 min | Sales velocity API, foot traffic sensor, time-series model | Rolling 2-hr sales window | Read POS, read sensors |
| **Inventory Agent** | Track stock, trigger restocks/markdowns | POS system, inventory DB, supplier API | Current stock levels, reorder history | Read/write inventory, call supplier API |
| **Pricing Agent** | Dynamic pricing to maximize revenue | Competitor price API, POS write API | Price history, demand signals | Write prices to POS (within guardrails) |
| **Labor Agent** | Schedule staff to meet wait-time SLA | Staff scheduling app, task dispatch API | Shift roster, wait-time history | Read/write staff schedule |
| **CX Agent** | Monitor satisfaction scores, wait times, handle inquiries | Chatbot interface, queue monitor, satisfaction survey API | Interaction logs, complaint history | Read queue, send notifications, escalate |

---

## 3. Architecture Diagram

```mermaid
graph TD
    ORC[Orchestrator / Command Center\nSets KPIs · enforces guardrails · human gateway]

    DA[Demand Agent\nforecast every 5 min]
    IA[Inventory Agent\ntrack stock every 10 min]
    PA[Pricing Agent\ndynamic pricing every 5 min]
    LA[Labor Agent\nschedule every 30 min]
    CX[CX Agent\ncontinuous monitoring]

    BUS[(Pub-Sub Event Bus)]
    SM[(Shared Blackboard\ncurrent stock · prices · satisfaction score · foot traffic)]

    HUMAN[Human Manager Dashboard]

    POS[(POS System)]
    SUP[(Supplier API)]
    STAFF[(Staff Scheduling App)]

    ORC -- "global KPIs + guardrails" --> BUS
    DA -- "DEMAND_FORECAST" --> BUS
    IA -- "INVENTORY_ALERT" --> BUS
    PA -- "PRICE_CHANGE" --> BUS
    LA -- "STAFF_REQUEST" --> BUS
    CX -- "CX_ALERT" --> BUS

    BUS --> SM
    SM --> DA & IA & PA & LA & CX

    PA <-- "markdown auction" --> IA

    ORC --> HUMAN
    CX -- "ESCALATE_HUMAN" --> HUMAN

    IA --> SUP
    PA --> POS
    LA --> STAFF
```

---

## 4. Communication Contract

### Message Schema

Every message on the event bus follows this envelope:

```json
{
  "schema_version": "v1",
  "trace_id": "tr_abc123",
  "message_id": "msg_001",
  "agent_id": "demand_agent",
  "msg_type": "DEMAND_FORECAST",
  "priority": "normal",
  "deadline_ms": 5000,
  "idempotency_key": "forecast_14:30:00",
  "payload": {}
}
```

### Message Types

| Type | Sender | Subscribers | Priority |
|---|---|---|---|
| `DEMAND_FORECAST` | Demand Agent | Pricing, Inventory, Labor | normal |
| `INVENTORY_ALERT` | Inventory Agent | Pricing, Orchestrator | high |
| `PRICE_CHANGE` | Pricing Agent | Inventory, CX, Orchestrator | normal |
| `MARKDOWN_BID` | Inventory Agent | Pricing Agent | high |
| `STAFF_REQUEST` | Labor Agent | Orchestrator | normal |
| `CX_ALERT` | CX Agent | Labor, Orchestrator | high |
| `ESCALATE_HUMAN` | CX Agent / Orchestrator | Human Manager | critical |

### Escalation Rules

- Any `priority: critical` message bypasses the bus and goes directly to the human dashboard
- Pricing changes > 25% require orchestrator approval before hitting POS
- Inventory orders above $300 require human confirmation

---

## 5. Coordination Mechanism

**Choice: Hybrid Supervisor + Market**

### Why not pure supervisor?

A pure hierarchy creates a bottleneck for the pricing-inventory negotiation, which has natural market dynamics. The orchestrator cannot optimally set markdown depth — the agents with local information (inventory urgency, current demand) can.

### Why not pure market?

Unconstrained market mechanisms between agents with misaligned local objectives (e.g., pricing maximizes margin, inventory wants to clear stock) risk emergent collusion or race-to-bottom pricing without guardrails.

### The hybrid design

- **Orchestrator layer:** Sets global KPIs, enforces hard guardrails (35% margin floor, 4.0/5.0 satisfaction floor), owns the human escalation path
- **Market layer (Pricing ↔ Inventory):** When stock is high and closing time approaches, Inventory Agent signals clearance urgency with a `MARKDOWN_BID`. Pricing Agent responds with a markdown offer. The market clears at the discount rate that satisfies both the margin floor and the clearance goal
- **Pub-sub for all other coordination:** Demand forecasts, CX alerts, and staff requests are broadcast events — any agent that needs them subscribes

---

## 6. Incentive Analysis

### Local and Global Objectives

| Agent | Local Reward | Global Penalty |
|---|---|---|
| Demand | Minimize forecast MAPE | −3× if MAPE > 15% |
| Inventory | Minimize end-of-event waste | −5× if stockout occurs |
| Pricing | Maximize revenue per transaction | −10× if satisfaction drops below 4.0 |
| Labor | Minimize labor cost | −5× if wait time > 4 min |
| CX | Maximize avg satisfaction score | −5× if escalation rate > 10% |

**Global reward (shared):** `(total_revenue × avg_satisfaction_score) / total_cost`

> **Note on satisfaction score:** We use a 1–5 in-event satisfaction rating (collected via post-transaction survey) rather than traditional NPS (−100 to +100 scale), which requires a follow-up window incompatible with a same-day pop-up.

### Markdown Timing (Pricing Agent Policy)

As closing time approaches, the pricing agent follows a real-world clearance curve:

| Time before close | Markdown depth |
|---|---|
| 2 hours | 10–15% off |
| 1 hour | 20–30% off |
| 30 min | 30–50% off |
| Final 10 min | 50–70% off (cost recovery only) |

### Risks

| Risk | Mitigation |
|---|---|
| Pricing-inventory death spiral | Margin floor guardrail hardcoded at 35% |
| Labor cutting staff to save cost while CX degrades | Wait-time SLA penalty (> 4 min) outweighs labor savings |
| Demand agent over-forecasting to trigger restocks | MAPE penalty on forecast accuracy |
| Free-rider (agent taking global reward without contributing) | Per-agent Shapley value attribution at event close |

---

## 7. Prototype / Simulation

### How to run

```bash
pip install -r requirements.txt
python simulation/run_simulation.py
```

### What the simulation demonstrates

A 3-hour pop-up event with four scripted scenarios:

| Time | Scenario | Agents Involved |
|---|---|---|
| t = 0–60 min | Normal operation | All agents coordinating |
| t = 45 min | Demand spike (beverages +150%) | Demand → Pricing, Labor |
| t = 90 min | Best-seller stockout | Inventory → Pricing (substitute promotion) |
| t = 150 min | End-of-event clearance | Inventory ↔ Pricing markdown auction |

The simulation prints all message exchanges to console and outputs a final event dashboard.

---

## 8. Evaluation Plan

### Agent-level metrics

| Agent | Metric | Target |
|---|---|---|
| Demand | MAPE | < 15% |
| Inventory | Stockout rate | < 5% of SKUs |
| Pricing | Revenue per transaction | > baseline +10% |
| Labor | Wait time | < 4 min average |
| CX | Avg satisfaction score | ≥ 4.0 / 5.0 |

### Interaction-level metrics

- Message delivery latency (p95 < deadline_ms)
- Auction clearance time for markdown bids (< 30 sec)
- Escalation rate to human (< 5% of events)

### System-level metrics

- Global reward: `(total_revenue × avg_satisfaction_score) / total_cost`
- Gini coefficient of reward distribution across agents (fairness)
- Shannon entropy of pricing actions (diversity of decisions)

### Human-level metrics

- Human override frequency
- Time-to-decision when escalated
- Manager satisfaction with dashboard clarity

---

## 9. Safety & Governance Plan

### Hard guardrails (cannot be overridden by agents)

- Pricing agent cannot set any price below cost (gross margin floor = 35%)
- Pricing agent cannot exceed 3× MSRP
- Inventory orders above $300 require human approval
- Any price change > 25% triggers orchestrator review

### Human-in-the-loop triggers

| Condition | Action |
|---|---|
| Satisfaction score drops below 3.5 | CX agent escalates to manager dashboard |
| Inventory order > $300 | Paused pending human confirmation |
| Price change > 25% | Flagged for orchestrator approval |
| Agent message queue backs up > 50 | Orchestrator alerts manager |

### Audit log

Every agent action is written to an immutable event log with:
`timestamp · agent_id · action_type · payload · outcome · trace_id`

### Rollback

- Pricing rollback: any price change can be reverted to previous value via manager dashboard within 60 seconds
- Staffing rollback: labor agent decisions are soft suggestions until confirmed by on-site staff lead
- Simulation-first policy: all coordination logic is validated in simulation before any production pop-up

### Failure / abuse cases

| Failure | Response |
|---|---|
| Pricing agent oscillation (price war with itself) | Circuit breaker after 3 reversals in 10 min |
| Demand agent stale data (sensor offline) | Fall back to last known forecast + alert |
| Inventory agent supplier API timeout | Hold current stock levels, alert manager |
| CX agent chatbot mishandling sensitive complaint | Immediate escalation to human staff |

---

## 10. MARL Bridge

**Is multi-agent RL appropriate here?**

Partially yes — but premature for a first deployment.

The pricing agent's decision problem maps cleanly to an MDP:
- **State:** current demand, inventory levels, time remaining, competitor prices
- **Action:** set price (continuous or discretized)
- **Reward:** revenue × avg_satisfaction_score contribution

However, for a pop-up (short, one-time event):
- There is no time to train online during the event
- Safe exploration is impossible in a live retail environment
- Governance requires predictable, auditable pricing decisions — not a learned policy

**Recommended path:**
1. **Now:** Rule-based pricing agent with hand-tuned policies
2. **After 3–5 pop-ups:** Train a pricing policy via **offline RL** on logged event data
3. **At scale:** Use **CTDE** (Centralized Training, Decentralized Execution) — train all agents jointly with global state, deploy each agent with only its local observations

MARL is earned here, not assumed.
