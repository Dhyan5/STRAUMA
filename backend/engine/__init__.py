"""Scoring, escalation and victim-facing projection.

Sub-modules:
    behavioral       response latency / re-contact / self-report -> behavioural score
    svi              Stress Vulnerability Index + Critical Override
    recommendations  deterministic (category, flags) -> action rules engine
    ingest           orchestration: interaction -> analyses -> SVI -> queue
    victim_copy      complainant-safe projection of internal state
"""

__all__ = ["behavioral", "svi", "recommendations", "ingest", "victim_copy"]
