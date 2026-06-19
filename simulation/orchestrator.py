from simulation.message_bus import MessageBus, Message, RED, GREEN, YELLOW, RESET, BOLD

MARGIN_FLOOR  = 0.35    # 35% gross margin floor
SAT_FLOOR     = 4.0     # satisfaction score floor
WAIT_SLA      = 4.0     # minutes
ORDER_CAP     = 300.0   # $ — above this needs human approval
PRICE_CHG_CAP = 0.25    # 25% change triggers a flag
STAFF_HOURLY  = 18.0    # $/hr per staff member


class Orchestrator:
    KPIs = {
        "margin_floor":       f"{MARGIN_FLOOR:.0%}",
        "satisfaction_floor": f"{SAT_FLOOR} / 5.0",
        "wait_time_sla":      f"{WAIT_SLA} min",
        "order_cap":          f"${ORDER_CAP:.0f}",
        "price_change_flag":  f">{PRICE_CHG_CAP:.0%}",
    }

    def __init__(self, bus: MessageBus, bb):
        self.bus = bus
        self.bb  = bb
        self.human_escalations: list = []

        bus.subscribe("PRICE_CHANGE",   self._on_price_change)
        bus.subscribe("STAFF_REQUEST",  self._on_staff_request)
        bus.subscribe("ESCALATE_HUMAN", self._on_escalation)

    # ── guardrail handlers ───────────────────────────────────────────────────

    def _on_price_change(self, msg: Message):
        product   = msg.payload["product"]
        new_price = msg.payload["new_price"]
        old_price = msg.payload["old_price"]
        cost      = self.bb.costs[product]
        margin    = (new_price - cost) / new_price if new_price > 0 else 0

        if margin < MARGIN_FLOOR:
            print(f"  {RED}[GUARDRAIL] BLOCKED {product} → ${new_price:.2f} "
                  f"(margin {margin:.0%} < {MARGIN_FLOOR:.0%} floor){RESET}")
            return  # price NOT applied

        pct = abs(new_price - old_price) / old_price if old_price else 0
        if pct > PRICE_CHG_CAP:
            print(f"  {YELLOW}[GUARDRAIL] Flagged {pct:.0%} change on "
                  f"{product} — within margin floor, auto-approved{RESET}")

        self.bb.prices[product] = new_price
        print(f"  {GREEN}[ORCHESTRATOR] Price applied: "
              f"{product} ${old_price:.2f} → ${new_price:.2f}{RESET}")

    def _on_staff_request(self, msg: Message):
        count = msg.payload["requested_staff"]
        self.bb.staff_count = count
        print(f"  {GREEN}[ORCHESTRATOR] Staffing approved: "
              f"{count} members on shift{RESET}")

    def _on_escalation(self, msg: Message):
        self.human_escalations.append(msg.payload)
        print(f"  {RED}{BOLD}[HUMAN ALERT] ⚠  Manager notified: "
              f"{msg.payload.get('reason', '')}{RESET}")

    # ── order validation (called directly by inventory agent) ────────────────

    def validate_order(self, amount: float, product: str) -> bool:
        if amount > ORDER_CAP:
            print(f"  {RED}[GUARDRAIL] Order ${amount:.0f} for {product} "
                  f"exceeds ${ORDER_CAP:.0f} cap — paused for human approval{RESET}")
            self.human_escalations.append(
                {"reason": f"Restock ${amount:.0f} for {product} needs approval"}
            )
            return False
        return True

    # ── labor cost accrual ───────────────────────────────────────────────────

    def accrue_labor(self, minutes: int = 1):
        self.bb.total_labor_cost += self.bb.staff_count * STAFF_HOURLY * (minutes / 60)

    # ── global reward ────────────────────────────────────────────────────────

    def global_reward(self) -> float:
        total_cost = self.bb.total_labor_cost + self.bb.total_restock_cost
        if total_cost == 0:
            return 0.0
        return round(
            (self.bb.total_revenue * self.bb.satisfaction_score) / total_cost, 2
        )
