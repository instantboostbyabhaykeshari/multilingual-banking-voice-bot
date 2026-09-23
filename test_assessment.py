"""Offline assessment examples; these tests do not consume Gemini API quota."""

import unittest

from nudge_engine import RealTimeNudgeEngine


class AssessmentExamples(unittest.TestCase):
    def test_missed_opportunity_example(self):
        engine = RealTimeNudgeEngine(cooldown_seconds=0)
        alerts = engine.accept_decision(
            "I am buying another vehicle for my family.", "customer",
            {"signal": "MISSED_CROSS_SELL", "confidence": 0.95},
        )
        self.assertEqual(alerts[0]["signal"], "MISSED_CROSS_SELL")

    def test_compliance_risk_example(self):
        engine = RealTimeNudgeEngine(cooldown_seconds=0)
        alerts = engine.accept_decision(
            "Approval is guaranteed with no documents.", "agent",
            {"signal": "COMPLIANCE_RISK", "confidence": 0.98},
        )
        self.assertEqual(alerts[0]["signal"], "COMPLIANCE_RISK")

    def test_low_value_statement_is_suppressed(self):
        engine = RealTimeNudgeEngine(cooldown_seconds=0)
        alerts = engine.accept_decision(
            "Hello, can you hear me?", "customer",
            {"signal": "MISSED_CROSS_SELL", "confidence": 0.50},
        )
        self.assertEqual(alerts, [])


if __name__ == "__main__":
    unittest.main()
