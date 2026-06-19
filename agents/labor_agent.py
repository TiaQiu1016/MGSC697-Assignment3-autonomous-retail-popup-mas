from simulation.message_bus import MessageBus, Message

MAX_STAFF = 5
MIN_STAFF = 2
WAIT_SLA  = 4.0   # minutes


class LaborAgent:
    NAME = "labor_agent"

    def __init__(self, bus: MessageBus, bb):
        self.bus = bus
        self.bb  = bb
        bus.subscribe("DEMAND_FORECAST", self._on_demand)

    def tick(self, t: int):
        if t % 30 != 0:
            return
        self._review_staffing(t)

    def _on_demand(self, msg: Message):
        """React immediately if foot traffic surges."""
        traffic = msg.payload.get("foot_traffic", 0)
        if traffic > 70 and self.bb.staff_count < MAX_STAFF:
            self._request_staff(self.bb.staff_count + 1)

    def _review_staffing(self, t: int):
        """Periodic review — scale up or down based on wait time."""
        wait    = self.bb.wait_time
        current = self.bb.staff_count

        if wait > WAIT_SLA and current < MAX_STAFF:
            self._request_staff(min(current + 1, MAX_STAFF), t)
        elif wait < 2.0 and current > MIN_STAFF:
            self._request_staff(max(current - 1, MIN_STAFF), t)

    def _request_staff(self, count: int, t: int = None):
        if count == self.bb.staff_count:
            return
        self.bus.publish(Message(
            agent_id=self.NAME,
            msg_type="STAFF_REQUEST",
            payload={
                "requested_staff":   count,
                "current_wait_time": self.bb.wait_time,
                "reason": "wait_sla_breach" if self.bb.wait_time > WAIT_SLA
                          else "traffic_surge" if self.bb.foot_traffic > 70
                          else "optimization",
            },
        ), t or self.bus.current_t)
