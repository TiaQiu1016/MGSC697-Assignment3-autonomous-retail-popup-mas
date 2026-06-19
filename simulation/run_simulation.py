import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulation.message_bus import MessageBus, RESET, GREEN, CYAN, BOLD, RED, YELLOW
from simulation.shared_state import Blackboard
from simulation.orchestrator import Orchestrator
from agents.demand_agent import DemandAgent
from agents.inventory_agent import InventoryAgent
from agents.pricing_agent import PricingAgent
from agents.labor_agent import LaborAgent
from agents.cx_agent import CXAgent

DIVIDER = "─" * 68
THICK   = "═" * 68


def print_header(orc: Orchestrator):
    print(f"\n{THICK}")
    print(f"  AUTONOMOUS RETAIL POP-UP SIMULATION  —  3-HOUR EVENT")
    print(f"  MGSC 697 · Multi-Agent Systems · Assignment 3")
    print(THICK)
    print(f"\n  {BOLD}Global KPIs set by Orchestrator:{RESET}")
    for k, v in orc.KPIs.items():
        print(f"    • {k:<25} {v}")
    print()


def print_scenario(num: int, title: str, desc: str = ""):
    print(f"\n{DIVIDER}")
    print(f"  {BOLD}SCENARIO {num}: {title}{RESET}")
    if desc:
        print(f"  {CYAN}{desc}{RESET}")
    print(DIVIDER)


def print_snapshot(bb: Blackboard, t: int):
    """Brief state snapshot printed at scenario boundaries."""
    print(f"\n  {CYAN}── State snapshot at t={t}min ──────────────────────────{RESET}")
    print(f"    Stock:       " +
          " | ".join(f"{p}: {q}" for p, q in bb.stock.items()))
    print(f"    Prices:      " +
          " | ".join(f"{p}: ${v:.2f}" for p, v in bb.prices.items()))
    print(f"    Satisfaction: {bb.satisfaction_score:.2f}/5.0  "
          f"| Wait: {bb.wait_time:.1f}min  "
          f"| Staff: {bb.staff_count}  "
          f"| Revenue: ${bb.total_revenue:.2f}")
    print()


def print_dashboard(bb: Blackboard, orc: Orchestrator, bus: MessageBus):
    total_cost   = bb.total_labor_cost + bb.total_restock_cost
    gross_margin = ((bb.total_revenue - total_cost) / bb.total_revenue * 100
                    if bb.total_revenue else 0)
    waste_value  = sum(bb.units_wasted[p] * bb.costs[p] for p in bb.units_wasted)

    print(f"\n{THICK}")
    print(f"  {BOLD}FINAL EVENT DASHBOARD{RESET}")
    print(THICK)
    print(f"  {'Revenue:':<28} ${bb.total_revenue:>8.2f}")
    print(f"  {'Labor cost:':<28} ${bb.total_labor_cost:>8.2f}")
    print(f"  {'Restock cost:':<28} ${bb.total_restock_cost:>8.2f}")
    print(f"  {'Total cost:':<28} ${total_cost:>8.2f}")
    print(f"  {'Gross margin:':<28} {gross_margin:>7.1f}%  "
          f"{'✓ above 35% floor' if gross_margin >= 35 else '✗ below floor'}")
    print(DIVIDER)
    print(f"  {'Satisfaction score:':<28} {bb.satisfaction_score:.2f} / 5.0  "
          f"{'✓' if bb.satisfaction_score >= 4.0 else '✗ below 4.0 floor'}")
    print(f"  {'Final wait time:':<28} {bb.wait_time:.1f} min  "
          f"{'✓' if bb.wait_time <= 4.0 else '✗ above 4min SLA'}")
    print(f"  {'Staff on shift:':<28} {bb.staff_count}")
    print(DIVIDER)
    print(f"  {BOLD}{'Global reward:':<28} {orc.global_reward():>8.2f}{RESET}")
    print(f"  (formula: total_revenue × satisfaction / total_cost)")
    print(DIVIDER)
    print(f"  Units sold:")
    for p, qty in bb.units_sold.items():
        print(f"    {p:<18} {qty:>4} units  "
              f"(${qty * bb.prices[p]:.2f} at final price)")
    print(f"  Units wasted (end-of-event stock):")
    for p, qty in bb.units_wasted.items():
        print(f"    {p:<18} {qty:>4} units  (${qty * bb.costs[p]:.2f} cost)")
    print(f"  Waste value lost:         ${waste_value:.2f}")
    print(DIVIDER)
    print(f"  Human escalations:        {len(orc.human_escalations)}")
    print(f"  Total messages logged:    {len(bus.log)}")
    print(THICK)


def run():
    bb  = Blackboard()
    bus = MessageBus()
    orc = Orchestrator(bus, bb)

    demand    = DemandAgent(bus, bb)
    inventory = InventoryAgent(bus, bb, orc)
    pricing   = PricingAgent(bus, bb)
    labor     = LaborAgent(bus, bb)
    cx        = CXAgent(bus, bb)
    agents    = [demand, inventory, pricing, labor, cx]

    print_header(orc)

    # ── SCENARIO 1: Normal Operation ─────────────────────────────────────────
    print_scenario(1, "Normal Operation",
                   "t=0 → t=44  |  All five agents coordinating at steady-state")

    for t in range(0, 45):
        orc.accrue_labor()
        for agent in agents:
            agent.tick(t)

    print_snapshot(bb, 44)

    # ── SCENARIO 2: Demand Spike ─────────────────────────────────────────────
    print_scenario(2, "Demand Spike — Beverages +150%",
                   "t=45  |  Demand agent detects surge → Pricing raises price, "
                   "Labor requests more staff")

    demand.apply_spike("beverages", 2.5)   # 8 → 20 units per 5 min
    for t in range(45, 90):
        orc.accrue_labor()
        for agent in agents:
            agent.tick(t)

    print_snapshot(bb, 89)

    # ── SCENARIO 3: Best-Seller Stockout ─────────────────────────────────────
    print_scenario(3, "Best-Seller Stockout — Beverages",
                   "t=90  |  Inventory alerts → CX satisfaction drops → "
                   "Pricing promotes substitute (snacks)")

    bb.stock["beverages"] = 0   # force stockout for scenario demo
    bb.demand_rate["beverages"] = 8   # spike has passed — back to normal rate
    bb.foot_traffic = 50
    for t in range(90, 150):
        orc.accrue_labor()
        for agent in agents:
            agent.tick(t)

    print_snapshot(bb, 149)

    # ── SCENARIO 4: End-of-Event Clearance ───────────────────────────────────
    print_scenario(4, "End-of-Event Clearance — Markdown Auction",
                   "t=150 → t=180  |  Inventory ↔ Pricing negotiate markdown depth; "
                   "two auction waves (30min and 15min before close)")

    for t in range(150, 180):
        orc.accrue_labor()
        if t == 150:
            inventory.initiate_clearance(t)   # 30 min left → 25% off
        if t == 165:
            inventory.initiate_clearance(t)   # 15 min left → 40% off
        for agent in agents:
            agent.tick(t)

    # ── Final dashboard ───────────────────────────────────────────────────────
    inventory.record_waste()
    print_dashboard(bb, orc, bus)


if __name__ == "__main__":
    run()
