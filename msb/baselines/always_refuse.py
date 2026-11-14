class AlwaysRefuseBaseline:
    """Calibration baseline: refuse every question."""
    name = "always_refuse"

    def answer(self, task_view: dict) -> dict:
        return {"behavior": "refuse", "refuse_reason_cat": "always", "sql": None, "value": None}
