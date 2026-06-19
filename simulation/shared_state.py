class Blackboard:
    """Shared read surface for all agents. Agents read here; writes go through
    the bus so the orchestrator can enforce guardrails."""

    def __init__(self):
        # inventory
        self.stock  = {"beverages": 300, "snacks": 250, "merchandise": 150}
        self.costs  = {"beverages": 3.0, "snacks":  2.0, "merchandise": 15.0}
        self.prices = {"beverages": 8.0, "snacks":  6.0, "merchandise": 40.0}

        # demand (units sold per 5-min interval under normal conditions)
        self.demand_rate = {"beverages": 8, "snacks": 6, "merchandise": 3}

        # operations
        self.satisfaction_score = 4.5   # 1–5 in-event rating
        self.foot_traffic       = 50    # customers currently in store
        self.staff_count        = 3
        self.wait_time          = 2.0   # minutes

        # financials
        self.total_revenue      = 0.0
        self.total_labor_cost   = 0.0
        self.total_restock_cost = 0.0
        self.units_sold         = {"beverages": 0, "snacks": 0, "merchandise": 0}
        self.units_wasted       = {"beverages": 0, "snacks": 0, "merchandise": 0}

        # flags
        self.event_duration   = 180   # minutes (3 hours)
        self.clearance_active = False
