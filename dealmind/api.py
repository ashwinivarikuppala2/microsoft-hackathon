"""JSON API for the React DealMind interface."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dealmind.chat import chat_with_memory
from dealmind.deals import deal_index, load_deals, option_values
from dealmind.engine import OUTCOMES, TACTICS, analyze, experience_metadata, experience_text, make_lesson
from dealmind.intelligence import run_deal_intelligence
from dealmind.memory import (
    ConfigError,
    MemoryFacade,
    get_client,
    load_settings,
    run_connection_test,
)
from dealmind.outcomes import DealOutcome, save_deal_outcome, verify_learning_loop
from dealmind.retrieval import CurrentDeal, STAGES
from dealmind.scenarios import DEAL_A, DEAL_B, QUESTION, SEED_MEMORIES
from dealmind.seed import seed_historical_deals

app = FastAPI(title="DealMind API", version="1.0.0")
WEB_DIST = Path(__file__).resolve().parents[1] / "web-dist"

DEAL_RECORDS = load_deals()
DEAL_INDEX = deal_index(DEAL_RECORDS)
CURRENT_DEAL = CurrentDeal(
    customer="Acme Freight Systems",
    industry="Logistics",
    product="Enterprise Platform",
    value=150000,
    stage="Negotiation",
    competitor="FreightIQ",
    objection="FreightIQ is quoting 20% lower for their cloud license.",
    stakeholder_concern="VP of Operations is concerned about go-live disruption during peak shipping.",
    pricing_discussion="Procurement requested an immediate 15% discount to match FreightIQ.",
)

DEMO_MEMORY = MemoryFacade()
DEMO_MEMORY.reset(SEED_MEMORIES)
DEMO_SCENES = {1: DEAL_A, 2: DEAL_B}
DEMO_RESULTS: dict[int, dict[str, Any]] = {}
DEMO_SAVED: dict[int, dict[str, Any]] = {}


class DealPayload(BaseModel):
    customer: str = ""
    industry: str = ""
    product: str = ""
    value: float = 0
    stage: str = ""
    competitor: str = ""
    objection: str = ""
    stakeholder_concern: str = ""
    pricing_discussion: str = ""


class OutcomePayload(DealPayload):
    id: str
    approach: str = ""
    outcome: str
    outcome_reason: str = ""
    date: str = ""


class DemoAskPayload(BaseModel):
    scene: int = Field(ge=1, le=2)
    query: str = QUESTION


class DemoOutcomePayload(BaseModel):
    scene: int = Field(ge=1, le=2)
    tactic: str
    outcome: str
    note: str = ""
    query: str = QUESTION


class LearningLoopPayload(BaseModel):
    recorded_outcome: OutcomePayload
    future_deal: DealPayload


class ChatPayload(BaseModel):
    message: str
    current_deal: DealPayload | None = None


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


@lru_cache(maxsize=1)
def _settings_and_client():
    settings = load_settings()
    return settings, get_client(settings)


def _configuration():
    try:
        return _settings_and_client()
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _deal(payload: DealPayload) -> CurrentDeal:
    return CurrentDeal(**payload.model_dump())


def _outcome(payload: OutcomePayload) -> DealOutcome:
    return DealOutcome(**payload.model_dump())


def _remember_record(record: dict[str, Any]) -> None:
    DEAL_INDEX[record["id"]] = record
    for position, current in enumerate(DEAL_RECORDS):
        if current["id"] == record["id"]:
            DEAL_RECORDS[position] = record
            break
    else:
        DEAL_RECORDS.append(record)


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    config = {"available": False, "message": "", "bank_id": "dealmind", "base_url": ""}
    try:
        settings = load_settings()
        config.update(
            available=True,
            bank_id=settings.bank_id,
            base_url=settings.base_url,
        )
    except ConfigError as exc:
        config["message"] = str(exc)
    return {
        "config": config,
        "demo": {
            "backend": DEMO_MEMORY.backend,
            "notice": DEMO_MEMORY.notice,
            "saved": _plain(DEMO_SAVED),
            "results": _plain(DEMO_RESULTS),
        },
        "current_deal": _plain(CURRENT_DEAL),
        "deals_count": len(DEAL_RECORDS),
        "industries": option_values(DEAL_RECORDS, "industry"),
        "products": option_values(DEAL_RECORDS, "product"),
        "stages": STAGES,
        "tactics": TACTICS,
        "outcomes": OUTCOMES,
        "scenes": {
            str(number): _plain(scene)
            for number, scene in DEMO_SCENES.items()
        },
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/presets/{preset_id}")
def get_preset(preset_id: int) -> dict[str, Any]:
    presets = {
        1: CurrentDeal(
            customer="Acme Freight Systems", industry="Logistics", product="Enterprise Platform",
            value=150000, stage="Negotiation", competitor="FreightIQ",
            objection="FreightIQ is quoting 20% lower for their cloud license.",
            stakeholder_concern="VP of Operations is concerned about go-live disruption during peak shipping.",
            pricing_discussion="Procurement requested an immediate 15% discount to match FreightIQ.",
        ),
        2: CurrentDeal(
            customer="Ascension Health Alliance", industry="Healthcare", product="Enterprise Platform",
            value=230000, stage="Security Review", competitor="Corvex",
            objection="No evidence of HIPAA compliance and audit readiness available.",
            stakeholder_concern="CISO is worried about patient record exposure during the migration.",
            pricing_discussion="Fixed quote presented; no discount requested yet pending CISO approval.",
        ),
        3: CurrentDeal(
            customer="Heritage Credit Union", industry="Financial Services", product="Analytics Add-on",
            value=85000, stage="Proposal", competitor="Optima Cloud",
            objection="Implementation looks too complex and Optima claims a 30-day go-live.",
            stakeholder_concern="Branch operations manager fears staff change fatigue with no internal data team.",
            pricing_discussion="Buyer asked for 15% discount to offset expected onboarding difficulty.",
        ),
    }
    if preset_id not in presets:
        raise HTTPException(status_code=404, detail="Unknown deal preset.")
    global CURRENT_DEAL
    CURRENT_DEAL = presets[preset_id]
    return _plain(CURRENT_DEAL)


@app.post("/api/historical/load")
def load_historical() -> dict[str, Any]:
    settings, client = _configuration()
    try:
        report = seed_historical_deals(client, settings.bank_id, DEAL_RECORDS)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Historical deal load failed: {exc}") from exc
    return {"ok": report.ok, "retained": report.retained, "failed": report.failed}


@app.post("/api/hindsight/test")
def hindsight_test() -> dict[str, Any]:
    try:
        return _plain(run_connection_test())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc


@app.post("/api/analysis")
def analyze_current_deal(payload: DealPayload) -> dict[str, Any]:
    settings, client = _configuration()
    deal = _deal(payload)
    errors = deal.validate()
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    global CURRENT_DEAL
    CURRENT_DEAL = deal
    try:
        return _plain(run_deal_intelligence(client, settings.bank_id, deal, DEAL_INDEX))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Hindsight recall failed: {type(exc).__name__}: {exc}") from exc


@app.post("/api/outcomes")
def record_outcome(payload: OutcomePayload) -> dict[str, Any]:
    settings, client = _configuration()
    try:
        outcome = _outcome(payload)
        result = save_deal_outcome(client, settings.bank_id, outcome, index=DEAL_INDEX)
        _remember_record(result["record"])
        return _plain(result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to save outcome: {type(exc).__name__}: {exc}") from exc


@app.post("/api/learning-loop")
def run_learning_loop(payload: LearningLoopPayload) -> dict[str, Any]:
    settings, client = _configuration()
    try:
        outcome = _outcome(payload.recorded_outcome)
        future_deal = _deal(payload.future_deal)
        errors = future_deal.validate()
        if errors:
            raise HTTPException(status_code=422, detail=errors)
        result = verify_learning_loop(client, settings.bank_id, outcome, future_deal, index=DEAL_INDEX)
        _remember_record(outcome.to_deal_dict())
        return _plain(result)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Learning loop failed: {type(exc).__name__}: {exc}") from exc


@app.post("/api/chat")
def chat(payload: ChatPayload) -> dict[str, Any]:
    settings, client = _configuration()
    try:
        deal = _deal(payload.current_deal) if payload.current_deal else CURRENT_DEAL
        response = chat_with_memory(
            client, settings.bank_id, payload.message, deal, DEAL_INDEX, settings.llm_api_key
        )
        return _plain(response)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Chat failed: {type(exc).__name__}: {exc}") from exc


@app.post("/api/demo/reset")
def reset_demo() -> dict[str, Any]:
    DEMO_MEMORY.reset(SEED_MEMORIES)
    DEMO_RESULTS.clear()
    DEMO_SAVED.clear()
    return {"backend": DEMO_MEMORY.backend, "notice": DEMO_MEMORY.notice}


@app.post("/api/demo/ask")
def ask_demo(payload: DemoAskPayload) -> dict[str, Any]:
    scene = DEMO_SCENES[payload.scene]
    memories = DEMO_MEMORY.recall(payload.query, scene)
    analysis = analyze(scene, memories)
    DEMO_RESULTS[payload.scene] = {"query": payload.query, "memories": memories, "analysis": analysis}
    compare = None
    if payload.scene == 2 and 1 in DEMO_SAVED:
        compare = analyze(scene, memories, exclude_deal_ids={DEAL_A.deal_id})
    return {
        "query": payload.query,
        "memories": _plain(memories),
        "analysis": _plain(analysis),
        "without_new_memory": _plain(compare),
    }


@app.post("/api/demo/outcome")
def save_demo_outcome(payload: DemoOutcomePayload) -> dict[str, Any]:
    if payload.scene not in DEMO_RESULTS:
        raise HTTPException(status_code=400, detail="Ask DealMind about this scene before recording its outcome.")
    if payload.tactic not in TACTICS:
        raise HTTPException(status_code=422, detail="Choose a valid tactic.")
    if payload.outcome not in OUTCOMES:
        raise HTTPException(status_code=422, detail="Choose Won, Lost, or Stalled.")

    scene = DEMO_SCENES[payload.scene]
    result = DEMO_RESULTS[payload.scene]
    analysis_before = result["analysis"]
    before_stat = next(row for row in analysis_before.tactic_stats if row["key"] == payload.tactic)
    lesson = make_lesson(scene, payload.tactic, payload.outcome, payload.note)
    DEMO_MEMORY.retain(
        experience_text(scene, payload.tactic, payload.outcome, lesson),
        experience_metadata(scene, payload.tactic, payload.outcome, lesson),
        scene.deal_id,
    )
    refreshed_memories = DEMO_MEMORY.recall(result["query"], scene)
    analysis_after = analyze(scene, refreshed_memories)
    after_stat = next(row for row in analysis_after.tactic_stats if row["key"] == payload.tactic)
    saved = {
        "tactic": payload.tactic,
        "outcome": payload.outcome,
        "lesson": lesson,
        "score_before": before_stat["score"],
        "score_after": after_stat["score"],
        "rec_before": analysis_before.recommendation,
        "rec_after": analysis_after.recommendation,
    }
    DEMO_SAVED[payload.scene] = saved
    DEMO_RESULTS[payload.scene] = {
        "query": result["query"], "memories": refreshed_memories, "analysis": analysis_after
    }
    return _plain(saved)


@app.on_event("shutdown")
def close_clients() -> None:
    clients = [getattr(DEMO_MEMORY.store, "client", None)]
    if _settings_and_client.cache_info().currsize:
        clients.append(_settings_and_client()[1])
    for client in clients:
        close = getattr(client, "close", None)
        if callable(close):
            close()


if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

if (WEB_DIST / "index.html").is_file():
    @app.get("/{path:path}", include_in_schema=False)
    def serve_react_app(path: str) -> FileResponse:
        requested = (WEB_DIST / path).resolve()
        if requested.is_relative_to(WEB_DIST) and requested.is_file():
            return FileResponse(requested)
        return FileResponse(WEB_DIST / "index.html")
