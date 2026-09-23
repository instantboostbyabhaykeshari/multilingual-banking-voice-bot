"""Nudge policy and timing controls for live LLM signal decisions."""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from statistics import quantiles


class RealTimeNudgeEngine:
    SIGNALS = {
        "MISSED_CROSS_SELL": ("medium", "Ask whether they want financing for the second asset; verify an available offer before quoting terms."),
        "RISING_FRUSTRATION": ("high", "Acknowledge the concern, slow down, and offer a human callback if requested."),
        "PAYMENT_DIFFICULTY": ("medium", "Acknowledge affordability concerns; check documented payment options or arrange a callback."),
        "COMPLIANCE_GAP": ("high", "Give the verified fees, rate, eligibility and terms disclosure before proceeding."),
        "COMPLIANCE_RISK": ("high", "Stop and correct the unsupported promise; explain actual eligibility and required documents."),
        "CALLBACK_REQUEST": ("medium", "Confirm a convenient callback window; do not claim it is booked without a scheduling workflow."),
    }
    CUSTOMER_SIGNALS = {"MISSED_CROSS_SELL", "RISING_FRUSTRATION", "PAYMENT_DIFFICULTY",
                        "COMPLIANCE_GAP", "CALLBACK_REQUEST"}

    def __init__(self, cooldown_seconds: float = 12.0, confidence_threshold: float = 0.78,
                 expiry_seconds: float = 45.0):
        self.cooldown_period = cooldown_seconds
        self.confidence_threshold = confidence_threshold
        self.expiry_seconds = expiry_seconds
        self.last_trigger_times = defaultdict(float)
        self._recent_fingerprints = {}
        self._latencies = defaultdict(lambda: deque(maxlen=2000))
        self.disclosure_seen = False

    @staticmethod
    def _is_usable(text: str) -> bool:
        text = (text or "").strip()
        words = re.findall(r"[\w']+", text, flags=re.UNICODE)
        alpha = sum(ch.isalpha() for ch in text)
        return len(text) >= 8 and len(words) >= 2 and alpha / len(text) >= 0.45

    def accept_decision(self, text: str, source: str, decision: dict) -> list[dict]:
        signal = str(decision.get("signal", "NONE"))
        try:
            confidence = float(decision.get("confidence", 0))
        except (TypeError, ValueError):
            return []
        if signal == "DISCLOSURE_GIVEN" and source == "agent" and confidence >= self.confidence_threshold:
            self.disclosure_seen = True
            return []
        if not self._is_usable(text) or signal not in self.SIGNALS:
            return []
        if signal == "COMPLIANCE_GAP" and self.disclosure_seen:
            return []
        if source == "agent" and signal != "COMPLIANCE_RISK":
            return []
        if source == "customer" and signal not in self.CUSTOMER_SIGNALS:
            return []
        if confidence < self.confidence_threshold:
            return []
        now = time.perf_counter()
        fingerprint = signal + ":" + re.sub(r"\W+", " ", text.lower()).strip()
        if now - self._recent_fingerprints.get(fingerprint, 0) < self.cooldown_period:
            return []
        if now - self.last_trigger_times[signal] < self.cooldown_period:
            return []
        self._recent_fingerprints[fingerprint] = now
        self.last_trigger_times[signal] = now
        priority, nudge = self.SIGNALS[signal]
        return [{"signal": signal, "nudge": nudge, "confidence": round(confidence, 2),
                 "priority": priority, "source": source,
                 "expires_in_seconds": self.expiry_seconds, "created_at": time.time()}]

    def record_latency(self, component: str, latency_ms: float) -> None:
        self._latencies[component].append(float(latency_ms))

    def latency_report(self) -> dict:
        report = {}
        for component, values in self._latencies.items():
            if not values:
                continue
            ordered = sorted(values)
            p95 = quantiles(ordered, n=20, method="inclusive")[18] if len(ordered) >= 2 else ordered[0]
            report[component] = {"count": len(ordered), "p50_ms": round(ordered[len(ordered) // 2], 2),
                                 "p95_ms": round(p95, 2)}
        return report
