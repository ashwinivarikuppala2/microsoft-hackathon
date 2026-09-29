# DealMind

**Hindsight-powered deal intelligence and adaptive learning loop.**

Enter a live deal, and DealMind recalls relevant past deal memories from Hindsight, identifies objection and competitor patterns, analyzes deal risk, and generates evidence-based recommendations citing historical precedent. When the deal closes, record its **WON / LOST / STALLED** outcome to save it into Hindsight memory, immediately educating future deal evaluations.

```mermaid
flowchart LR
    CD[Current Deal] --> RM[Recall Hindsight Memories]
    RM --> SD[Find Similar Deals]
    SD --> IP[Identify Patterns]
    IP --> RA[Recommend Action]
    RA --> RO[Record Outcome: Won/Lost/Stalled]
    RO --> SH[Save Outcome to Hindsight]
    SH --> FD[Use for Future Deals]
```

## Features

- **Centralized Hindsight Memory**: All historical intelligence, buyer objections, competitor tactics, and closing outcomes are stored in Hindsight memory (`retain`, `recall`).
- **Objection Pattern Detection**: Discovers recurring objection patterns (e.g. price discounting vs. ROI, compliance/security, change fatigue) and measures win rates across cohorts.
- **Competitor Pattern Detection**: Unpacks competitor playbooks (e.g. FreightIQ undercutting, Optima Cloud go-live claims) and reveals our proven counter-strategies.
- **Deal-Risk Analysis**: Evaluates deal vulnerability (`LOW`, `MEDIUM`, `HIGH`) and surfaces critical risk factors (e.g., commodity discounting trap, late-stage governance bottleneck) with specific historical deal citations.
- **Evidence-Based Recommendations**: Generates tactical actions strictly grounded in recalled memories:
  - 🎯 **Primary Strategy**: Recommended move citing winning historical deals.
  - ⚠️ **Pitfall to Avoid**: Critical warning citing past losses.
  - 🤝 **Stakeholder Alignment**: Targeted proof to resolve specific stakeholder fears.
  - 💰 **Pricing & Negotiation Tactic**: Value-preserving commercial structures.
- **WON / LOST / STALLED Outcome Recording**: Records completed deal outcomes and saves them into Hindsight with document IDs and structured fact prose.
- **Demonstrable Learning Loop**: Validates that newly saved outcomes are immediately recallable by future deals and influence future recommendations.
- **Natural-Language Chat**: Conversational deal advisor that answers questions grounded strictly in Hindsight memories with transparent deal citations.

## Setup
```bash
python -m pip install -r requirements.txt
cp .env.example .env        # add HINDSIGHT_API_KEY
npm install
```

## Run
```bash
npm run dev                 # starts the React UI and Python API together
```

Open `http://localhost:5173`. The React app uses the existing Python deal logic
through FastAPI on port `8000`. Historical deals can be loaded from the app's
sidebar, or seeded from the project directory with `python -m dealmind.seed`.
On Windows PowerShell, use `npm.cmd` in place of `npm` if script execution is
restricted.

The original Streamlit interface remains available with `streamlit run app.py`
from this project directory; it is retained for compatibility and the existing
smoke tests.

## Code Layout
- `dealmind/memory.py`: Hindsight wrapper (`retain`, `recall`, `ensure_bank`, connection test)
- `dealmind/deals.py`: Deals dataset loading, schema validation, prose memory formatting
- `dealmind/retrieval.py`: Deal query generation, Hindsight recall, evidence grouping
- `dealmind/intelligence.py`: Objection & competitor pattern detection, deal risk, evidence-based recommendations
- `dealmind/outcomes.py`: Outcome recording (`Won`/`Lost`/`Stalled`), Hindsight retention, learning loop verification
- `dealmind/chat.py`: Grounded natural-language chat backed by Hindsight memory recall
- `dealmind/api.py`: FastAPI endpoints for the React UI, reusing existing domain services
- `frontend/`: React/Vite application with the guided demo, analysis, outcomes, learning loop, and chat
- `app.py`: Legacy Streamlit interface retained for compatibility and smoke tests
- `tests/`: Automated unit & smoke test suite (runs offline with mock Hindsight client)

## Tests (offline / zero network needed)
```bash
python -m unittest discover -s tests -t . -v
```
