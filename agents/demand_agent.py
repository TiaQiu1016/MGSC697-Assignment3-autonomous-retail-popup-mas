from simulation.message_bus import MessageBus, Message

BASELINE_DEMAND = {"beverages": 8, "snacks": 6, "merchandise": 3}


class DemandAgent:
    NAME = "demand_agent"

    def __init__(self, bus: MessageBus, bb):
        self.bus     = bus
        self.bb      = bb
        self._errors = []

    def tick(self, t: int):
        if t % 5 != 0:
            return
        self._process_sales()
        self._update_operations()
        self.bus.publish(Message(
            agent_id=self.NAME,
            msg_type="DEMAND_FORECAST",
            payload={
                "forecast":     dict(self.bb.demand_rate),
                "foot_traffic": self.bb.foot_traffic,
                "mape":         self._mape(),
            },
        ), t)

    def _process_sales(self):
        for product, rate in self.bb.demand_rate.items():
            available = self.bb.stock[product]
            sold      = min(rate, available)
            if sold > 0:
                self.bb.stock[product]      -= sold
                self.bb.units_sold[product] += sold
                self.bb.total_revenue       += sold * self.bb.prices[product]
                self._errors.append(abs(rate - sold) / max(sold, 1))

    def _update_operations(self):
        total_demand    = sum(self.bb.demand_rate.values())
        staff_capacity  = self.bb.staff_count * 4   # 4 customers/staff per 5 min
        self.bb.wait_time = round(
            max(1.0, 1.0 + (total_demand - staff_capacity) / max(staff_capacity, 1) * 3), 1
        )

        sat = 4.5
        if self.bb.wait_time > 4.0:
            sat -= 0.3
        if self.bb.wait_time > 7.0:
            sat -= 0.4
        for qty in self.bb.stock.values():
            if qty == 0:
                sat -= 0.2
        self.bb.satisfaction_score = round(max(1.0, min(5.0, sat)), 2)

    def apply_spike(self, product: str, multiplier: float):
        self.bb.demand_rate[product] = int(BASELINE_DEMAND[product] * multiplier)
        self.bb.foot_traffic = int(self.bb.foot_traffic * 1.4)

    def _mape(self) -> float:
        return round(sum(self._errors) / len(self._errors), 3) if self._errors else 0.0
