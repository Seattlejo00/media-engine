"""
Cost tracker.
Tracks API token usage across the pipeline and estimates cost per episode.
Writes a cost_report.json alongside each episode.

Pricing is approximate and updated manually — check provider dashboards
for exact billing. This gives you a ballpark so nothing surprises you.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Approximate pricing per 1M tokens (as of early 2026 — update as needed)
# ---------------------------------------------------------------------------
PRICING = {
    # provider: {model_pattern: (input_$/1M, output_$/1M)}
    "claude-sonnet-4": (3.00, 15.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "grok-3": (3.00, 15.00),
    "grok-3-mini": (0.30, 0.50),
    # TTS — charged per character, but we'll track per 1M chars
    "tts-1": (15.00, 0),  # ~$15 per 1M chars (OpenAI TTS)
    "tts-1-hd": (30.00, 0),
}


def _match_price(model: str) -> tuple[float, float]:
    """Find the best pricing match for a model string."""
    for pattern, prices in PRICING.items():
        if pattern in model:
            return prices
    return (0.0, 0.0)


class CostTracker:
    """Thread-safe singleton that accumulates usage across pipeline steps."""

    def __init__(self):
        self._lock = Lock()
        self._records: list[dict] = []
        self._tts_chars = 0
        self._start_time = datetime.now()

    def record(
        self,
        step: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        speaker: str = "",
    ):
        """Record a single API call."""
        with self._lock:
            self._records.append({
                "step": step,
                "model": model,
                "speaker": speaker,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "timestamp": datetime.now().isoformat(),
            })

    def record_tts(self, characters: int):
        """Record TTS character usage (OpenAI TTS bills per character)."""
        with self._lock:
            self._tts_chars += characters

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost for a single call in USD."""
        input_rate, output_rate = _match_price(model)
        return (input_tokens * input_rate / 1_000_000) + (output_tokens * output_rate / 1_000_000)

    def get_summary(self) -> dict:
        """Compute a full cost summary."""
        with self._lock:
            total_input = 0
            total_output = 0
            total_cost = 0.0
            by_step: dict[str, float] = {}
            by_model: dict[str, dict] = {}
            by_speaker: dict[str, dict] = {}

            for r in self._records:
                inp, out = r["input_tokens"], r["output_tokens"]
                cost = self._estimate_cost(r["model"], inp, out)

                total_input += inp
                total_output += out
                total_cost += cost

                # By step
                by_step[r["step"]] = by_step.get(r["step"], 0.0) + cost

                # By model
                if r["model"] not in by_model:
                    by_model[r["model"]] = {"input_tokens": 0, "output_tokens": 0, "cost": 0.0, "calls": 0}
                by_model[r["model"]]["input_tokens"] += inp
                by_model[r["model"]]["output_tokens"] += out
                by_model[r["model"]]["cost"] += cost
                by_model[r["model"]]["calls"] += 1

                # By speaker
                if r["speaker"]:
                    if r["speaker"] not in by_speaker:
                        by_speaker[r["speaker"]] = {"input_tokens": 0, "output_tokens": 0, "cost": 0.0, "calls": 0}
                    by_speaker[r["speaker"]]["input_tokens"] += inp
                    by_speaker[r["speaker"]]["output_tokens"] += out
                    by_speaker[r["speaker"]]["cost"] += cost
                    by_speaker[r["speaker"]]["calls"] += 1

            # TTS cost
            tts_cost = self._tts_chars * 15.00 / 1_000_000  # ~$15/1M chars for tts-1
            total_cost += tts_cost

            elapsed = (datetime.now() - self._start_time).total_seconds()

            return {
                "total_cost_usd": round(total_cost, 4),
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "total_tokens": total_input + total_output,
                "tts_characters": self._tts_chars,
                "tts_cost_usd": round(tts_cost, 4),
                "api_calls": len(self._records),
                "elapsed_seconds": round(elapsed, 1),
                "by_step": {k: round(v, 4) for k, v in by_step.items()},
                "by_model": {
                    k: {**v, "cost": round(v["cost"], 4)}
                    for k, v in by_model.items()
                },
                "by_speaker": {
                    k: {**v, "cost": round(v["cost"], 4)}
                    for k, v in by_speaker.items()
                },
                "timestamp": datetime.now().isoformat(),
            }

    def save_report(self, output_dir: Path):
        """Save the cost report as JSON."""
        summary = self.get_summary()
        report_path = output_dir / "cost_report.json"
        report_path.write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        logger.info(
            f"💰 Episode cost: ${summary['total_cost_usd']:.4f} "
            f"({summary['api_calls']} API calls, "
            f"{summary['total_tokens']:,} tokens, "
            f"{summary['tts_characters']:,} TTS chars)"
        )
        return summary


# Global instance — import and use from any pipeline module
tracker = CostTracker()
