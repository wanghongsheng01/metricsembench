class AlwaysClarifyBaseline:
    """Calibration baseline: ask a generic clarification every time."""
    name = "always_clarify"

    def answer(self, task_view: dict) -> dict:
        return {
            "behavior": "clarify",
            "clarify_axes": ["unspecified"],
            "sql": None,
            "value": None,
        }
