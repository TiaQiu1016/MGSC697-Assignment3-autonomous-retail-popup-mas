from simulation.message_bus import MessageBus, Message

SAT_FLOOR     = 4.0
SAT_ESCALATE  = 3.5
MAX_ESCALATIONS = 3   # cap to avoid spam


class CXAgent:
    NAME = "cx_agent"

    def __init__(self, bus: MessageBus, bb):
        self.bus          = bus
        self.bb           = bb
        self._escalations = 0
        self._last_alert  = -10   # prevent duplicate alerts each tick
        bus.subscribe("INVENTORY_ALERT", self._on_inventory_alert)

    def tick(self, t: int):
        if t % 5 != 0:
            return
        self._monitor(t)

    def _monitor(self, t: int):
        sat  = self.bb.satisfaction_score
        wait = self.bb.wait_time

        if sat < SAT_ESCALATE and self._escalations < MAX_ESCALATIONS \
                and t - self._last_alert >= 10:
            self._escalations  += 1
            self._last_alert    = t
            self.bus.publish(Message(
                agent_id=self.NAME,
                msg_type="ESCALATE_HUMAN",
                payload={
                    "reason":        f"Satisfaction {sat:.1f} below {SAT_ESCALATE} floor",
                    "satisfaction":  sat,
                    "wait_time_min": wait,
                },
                priority="critical",
            ), t)

        elif sat < SAT_FLOOR and t - self._last_alert >= 10:
            self._last_alert = t
            self.bus.publish(Message(
                agent_id=self.NAME,
                msg_type="CX_ALERT",
                payload={
                    "satisfaction":  sat,
                    "wait_time_min": wait,
                    "action":        "Notifying labor agent",
                },
                priority="high",
            ), t)

    def _on_inventory_alert(self, msg: Message):
        """Stockouts hurt satisfaction directly."""
        if msg.payload.get("status") == "STOCKOUT":
            self.bb.satisfaction_score = round(
                max(1.0, self.bb.satisfaction_score - 0.15), 2
            )
