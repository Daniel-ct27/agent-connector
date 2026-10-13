"""Shared extraction of structured findings from incident logs."""

from __future__ import annotations

from collections import Counter

from agent_connector.domain.models import EvidenceItem, LogEntry, LogLevel


_ERROR_LIKE = {LogLevel.ERROR, LogLevel.FATAL}


def extract_evidence(logs: list[LogEntry]) -> list[EvidenceItem]:
    """Group error-like logs by service and normalized message pattern.

    Every item represents exactly one ``(service, pattern)`` group. ``count``
    is the number of input entries in that group. Results are ranked by count,
    then service and pattern, so ordering is deterministic.
    """
    counts: Counter[tuple[str, str]] = Counter()
    samples: dict[tuple[str, str], str] = {}

    for entry in logs:
        if entry.level not in _ERROR_LIKE:
            continue
        pattern = normalize_message(entry.message)
        key = (entry.service, pattern)
        counts[key] += 1
        samples.setdefault(key, entry.message)

    ranked_groups = sorted(
        counts.items(),
        key=lambda item: (-item[1], item[0][0], item[0][1]),
    )
    return [
        EvidenceItem(
            service=service,
            summary=pattern,
            count=count,
            sample_message=samples[(service, pattern)],
        )
        for (service, pattern), count in ranked_groups
    ]


def normalize_message(message: str) -> str:
    """Remove known request and attempt suffixes before grouping messages."""
    text = message.lower().strip()
    for token in ("attempt", "request_id", "ord-", "req-"):
        if token in text:
            text = text.split(token)[0].rstrip(" :;-")
    return " ".join(text.split())
