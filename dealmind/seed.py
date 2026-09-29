"""Load the synthetic historical deals into Hindsight.

Run from the project root:  python -m dealmind.seed

Each deal is retained with document_id = deal id, so running this again
replaces the existing memories instead of duplicating them.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from dealmind.deals import (
    deal_metadata, deal_timestamp, deal_to_memory_text, load_deals,
)
from dealmind.memory import (
    ConfigError, ensure_bank, get_client, load_settings, recall_memories,
    retain_deal_memory,
)


@dataclass
class SeedReport:
    retained: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)  # deal id -> error

    @property
    def ok(self) -> bool:
        return not self.failed and bool(self.retained)


def seed_historical_deals(
    client,
    bank_id: str,
    deals: list[dict] | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> SeedReport:
    """Retain every historical deal in Hindsight. Failures are collected, not hidden."""
    deals = deals if deals is not None else load_deals()
    report = SeedReport()
    ensure_bank(client, bank_id)
    for n, deal in enumerate(deals, start=1):
        try:
            retain_deal_memory(
                client,
                bank_id,
                deal_to_memory_text(deal),
                context=f"historical sales deal ({deal['outcome']})",
                document_id=deal["id"],
                timestamp=deal_timestamp(deal),
                metadata=deal_metadata(deal),
            )
            report.retained.append(deal["id"])
        except Exception as exc:  # keep going; report every failure at the end
            report.failed[deal["id"]] = f"{type(exc).__name__}: {exc}"
        if on_progress:
            on_progress(n, len(deals), deal["customer"])
    return report


def wait_until_recallable(
    client, bank_id: str, deal: dict, timeout_s: int = 90, poll_every_s: int = 3
) -> bool:
    """Poll Hindsight until a seeded deal can be recalled (extraction is async)."""
    query = f"What happened in the {deal['customer']} deal?"
    start = time.time()
    while time.time() - start < timeout_s:
        memories = recall_memories(client, bank_id, query)
        if any(deal["customer"].lower() in m.text.lower() for m in memories):
            return True
        time.sleep(poll_every_s)
    return False


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as e:
        print(f"Config error: {e}")
        return 2
    client = get_client(settings)
    deals = load_deals()
    print(f"Seeding {len(deals)} deals into bank '{settings.bank_id}' ...")
    report = seed_historical_deals(
        client, settings.bank_id, deals,
        on_progress=lambda n, total, name: print(f"  [{n}/{total}] {name}"),
    )
    print(f"Retained: {len(report.retained)}  Failed: {len(report.failed)}")
    for deal_id, err in report.failed.items():
        print(f"  FAILED {deal_id}: {err}")
    if report.retained:
        print("Verifying the last deal is recallable (can take up to ~90s) ...")
        found = wait_until_recallable(client, settings.bank_id, deals[-1])
        print("Recall verified." if found else "Not recallable yet - Hindsight may still be processing.")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
