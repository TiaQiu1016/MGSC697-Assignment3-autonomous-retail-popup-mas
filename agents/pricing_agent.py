from simulation.message_bus import MessageBus, Message, GREEN, RESET

MARGIN_FLOOR    = 0.35
MAX_SURGE       = 1.5   # prices cannot exceed 1.5× baseline during a spike
BASELINE_PRICES = {"beverages": 8.0, "snacks": 6.0, "merchandise": 40.0}
BASELINE_DEMAND = {"beverages": 8,   "snacks": 6,   "merchandise": 3}


class PricingAgent:
    NAME = "pricing_agent"

    def __init__(self, bus: MessageBus, bb):
        self.bus = bus
        self.bb  = bb
        bus.subscribe("DEMAND_FORECAST", self._on_demand)
        bus.subscribe("INVENTORY_ALERT", self._on_inventory_alert)
        bus.subscribe("MARKDOWN_BID",    self._on_markdown_bid)

    def tick(self, t: int):
        pass  # fully event-driven — reacts to bus messages

    def _on_demand(self, msg: Message):
        if self.bb.clearance_active:
            return  # clearance prices take priority over surge pricing
        forecast = msg.payload["forecast"]
        for product, rate in forecast.items():
            if self.bb.stock.get(product, 0) == 0:
                continue  # don't surge an out-of-stock item
            baseline_rate  = BASELINE_DEMAND.get(product, 1)
            baseline_price = BASELINE_PRICES[product]
            current_price  = self.bb.prices[product]
            if current_price >= baseline_price * MAX_SURGE:
                continue  # already at surge cap
            if rate > baseline_rate * 1.5:   # significant surge detected
                old = current_price
                new = round(min(old * 1.10, baseline_price * MAX_SURGE), 2)
                self._propose(product, old, new)

    def _on_inventory_alert(self, msg: Message):
        if msg.payload.get("status") != "STOCKOUT":
            return
        product = msg.payload["product"]
        subs    = {"beverages": "snacks", "snacks": "merchandise"}
        sub     = subs.get(product)
        if sub and self.bb.stock.get(sub, 0) > 0:
            old = self.bb.prices[sub]
            new = round(old * 1.08, 2)
            print(f"  {GREEN}[PRICING] Promoting {sub} as substitute "
                  f"for {product} stockout{RESET}")
            self._propose(sub, old, new)

    def _on_markdown_bid(self, msg: Message):
        product  = msg.payload["product"]
        discount = msg.payload["suggested_discount"]
        base     = BASELINE_PRICES[product]
        cost     = self.bb.costs[product]

        new = round(base * (1 - discount), 2)
        # enforce margin floor — cannot go below this
        min_price = round(cost / (1 - MARGIN_FLOOR), 2)
        new = max(new, min_price)

        old = self.bb.prices[product]
        self._propose(product, old, new)

    def _propose(self, product: str, old: float, new: float):
        if abs(new - old) < 0.01:
            return
        self.bus.publish(Message(
            agent_id=self.NAME,
            msg_type="PRICE_CHANGE",
            payload={"product": product, "old_price": old, "new_price": new},
        ), self.bus.current_t)
