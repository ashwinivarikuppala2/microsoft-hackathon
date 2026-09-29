"""TEST-ONLY helpers. Nothing in the app imports this module.

FakeHindsight imitates the parts of the Hindsight client that DealMind uses
(retain / recall / create_bank) so the code paths can be exercised without a
network. It uses crude keyword overlap; it says nothing about how good real
Hindsight's semantic recall is.
"""

import re
import sys
import types
from types import SimpleNamespace

STOP = set("the a an of to and in for is was were with that this what which their from are at on as by be it".split())


def install_hindsight_stub_if_missing() -> None:
    """dealmind.memory imports hindsight_client at module load; stub it if not installed."""
    try:
        import hindsight_client  # noqa: F401
    except ImportError:
        mod = types.ModuleType("hindsight_client")
        mod.Hindsight = FakeHindsight
        sys.modules["hindsight_client"] = mod


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP}


class FakeHindsight:
    def __init__(self, **kwargs):
        self.docs: dict[str, dict] = {}   # document_id -> retained payload
        self.calls = {"retain": 0, "recall": 0}
        self.fail_on: set[str] = set()    # document ids that should raise on retain
        self._anon = 0

    def create_bank(self, bank_id, name=None, **kw):
        return None

    def retain(self, bank_id, content, context=None, document_id=None, timestamp=None, metadata=None, **kw):
        self.calls["retain"] += 1
        if document_id in self.fail_on:
            raise RuntimeError("simulated retain failure")
        if document_id is None:
            self._anon += 1
            document_id = f"anon-{self._anon}"
        self.docs[document_id] = {
            "content": content, "context": context, "metadata": metadata or {}, "timestamp": timestamp,
        }

    def recall(self, bank_id, query, **kw):
        self.calls["recall"] += 1
        q = _tokens(query)
        scored = []
        for doc_id, doc in self.docs.items():
            for fact in re.split(r"(?<=[.!?])\s+", doc["content"]):
                score = len(q & _tokens(fact))
                if score >= 3:
                    scored.append((score, SimpleNamespace(
                        text=fact, type="world", context=doc["context"],
                        document_id=doc_id, metadata=doc["metadata"],
                    )))
        scored.sort(key=lambda t: -t[0])
        return SimpleNamespace(results=[m for _, m in scored[:15]])
