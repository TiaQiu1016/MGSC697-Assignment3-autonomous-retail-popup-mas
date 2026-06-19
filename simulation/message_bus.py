import uuid
from collections import defaultdict
from typing import Callable, Dict, List

RESET  = "\033[0m"
YELLOW = "\033[93m"
RED    = "\033[91m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"

PRIORITY_COLOR = {"normal": RESET, "high": YELLOW, "critical": RED}


class Message:
    def __init__(self, agent_id: str, msg_type: str, payload: dict,
                 priority: str = "normal", deadline_ms: int = 5000):
        self.schema_version  = "v1"
        self.trace_id        = f"tr_{uuid.uuid4().hex[:6]}"
        self.message_id      = f"msg_{uuid.uuid4().hex[:6]}"
        self.agent_id        = agent_id
        self.msg_type        = msg_type
        self.priority        = priority
        self.deadline_ms     = deadline_ms
        self.idempotency_key = f"{msg_type}_{agent_id}"
        self.payload         = payload


class MessageBus:
    def __init__(self):
        self._subs: Dict[str, List[Callable]] = defaultdict(list)
        self.log: List[dict] = []
        self.current_t: int  = 0

    def subscribe(self, msg_type: str, handler: Callable):
        self._subs[msg_type].append(handler)

    def publish(self, msg: Message, t: int = None):
        if t is not None:
            self.current_t = t
        self.log.append({
            "t":        self.current_t,
            "from":     msg.agent_id,
            "type":     msg.msg_type,
            "priority": msg.priority,
            "payload":  msg.payload,
        })
        c = PRIORITY_COLOR.get(msg.priority, RESET)
        print(f"  {c}[t={self.current_t:3d}m][{msg.msg_type:<22}]{RESET} "
              f"{msg.agent_id:<22} → {msg.payload}")
        for handler in self._subs.get(msg.msg_type, []):
            handler(msg)
