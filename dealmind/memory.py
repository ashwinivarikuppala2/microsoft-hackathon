"""Hindsight memory layer for DealMind.

All deal memory lives in Hindsight (retain / recall / reflect). There is no
local fallback store. This module only wraps the official `hindsight-client`.

Run the connection test from a terminal with:  python -m dealmind.memory
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime

from dotenv import load_dotenv
from hindsight_client import Hindsight

load_dotenv()

DEFAULT_BASE_URL = "https://api.hindsight.vectorize.io"
DEFAULT_BANK_ID = "dealmind"


class ConfigError(RuntimeError):
    """Raised when required environment variables are missing."""


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    bank_id: str
    llm_api_key: str  # not used yet; loaded so later steps can rely on it


def load_settings() -> Settings:
    """Read configuration from environment variables (never hardcoded)."""
    load_dotenv(override=False)
    api_key = os.getenv("HINDSIGHT_API_KEY", "").strip()
    base_url = os.getenv("HINDSIGHT_BASE_URL", DEFAULT_BASE_URL).strip()
    if not api_key and base_url.rstrip("/") == DEFAULT_BASE_URL:
        raise ConfigError(
            "HINDSIGHT_API_KEY is not set. Copy .env.example to .env and add your "
            "Hindsight Cloud API key."
        )
    return Settings(
        api_key=api_key,
        base_url=base_url,
        bank_id=os.getenv("HINDSIGHT_BANK_ID", DEFAULT_BANK_ID).strip() or DEFAULT_BANK_ID,
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
    )


def get_client(settings: Settings) -> Hindsight:
    kwargs = {"base_url": settings.base_url}
    if settings.api_key:
        kwargs["api_key"] = settings.api_key
    return Hindsight(**kwargs)


def ensure_bank(client: Hindsight, bank_id: str) -> str:
    """Create the memory bank if needed. Returns a short status string."""
    try:
        client.create_bank(bank_id=bank_id, name="DealMind")
        return f"Bank '{bank_id}' ready."
    except Exception as exc:  # bank may already exist, or be auto-created on retain
        return f"Bank '{bank_id}' create skipped ({type(exc).__name__}); continuing."


def retain_deal_memory(
    client: Hindsight,
    bank_id: str,
    content: str,
    context: str = "deal",
    *,
    document_id: str | None = None,
    timestamp: datetime | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    """Store one deal memory in Hindsight.

    Reusing the same `document_id` replaces the earlier version of that
    document, which makes re-seeding idempotent.
    """
    kwargs: dict = {"bank_id": bank_id, "content": content, "context": context}
    if document_id:
        kwargs["document_id"] = document_id
    if timestamp:
        kwargs["timestamp"] = timestamp
    if metadata:
        kwargs["metadata"] = metadata
    client.retain(**kwargs)


@dataclass(frozen=True)
class RecalledMemory:
    """One memory returned by Hindsight recall."""

    text: str
    type: str = ""
    context: str = ""
    document_id: str = ""
    metadata: dict = field(default_factory=dict)


def _get(item, name: str, default=None):
    """Read a field from an SDK object or a plain dict."""
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def recall_memories(client: Hindsight, bank_id: str, query: str) -> list[RecalledMemory]:
    """Recall from Hindsight and keep the fields needed to trace evidence."""
    result = client.recall(bank_id=bank_id, query=query)
    items = _get(result, "results", result) or []
    memories = []
    for item in items:
        memories.append(
            RecalledMemory(
                text=_get(item, "text", None) or str(item),
                type=str(_get(item, "type", "") or ""),
                context=str(_get(item, "context", "") or ""),
                document_id=str(_get(item, "document_id", "") or ""),
                metadata=dict(_get(item, "metadata", None) or {}),
            )
        )
    return memories


def recall_deal_memory(client: Hindsight, bank_id: str, query: str) -> list[str]:
    """Recall memories from Hindsight; returns the memory texts."""
    return [m.text for m in recall_memories(client, bank_id, query)]


TEST_MEMORY = (
    "SYNTHETIC TEST DEAL: Northwind Traders, a mid-market logistics company, was "
    "quoted 120 seats of the Enterprise plan at a 12% discount. The champion is "
    "Priya Nair (VP Operations). The deal stalled in procurement because the "
    "competitor FreightIQ offered a lower price."
)
TEST_QUERY = "What happened with the Northwind Traders deal?"


def run_connection_test(timeout_s: int = 60, poll_every_s: int = 3) -> dict:
    """Retain one synthetic deal memory, then poll recall until it shows up.

    Hindsight extracts facts with an LLM after retain, so the memory can take a
    few seconds to become searchable - hence the polling.
    """
    settings = load_settings()
    client = get_client(settings)
    report = {"bank_id": settings.bank_id, "base_url": settings.base_url, "steps": []}
    try:
        report["steps"].append(ensure_bank(client, settings.bank_id))

        retain_deal_memory(client, settings.bank_id, TEST_MEMORY, context="synthetic test deal")
        report["steps"].append("Retained 1 synthetic deal memory.")

        start = time.time()
        recalled: list[str] = []
        while time.time() - start < timeout_s:
            recalled = recall_deal_memory(client, settings.bank_id, TEST_QUERY)
            if any("northwind" in text.lower() for text in recalled):
                break
            time.sleep(poll_every_s)

        report["seconds_to_recall"] = round(time.time() - start, 1)
        report["recalled"] = recalled
        report["success"] = any("northwind" in t.lower() for t in recalled)
        report["steps"].append(
            "Recall found the test memory." if report["success"]
            else f"Recall did not return the test memory within {timeout_s}s."
        )
        return report
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


# --- Stage 4 Memory Facade & Local Fallback Store ----------------------------

import json
import uuid
from pathlib import Path
from dealmind.engine import Deal, similarity

_STOP_WORDS = set("a an the and or of to for with in on at is are was be we i it this that how should".split())


@dataclass
class Memory:
    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    relevance: float = 0.0
    source: str = "local"


def _tokens(s: str) -> set[str]:
    import re
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in _STOP_WORDS and len(t) > 2}


def _relevance(query: str, deal: Deal, text: str, metadata: dict) -> float:
    attr, _ = similarity(deal.profile(), {k: metadata.get(k, "") for k in deal.profile()})
    q = _tokens(f"{query} {deal.profile_text()}")
    m = _tokens(text)
    overlap = len(q & m) / max(1, min(len(q), len(m)))
    return round(min(1.0, 0.7 * attr + 0.3 * overlap), 3)


class LocalStore:
    name = "Local demo store"

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def reset(self, seed) -> None:
        self.path.write_text("[]", encoding="utf-8")
        for text, md, doc_id in seed:
            self.retain(text, md, doc_id)

    def retain(self, text: str, metadata: dict, document_id: str) -> str:
        rows = [r for r in self._load() if r.get("metadata", {}).get("deal_id") != document_id]
        mem_id = f"mem-{uuid.uuid4().hex[:6]}"
        rows.append({"id": mem_id, "text": text, "metadata": metadata, "created_at": time.time()})
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        return mem_id

    def recall(self, query: str, deal: Deal, limit: int) -> list[Memory]:
        return [Memory(r["id"], r["text"], r["metadata"], 0.0, "local") for r in self._load()][:limit * 4]


class HindsightStore:
    name = "Hindsight"

    def __init__(self, base_url: str, api_key: str | None):
        self.client = Hindsight(base_url=base_url, api_key=api_key or None, timeout=60.0, max_attempts=1)
        self.bank_id = self._new_bank()

    @staticmethod
    def _new_bank() -> str:
        return os.environ.get("HINDSIGHT_BANK_ID", "dealmind").strip() or "dealmind"

    def reset(self, seed) -> None:
        self.bank_id = self._new_bank()
        for text, md, doc_id in seed:
            self.retain(text, md, doc_id)

    def retain(self, text: str, metadata: dict, document_id: str) -> str:
        self.client.retain(
            bank_id=self.bank_id,
            content=text,
            context="sales deal outcome",
            metadata=metadata,
            document_id=document_id,
            tags=["dealmind", f"outcome:{metadata.get('outcome', '').lower()}"],
        )
        return document_id

    def recall(self, query: str, deal: Deal, limit: int) -> list[Memory]:
        resp = self.client.recall(
            bank_id=self.bank_id,
            query=f"{query} ({deal.profile_text()})",
            max_tokens=4096,
            budget="low",
        )
        out = []
        for r in getattr(resp, "results", []) or []:
            md = {k: str(v) for k, v in getattr(r, "metadata", {}).items()} if getattr(r, "metadata", None) else {}
            out.append(Memory(getattr(r, "id", str(uuid.uuid4())[:6]), getattr(r, "text", ""), md, 0.0, "hindsight"))
        return out

    def close(self) -> None:
        close = getattr(self.client, "close", None)
        if callable(close):
            close()


class MemoryFacade:
    """Unified memory interface with transparent fallback to LocalStore."""

    def __init__(self):
        self.notice = ""
        data_dir = Path(os.environ.get("DEALMIND_DATA_DIR", Path(__file__).resolve().parent / "data"))
        self.local = LocalStore(data_dir / "memory.json")
        self.store = self.local
        url = os.environ.get("HINDSIGHT_BASE_URL", "").strip()
        api_key = os.environ.get("HINDSIGHT_API_KEY", "").strip()
        if url:
            try:
                self.store = HindsightStore(url, api_key)
            except Exception as e:
                self.notice = f"Hindsight unavailable ({type(e).__name__}); using local store."

    @property
    def backend(self) -> str:
        return self.store.name

    def _call(self, method: str, *args):
        try:
            return getattr(self.store, method)(*args)
        except Exception as e:
            if self.store is self.local:
                raise
            self.notice = f"Hindsight call failed ({type(e).__name__}: {e}); switched to local store."
            self.store = self.local
            return getattr(self.local, method)(*args)

    def reset(self, seed) -> None:
        self._call("reset", seed)

    def retain(self, text: str, metadata: dict, document_id: str) -> str:
        return self._call("retain", text, metadata, document_id)

    def recall(self, query: str, deal: Deal, limit: int = 8) -> list[Memory]:
        res = self._call("recall", query, deal, limit)
        for m in res:
            m.relevance = _relevance(query, deal, m.text, m.metadata)
        res.sort(key=lambda m: -m.relevance)
        return res[:limit]



if __name__ == "__main__":
    try:
        out = run_connection_test()
    except ConfigError as e:
        raise SystemExit(f"Config error: {e}")
    for s in out["steps"]:
        print("-", s)
    print("Recalled memories:")
    for t in out.get("recalled", []):
        print("  *", t)
    print("SUCCESS" if out.get("success") else "FAILED")
