from simulation.message_bus import MessageBus, Message, GREEN, RESET

LOW_THRESHOLD = 15   # units — trigger LOW alert below this


class InventoryAgent:
    NAME = "inventory_agent"

    def __init__(self, bus: MessageBus, bb, orchestrator):
        self.bus      = bus
        self.bb       = bb
        self.orc      = orchestrator
        self._alerted = set()   # track which stockouts we've already alerted

    def tick(self, t: int):
        if t % 10 != 0:
            return
        self._check_stock(t)

    def _check_stock(self, t: int):
        for product, qty in list(self.bb.stock.items()):
            stockout_key = f"{product}_stockout"
            if qty <= 0 and stockout_key not in self._alerted:
                self._alerted.add(stockout_key)
                self.bus.publish(Message(
                    agent_id=self.NAME,
                    msg_type="INVENTORY_ALERT",
                    payload={"product": product, "stock": qty, "status": "STOCKOUT"},
                    priority="high",
                ), t)
                self._attempt_restock(product, 30, t)

            elif 0 < qty <= LOW_THRESHOLD:
                self.bus.publish(Message(
                    agent_id=self.NAME,
                    msg_type="INVENTORY_ALERT",
                    payload={"product": product, "stock": qty, "status": "LOW"},
                    priority="high",
                ), t)

    def _attempt_restock(self, product: str, units: int, t: int):
        order_cost = self.bb.costs[product] * units
        if self.orc.validate_order(order_cost, product):
            self.bb.stock[product]     += units
            self.bb.total_restock_cost += order_cost
            print(f"  {GREEN}[INVENTORY] Auto-restocked {units}x {product} "
                  f"(${order_cost:.0f}){RESET}")

    def initiate_clearance(self, t: int):
        """Publish MARKDOWN_BID for all products with remaining stock."""
        minutes_left = self.bb.event_duration - t
        discount     = self._discount_for(minutes_left)
        self.bb.clearance_active = True
        for product, qty in self.bb.stock.items():
            if qty > 0:
                self.bus.publish(Message(
                    agent_id=self.NAME,
                    msg_type="MARKDOWN_BID",
                    payload={
                        "product":            product,
                        "stock_remaining":    qty,
                        "minutes_to_close":   minutes_left,
                        "suggested_discount": discount,
                    },
                    priority="high",
                ), t)

    def record_waste(self):
        for product, qty in self.bb.stock.items():
            self.bb.units_wasted[product] = max(0, qty)

    @staticmethod
    def _discount_for(minutes_left: int) -> float:
        """Real-world retail clearance curve."""
        if minutes_left > 60: return 0.10
        if minutes_left > 30: return 0.25
        if minutes_left > 10: return 0.40
        return 0.60
