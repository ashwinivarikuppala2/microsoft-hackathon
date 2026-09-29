import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BookOpen,
  Bot,
  BrainCircuit,
  Check,
  ChevronDown,
  CircleHelp,
  Database,
  FileClock,
  FlaskConical,
  Gauge,
  Handshake,
  History,
  LoaderCircle,
  MessageSquareText,
  PanelLeftClose,
  Plus,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  Trophy,
  Upload,
  X,
} from "lucide-react";

const API = "/api";
const NAV = [
  { id: "demo", label: "Guided demo", icon: Sparkles },
  { id: "intelligence", label: "Deal intelligence", icon: Target },
  { id: "outcome", label: "Record outcome", icon: FileClock },
  { id: "loop", label: "Learning loop", icon: Activity },
  { id: "chat", label: "DealMind chat", icon: MessageSquareText },
];
const QUICK_PROMPTS = [
  "What is our best move against FreightIQ?",
  "Why did Harborline Freight lose?",
  "How should we handle CISO HIPAA concerns?",
];
const emptyResult = {
  memories: [],
  evidence: [],
  objection_patterns: [],
  competitor_patterns: [],
  recommendations: [],
  deal_playbooks: [],
};

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.join(" ")
      : body.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return body;
}

function money(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

const GUIDED_STEPS = [
  "Start with little/no relevant memory",
  "Ask the pricing-objection question",
  "Recalled Hindsight experiences",
  "Historical evidence",
  "Evidence-based recommendation",
  "Record WON / LOST / STALLED",
  "Save outcome to Hindsight",
  "Create a future similar deal",
  "New experience recalled & used",
];
const OBJECTION_KEYWORDS = {
  "Price & Commercial Terms": [
    "price",
    "cheaper",
    "discount",
    "expensive",
    "cost",
    "budget",
    "quote",
    "rate",
    "undercut",
    "license",
    "fee",
    "pricing",
  ],
  "Security, Privacy & Compliance": [
    "security",
    "hipaa",
    "gdpr",
    "compliance",
    "ciso",
    "privacy",
    "soc 2",
    "audit",
    "validation",
    "questionnaire",
  ],
  "Adoption & Change Fatigue": [
    "adopt",
    "adoption",
    "training",
    "fatigue",
    "complex",
    "sprawl",
    "in-house",
    "burden",
    "team",
    "internal",
  ],
  "Implementation & Timeline": [
    "timeline",
    "go-live",
    "months",
    "deploy",
    "disrupt",
    "delay",
    "shipping",
    "schedule",
  ],
  "Integrations & Technical Parity": [
    "integrate",
    "connector",
    "tms",
    "api",
    "parity",
    "workflow",
    "feature",
  ],
  "Lock-in & Contract Terms": [
    "lock-in",
    "term",
    "contract",
    "viability",
    "unproven",
    "flexible",
  ],
};

function objectionCategory(text) {
  const value = (text || "").toLowerCase();
  return (
    Object.entries(OBJECTION_KEYWORDS).find(([, words]) =>
      words.some((word) => value.includes(word)),
    )?.[0] || "Value Proposition & Fit"
  );
}

function recordRelevance(current, record) {
  const reasons = [];
  [
    ["competitor", "competitor"],
    ["industry", "industry"],
    ["product", "product"],
    ["stage", "deal stage"],
  ].forEach(([field, label]) => {
    const live = (current?.[field] || "").trim();
    const past = (record?.[field] || "").trim();
    if (live && past && live.toLowerCase() === past.toLowerCase())
      reasons.push(`Same ${label}: ${past}`);
  });
  const currentObjection = objectionCategory(current?.objection);
  const pastObjection = objectionCategory(record?.objection);
  if (
    current?.objection?.trim() &&
    currentObjection !== "Value Proposition & Fit" &&
    currentObjection === pastObjection
  )
    reasons.push(`Same kind of objection: ${pastObjection}`);
  const currentConcern = objectionCategory(current?.stakeholder_concern);
  const pastConcern = objectionCategory(record?.stakeholder_concern);
  if (
    current?.stakeholder_concern?.trim() &&
    currentConcern !== "Value Proposition & Fit" &&
    currentConcern === pastConcern
  )
    reasons.push(`Similar stakeholder concern theme: ${pastConcern}`);
  return reasons.length
    ? reasons
    : [
        "Recalled by Hindsight as related to this deal; no exact attribute or objection-theme match.",
      ];
}

function realCitations(citations = [], evidence = []) {
  const records = new Map(
    evidence
      .filter((item) => item.record)
      .map((item) => [item.deal_id, item.record]),
  );
  return citations.flatMap((text) => {
    const id = text.match(/^Deal (D-\d+)\b/)?.[1];
    return id && records.has(id) ? [[text, records.get(id)]] : [];
  });
}

function asList(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value.filter(Boolean);
  return [String(value)].filter(Boolean);
}

function playbookMap(report) {
  return Object.fromEntries(
    (report?.deal_playbooks || []).map((playbook) => [
      playbook.deal_id,
      playbook,
    ]),
  );
}

function similarityPercent(score) {
  const value = Number(score || 0);
  return `${Math.round(value * 100)}%`;
}

function guidedEvidenceReasons(item, recommendedLabel) {
  const labels = {
    objection: "same objection type",
    industry: "same industry",
    size: "same company size",
    role: "same buyer role",
    competitor: "same competitor",
  };
  const reasons = [];
  const matched = (item.matched || [])
    .map((field) => labels[field])
    .filter(Boolean);
  if (matched.length)
    reasons.push(
      `Matched on ${matched.join(", ")} (similarity ${Number(item.similarity).toFixed(2)}).`,
    );
  const outcome = item.outcome.toLowerCase();
  if (item.signal === "supports" && item.tactic === recommendedLabel)
    reasons.push(
      `${item.outcome} using the recommended approach, which supports recommending it.`,
    );
  else if (item.signal === "supports")
    reasons.push(
      `${item.outcome} using ${item.tactic}, which argues against leading with it.`,
    );
  else if (item.signal === "cautions")
    reasons.push(
      `The recommended approach was used here and the deal was ${outcome}: treat with caution.`,
    );
  else
    reasons.push(
      `${item.outcome} using ${item.tactic}; noted as context, not a driver of this recommendation.`,
    );
  return reasons;
}

function Field({ label, children, className = "", hint }) {
  return (
    <label className={`field ${className}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

function Panel({ children, className = "", title, aside }) {
  return (
    <section className={`panel ${className}`}>
      {(title || aside) && (
        <div className="panel-head">
          {title && <h2>{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

function Button({
  children,
  icon: Icon,
  variant = "secondary",
  className = "",
  ...props
}) {
  return (
    <button className={`button button-${variant} ${className}`} {...props}>
      {Icon && <Icon size={16} strokeWidth={1.8} />}
      {children}
    </button>
  );
}

function OutcomeTag({ outcome }) {
  const value = (outcome || "").toLowerCase().replace(" ", "-");
  return (
    <span className={`outcome-tag outcome-${value}`}>
      {outcome || "Unknown"}
    </span>
  );
}

function ProgressLine({ value = 0, color = "green" }) {
  return (
    <div className={`progress-line progress-${color}`}>
      <span style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

function EmptyState({ icon: Icon = Search, title, children }) {
  return (
    <div className="empty-state">
      <Icon size={22} />
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  );
}

function PageTitle({ eyebrow, title, subtitle, right }) {
  return (
    <div className="page-title">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

function MemoryList({ memories = [] }) {
  if (!memories.length)
    return (
      <EmptyState title="No memories recalled">
        Load historical deals from the sidebar, then try again.
      </EmptyState>
    );
  return (
    <div className="memory-list">
      {memories.map((memory, index) => (
        <details
          className="memory-row"
          key={memory.id || memory.document_id || index}
        >
          <summary>
            <span className="memory-index">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="memory-copy">
              <strong>
                {memory.metadata?.customer ||
                  memory.metadata?.company ||
                  memory.document_id ||
                  memory.type ||
                  "Recalled fact"}
              </strong>
              <span>{memory.text}</span>
            </span>
            <ChevronDown size={15} />
          </summary>
          <div className="memory-expanded">
            <code>{memory.id || memory.document_id || "Hindsight fact"}</code>
            <p>{memory.text}</p>
          </div>
        </details>
      ))}
    </div>
  );
}

function App() {
  const [bootstrap, setBootstrap] = useState(null);
  const [activeTab, setActiveTab] = useState("demo");
  const [mobileNav, setMobileNav] = useState(false);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState(null);
  const [deal, setDeal] = useState(null);
  const [report, setReport] = useState(null);
  const [demoScene, setDemoScene] = useState(1);
  const [demoQuestion, setDemoQuestion] = useState(
    "How should I handle this pricing objection?",
  );
  const [demoAnswer, setDemoAnswer] = useState(null);
  const [demoResults, setDemoResults] = useState({});
  const [demoSaved, setDemoSaved] = useState({});
  const [demoTactic, setDemoTactic] = useState("proof");
  const [demoOutcome, setDemoOutcome] = useState("LOST");
  const [demoNote, setDemoNote] = useState("");
  const [outcomeForm, setOutcomeForm] = useState(null);
  const [savedOutcome, setSavedOutcome] = useState(null);
  const [loopForm, setLoopForm] = useState(null);
  const [loopReport, setLoopReport] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [chatInput, setChatInput] = useState("");

  const refresh = async () => {
    const data = await request("/bootstrap");
    setBootstrap(data);
    setDeal((current) => current || data.current_deal);
    setOutcomeForm(
      (current) =>
        current || createOutcomeForm(data.current_deal, data.deals_count),
    );
    setLoopForm((current) => current || createLoopForm(data.current_deal));
    setDemoSaved(data.demo.saved || {});
    setDemoResults(data.demo.results || {});
    const restored = data.demo.results?.[String(demoScene)];
    setDemoAnswer(
      (current) =>
        current ||
        (restored ? { ...restored, without_new_memory: null } : null),
    );
    return data;
  };

  useEffect(() => {
    refresh().catch((error) =>
      setNotice({ kind: "error", text: error.message }),
    );
  }, []);

  useEffect(() => {
    if (bootstrap?.demo?.results?.[String(demoScene)]) {
      const saved = bootstrap.demo.results[String(demoScene)];
      setDemoAnswer(
        (current) => current || { ...saved, without_new_memory: null },
      );
    }
    setDemoOutcome(demoScene === 1 ? "LOST" : "WON");
    setDemoTactic(demoAnswer?.analysis?.recommendation?.key || "proof");
  }, [demoScene, bootstrap]);

  const run = async (key, action) => {
    setBusy(key);
    setNotice(null);
    try {
      return await action();
    } catch (error) {
      setNotice({ kind: "error", text: error.message });
      return null;
    } finally {
      setBusy("");
    }
  };

  const setPreset = (number) =>
    run("preset", async () => {
      const preset = await request(`/presets/${number}`, { method: "POST" });
      setDeal(preset);
      setReport(null);
      setActiveTab("intelligence");
      setNotice({ kind: "success", text: "Sample deal loaded." });
    });

  const loadHistory = () =>
    run("history", async () => {
      const result = await request("/historical/load", { method: "POST" });
      setNotice({
        kind: result.ok ? "success" : "error",
        text: `${result.retained.length} deals loaded${Object.keys(result.failed).length ? `, ${Object.keys(result.failed).length} failed` : ""}.`,
      });
      await refresh();
    });

  const testConnection = () =>
    run("connection", async () => {
      const result = await request("/hindsight/test", { method: "POST" });
      setNotice({
        kind: result.success ? "success" : "error",
        text: result.steps?.join(" ") || "Connection test completed.",
      });
    });

  const analyzeDeal = (event) => {
    event.preventDefault();
    run("analysis", async () => {
      const result = await request("/analysis", {
        method: "POST",
        body: JSON.stringify(deal),
      });
      setReport(result);
      setNotice({ kind: "success", text: "Similar-deal analysis completed." });
    });
  };

  const askDemo = (event) => {
    event.preventDefault();
    run("demo-ask", async () => {
      const result = await request("/demo/ask", {
        method: "POST",
        body: JSON.stringify({ scene: demoScene, query: demoQuestion }),
      });
      setDemoAnswer(result);
      setDemoResults((current) => ({ ...current, [String(demoScene)]: result }));
      setDemoTactic(result.analysis.recommendation.key || "proof");
    });
  };

  const saveDemo = (event) => {
    event.preventDefault();
    run("demo-save", async () => {
      const result = await request("/demo/outcome", {
        method: "POST",
        body: JSON.stringify({
          scene: demoScene,
          query: demoQuestion,
          tactic: demoTactic,
          outcome: demoOutcome,
          note: demoNote,
        }),
      });
      setDemoSaved((current) => ({ ...current, [String(demoScene)]: result }));
      setNotice({
        kind: "success",
        text: "Outcome retained. DealMind has updated its learned playbook.",
      });
      const refreshed = await request("/demo/ask", {
        method: "POST",
        body: JSON.stringify({ scene: demoScene, query: demoQuestion }),
      });
      setDemoAnswer(refreshed);
      setDemoResults((current) => ({ ...current, [String(demoScene)]: refreshed }));
    });
  };

  const resetDemo = () =>
    run("reset-demo", async () => {
      await request("/demo/reset", { method: "POST" });
      setDemoScene(1);
      setDemoQuestion("How should I handle this pricing objection?");
      setDemoAnswer(null);
      setDemoResults({});
      setDemoSaved({});
      setDemoNote("");
      setNotice({ kind: "success", text: "Guided demo restarted." });
      await refresh();
    });

  const saveOutcome = (event) => {
    event.preventDefault();
    run("outcome", async () => {
      const result = await request("/outcomes", {
        method: "POST",
        body: JSON.stringify(outcomeForm),
      });
      setSavedOutcome(result);
      setNotice({
        kind: "success",
        text: `${result.deal_id} saved to Hindsight memory.`,
      });
      await refresh();
    });
  };

  const runLoop = (event) => {
    event.preventDefault();
    run("loop", async () => {
      const { recorded_outcome, future_deal } = loopForm;
      const result = await request("/learning-loop", {
        method: "POST",
        body: JSON.stringify({ recorded_outcome, future_deal }),
      });
      setLoopReport(result);
      setNotice({
        kind: "success",
        text: "End-to-end learning loop completed.",
      });
      await refresh();
    });
  };

  const sendChat = async (message = chatInput) => {
    const clean = message.trim();
    if (!clean) return;
    setChatInput("");
    const userMessage = { role: "user", content: clean };
    setChatHistory((history) => [...history, userMessage]);
    await run("chat", async () => {
      const result = await request("/chat", {
        method: "POST",
        body: JSON.stringify({ message: clean, current_deal: deal }),
      });
      setChatHistory((history) => [
        ...history,
        userMessage,
        { role: "assistant", ...result },
      ]);
    });
  };

  const updateDeal = (key, value) =>
    setDeal((current) => ({ ...current, [key]: value }));
  const updateOutcome = (key, value) =>
    setOutcomeForm((current) => ({ ...current, [key]: value }));
  const updateLoop = (section, key, value) =>
    setLoopForm((current) => ({
      ...current,
      [section]: { ...current[section], [key]: value },
    }));

  if (!bootstrap)
    return (
      <div className="boot-screen">
        <div className="brand-mark">
          <BrainCircuit size={24} />
        </div>
        <LoaderCircle className="spin" size={22} />
        <span>Opening the deal desk...</span>
      </div>
    );

  const configReady = bootstrap.config.available;
  const currentScene = bootstrap.scenes[String(demoScene)];
  const currentDemoSave = demoSaved[String(demoScene)];
  const scene1Result = demoScene === 1 ? demoAnswer : demoResults["1"];
  const scene2Result = demoScene === 2 ? demoAnswer : demoResults["2"];
  const progressFlags = [
    Boolean(scene1Result && scene1Result.analysis.similar.length === 0),
    Boolean(scene1Result),
    Boolean(scene1Result?.memories.length),
    Boolean(scene1Result?.analysis.evidence.length || scene2Result?.analysis.evidence.length),
    Boolean(scene1Result?.analysis.mode === "evidence" || scene2Result?.analysis.mode === "evidence"),
    Boolean(demoSaved["1"]),
    Boolean(demoSaved["1"]),
    demoScene === 2,
    Boolean(
      demoSaved["1"] &&
      scene2Result?.analysis.similar.some((item) => item.exp.deal_id === bootstrap.scenes["1"].deal_id),
    ),
  ];
  const completedSteps = progressFlags.filter(Boolean).length;

  return (
    <div className="app-frame">
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <div className="brand-lockup">
          <div className="brand-mark">
            <BrainCircuit size={22} />
          </div>
          <div>
            <strong>DealMind</strong>
            <span>REVENUE INTELLIGENCE</span>
          </div>
          <button
            className="icon-button sidebar-close"
            onClick={() => setMobileNav(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>
        <div className="sidebar-kicker">WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`side-link ${activeTab === id ? "is-active" : ""}`}
              onClick={() => {
                setActiveTab(id);
                setMobileNav(false);
              }}
            >
              <Icon size={17} />
              <span>{label}</span>
              {activeTab === id && <span className="nav-marker" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-rule" />
        <div className="sidebar-section-head">
          <span>HINDSIGHT MEMORY</span>
          <span
            className={`status-light ${configReady ? "online" : "offline"}`}
          />
        </div>
        <div className="memory-status">
          <div className="memory-status-icon">
            <Database size={16} />
          </div>
          <div>
            <strong>{bootstrap.demo.backend}</strong>
            <span>
              {configReady
                ? `Bank · ${bootstrap.config.bank_id}`
                : "Cloud connection not configured"}
            </span>
          </div>
        </div>
        {bootstrap.demo.notice && (
          <div className="side-note">{bootstrap.demo.notice}</div>
        )}
        {!configReady && (
          <div className="setup-note">{bootstrap.config.message}</div>
        )}
        <Button
          icon={Upload}
          className="side-action"
          onClick={loadHistory}
          disabled={!configReady || busy === "history"}
        >
          {busy === "history"
            ? "Loading deals..."
            : `Load ${bootstrap.deals_count} historical deals`}
        </Button>
        <Button
          icon={ShieldCheck}
          className="side-action"
          onClick={testConnection}
          disabled={!configReady || busy === "connection"}
        >
          {busy === "connection"
            ? "Testing connection..."
            : "Run connection test"}
        </Button>
        <div className="sidebar-rule" />
        <div className="sidebar-section-head">
          <span>QUICK DEALS</span>
          <span className="muted-count">03</span>
        </div>
        <button className="preset-link" onClick={() => setPreset(1)}>
          <span className="preset-symbol freight">F</span>
          <span>
            <strong>FreightIQ price battle</strong>
            <small>Logistics · Negotiation</small>
          </span>
          <ArrowRight size={14} />
        </button>
        <button className="preset-link" onClick={() => setPreset(2)}>
          <span className="preset-symbol health">H</span>
          <span>
            <strong>Healthcare HIPAA review</strong>
            <small>Healthcare · Security</small>
          </span>
          <ArrowRight size={14} />
        </button>
        <button className="preset-link" onClick={() => setPreset(3)}>
          <span className="preset-symbol finance">O</span>
          <span>
            <strong>Optima adoption risk</strong>
            <small>Financial · Proposal</small>
          </span>
          <ArrowRight size={14} />
        </button>
        <div className="sidebar-spacer" />
        <div className="sidebar-footer">
          <div className="footer-orbit">
            <Activity size={16} />
          </div>
          <div>
            <span>ACTIVE DEALS INDEX</span>
            <strong>{bootstrap.deals_count} historical records</strong>
          </div>
        </div>
      </aside>

      {mobileNav && (
        <button
          className="nav-scrim"
          onClick={() => setMobileNav(false)}
          aria-label="Close menu"
        />
      )}

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobileNav(true)}
              aria-label="Open navigation"
            >
              <PanelLeftClose size={19} />
            </button>
            <div className="crumb">
              <span>Deal desk</span>
              <span className="crumb-slash">/</span>
              <strong>
                {NAV.find((item) => item.id === activeTab)?.label}
              </strong>
            </div>
          </div>
          <div className="topbar-right">
            <span
              className={`connection-pill ${configReady ? "connected" : "disconnected"}`}
            >
              <span />
              {configReady ? "HINDSIGHT CONNECTED" : "LOCAL DEMO MODE"}
            </span>
            <div className="topbar-date">
              <span>DEALMIND</span>
              <strong>SALES PLAYBOOK</strong>
            </div>
          </div>
        </header>

        {notice && (
          <div className={`toast toast-${notice.kind}`} role="status">
            <span>
              {notice.kind === "error" ? (
                <AlertTriangle size={16} />
              ) : (
                <Check size={16} />
              )}
              {notice.text}
            </span>
            <button
              className="icon-button"
              onClick={() => setNotice(null)}
              aria-label="Dismiss notification"
            >
              <X size={15} />
            </button>
          </div>
        )}

        <div className="content-wrap">
          {activeTab === "demo" && (
            <>
              <PageTitle
                eyebrow="FIELD GUIDE / 01"
                title="Learn by doing"
                subtitle="A live deal, a real objection, and the memory that changes the next move."
                right={
                  <Button
                    icon={RotateCcw}
                    onClick={resetDemo}
                    disabled={busy === "reset-demo"}
                  >
                    Restart demo
                  </Button>
                }
              />
              <div
                className="scene-switcher"
                role="tablist"
                aria-label="Demo scenes"
              >
                {[1, 2].map((scene) => (
                  <button
                    key={scene}
                    role="tab"
                    aria-selected={demoScene === scene}
                    className={`scene-tab ${demoScene === scene ? "selected" : ""}`}
                    onClick={() => {
                      setDemoScene(scene);
                      const restored = demoResults[String(scene)] || bootstrap.demo.results?.[String(scene)] || null;
                      setDemoAnswer(restored);
                      setDemoQuestion(restored?.query || "How should I handle this pricing objection?");
                    }}
                  >
                    <span className="scene-number">0{scene}</span>
                    <span>
                      <strong>
                        {scene === 1 ? "Cold start" : "Future similar deal"}
                      </strong>
                      <small>
                        {scene === 1
                          ? "Northwind Logistics"
                          : "Contoso Freight"}
                      </small>
                    </span>
                    {demoSaved[String(scene)] && (
                      <BadgeCheck size={17} className="scene-check" />
                    )}
                  </button>
                ))}
              </div>
              <div className={`scene-context ${demoScene === 1 ? "cold" : "future"}`}>
                <Sparkles size={15} />
                <span><strong>{demoScene === 1 ? "Cold start" : "Future similar deal"}</strong>{demoScene === 1 ? " · DealMind begins with little relevant deal memory." : " · The saved outcome can now inform this similar opportunity."}</span>
              </div>
              <div className="demo-grid">
                <div className="demo-main">
                  <Panel className="deal-brief">
                    <div className="brief-topline">
                      <span className="brief-kicker">CURRENT OPPORTUNITY</span>
                      <span className="stage-chip">{currentScene.stage}</span>
                    </div>
                    <div className="brief-title">
                      <div>
                        <h2>{currentScene.company}</h2>
                        <p>
                          {currentScene.industry} <span>·</span>{" "}
                          {currentScene.size}
                        </p>
                      </div>
                      <div className="brief-value">
                        <span>DEAL VALUE</span>
                        <strong>{money(currentScene.value)}</strong>
                      </div>
                    </div>
                    <div className="brief-metrics">
                      <div>
                        <span>BUYER</span>
                        <strong>{currentScene.role}</strong>
                      </div>
                      <div>
                        <span>COMPETITOR</span>
                        <strong>{currentScene.competitor}</strong>
                      </div>
                      <div>
                        <span>OBJECTION</span>
                        <strong>{currentScene.objection}</strong>
                      </div>
                    </div>
                    <blockquote>
                      <span>BUYER SAID</span>
                      <p>“{currentScene.customer_said}”</p>
                    </blockquote>
                  </Panel>
                  <Panel title="Ask about this deal" className="ask-panel">
                    <form onSubmit={askDemo} className="ask-row">
                      <input
                        value={demoQuestion}
                        onChange={(event) =>
                          setDemoQuestion(event.target.value)
                        }
                        aria-label="Question for DealMind"
                      />
                      <Button
                        icon={busy === "demo-ask" ? LoaderCircle : ArrowRight}
                        variant="dark"
                        type="submit"
                        disabled={
                          busy === "demo-ask" || Boolean(currentDemoSave)
                        }
                      >
                        {busy === "demo-ask" ? "Searching..." : "Ask DealMind"}
                      </Button>
                    </form>
                    {demoAnswer && (
                      <div className="answer-summary">
                        <span className="answer-mark">
                          <BrainCircuit size={16} />
                        </span>
                        <span>
                          {demoAnswer.memories.length} memories recalled{" "}
                          <i>·</i> {demoAnswer.analysis.similar.length} similar
                          deals <i>·</i>{" "}
                          {demoAnswer.analysis.mode === "evidence"
                            ? "Evidence-based"
                            : "Playbook default"}
                        </span>
                      </div>
                    )}
                  </Panel>
                  {demoAnswer && (
                    <>
                      <Panel
                        title="Recalled memory"
                        aside={
                          <span className="section-count">
                            {demoAnswer.memories.length} FACTS
                          </span>
                        }
                      >
                        <MemoryList memories={demoAnswer.memories} />
                      </Panel>
                      <div className="two-col-panels">
                        <Panel
                          title="Similar deals"
                          aside={<Search size={16} className="panel-icon" />}
                        >
                          {demoAnswer.analysis.similar.length ? (
                            <div className="similar-list">
                              {demoAnswer.analysis.similar.map(
                                ({ exp, sim, matched }) => (
                                  <article
                                    className="similar-row"
                                    key={exp.deal_id}
                                  >
                                    <div>
                                      <strong>{exp.company}</strong>
                                      <span>
                                        {exp.deal_id} ·{" "}
                                        {TACTICS_LABEL(bootstrap, exp.tactic)}
                                      </span>
                                    </div>
                                    <OutcomeTag outcome={exp.outcome} />
                                    <div className="similar-meter">
                                      <ProgressLine value={sim} color="teal" />
                                      <span>{Number(sim).toFixed(2)}</span>
                                    </div>
                                    <small>Matched: {matched.join(", ")}</small>
                                  </article>
                                ),
                              )}
                            </div>
                          ) : (
                            <EmptyState
                              icon={History}
                              title="No similar deals in memory yet."
                            />
                          )}
                        </Panel>
                        <Panel
                          title="Patterns"
                          aside={
                            <TrendingUp size={16} className="panel-icon" />
                          }
                        >
                          <ul className="pattern-list">
                            {demoAnswer.analysis.patterns.map((pattern) => (
                              <li key={pattern}>{pattern}</li>
                            ))}
                          </ul>
                          {demoAnswer.analysis.avoid.length > 0 && (
                            <div className="avoid-note">
                              <AlertTriangle size={15} /> Deprioritize:{" "}
                              {demoAnswer.analysis.avoid
                                .map((row) => row.label)
                                .join(", ")}
                            </div>
                          )}
                        </Panel>
                      </div>
                      <Panel
                        title="Evidence and recommendation"
                        className="recommendation-panel"
                        aside={
                          <span
                            className={`confidence-chip ${demoAnswer.analysis.mode}`}
                          >
                            {
                              demoAnswer.analysis.recommendation
                                .confidence_label
                            }{" "}
                            confidence ·{" "}
                            {Math.round(
                              demoAnswer.analysis.recommendation.confidence *
                                100,
                            )}
                            %
                          </span>
                        }
                      >
                        <div className="recommendation-layout">
                          <div className="recommendation-copy">
                            <span className="recommend-label">
                              <Target size={15} /> PRIMARY MOVE
                            </span>
                            <h3>{demoAnswer.analysis.recommendation.label}</h3>
                            <p>{demoAnswer.analysis.recommendation.why}</p>
                            <ol>
                              {demoAnswer.analysis.recommendation.track.map(
                                (step) => (
                                  <li key={step}>{step}</li>
                                ),
                              )}
                            </ol>
                          </div>
                          <div className="risk-box">
                            <div className="risk-heading">
                              <Gauge size={17} />
                              <span>DEAL RISK</span>
                            </div>
                            <strong
                              className={`risk-${demoAnswer.analysis.risk.level.toLowerCase()}`}
                            >
                              {demoAnswer.analysis.risk.level}
                            </strong>
                            <div className="risk-score">
                              {Math.round(demoAnswer.analysis.risk.score * 100)}
                              % score
                            </div>
                            <ProgressLine
                              value={demoAnswer.analysis.risk.score}
                              color="orange"
                            />
                            <ul>
                              {demoAnswer.analysis.risk.reasons.map(
                                (reason) => (
                                  <li key={reason}>{reason}</li>
                                ),
                              )}
                            </ul>
                          </div>
                        </div>
                        {demoAnswer.analysis.evidence.length > 0 && (
                          <div className="evidence-strip">
                            <span>SUPPORTING PRECEDENT</span>
                            {demoAnswer.analysis.evidence.map((item) => (
                              <div key={item.memory_id}>
                                <strong>{item.company}</strong>
                                <OutcomeTag outcome={item.outcome} />
                                <small>
                                  {guidedEvidenceReasons(item, demoAnswer.analysis.recommendation.label).join(" ")}
                                </small>
                                {item.lesson && <small className="evidence-lesson">Lesson: {item.lesson}</small>}
                              </div>
                            ))}
                          </div>
                        )}
                      </Panel>
                      {demoScene === 2 && demoAnswer.without_new_memory && (
                        <Panel
                          title="What the new experience changed"
                          className="counterfactual-panel"
                        >
                          <p>
                            The {DEMO_SAVED_LABEL(demoSaved)} outcome from
                            Northwind was recalled for this deal.
                          </p>
                          <div className="counterfactual-grid">
                            <div>
                              <span>WITHOUT THE NEW MEMORY</span>
                              <strong>
                                {
                                  demoAnswer.without_new_memory.recommendation
                                    .label
                                }
                              </strong>
                              <small>
                                {Math.round(
                                  demoAnswer.without_new_memory.recommendation
                                    .confidence * 100,
                                )}
                                % confidence ·{" "}
                                {demoAnswer.without_new_memory.risk.level} risk
                              </small>
                            </div>
                            <ArrowRight size={18} />
                            <div>
                              <span>WITH THE NEW MEMORY</span>
                              <strong>
                                {demoAnswer.analysis.recommendation.label}
                              </strong>
                              <small>
                                {Math.round(
                                  demoAnswer.analysis.recommendation
                                    .confidence * 100,
                                )}
                                % confidence · {demoAnswer.analysis.risk.level}{" "}
                                risk
                              </small>
                            </div>
                          </div>
                        </Panel>
                      )}
                      <Panel
                        title="Record what happened"
                        className="demo-outcome-panel"
                        aside={
                          currentDemoSave && (
                            <OutcomeTag outcome={currentDemoSave.outcome} />
                          )
                        }
                      >
                        {currentDemoSave ? (
                          <div className="saved-lesson">
                            <div className="saved-check">
                              <Check size={18} />
                            </div>
                            <div>
                              <strong>
                                Outcome retained in {bootstrap.demo.backend}
                              </strong>
                              <p>{currentDemoSave.lesson}</p>
                              <div className="learning-metrics">
                                <span>
                                  TACTIC SCORE{" "}
                                  <b>
                                    {Number(
                                      currentDemoSave.score_before,
                                    ).toFixed(2)}{" "}
                                    →{" "}
                                    {Number(
                                      currentDemoSave.score_after,
                                    ).toFixed(2)}
                                  </b>
                                </span>
                                <span>
                                  RECOMMENDATION{" "}
                                  <b>{currentDemoSave.rec_after.label}</b>
                                </span>
                              </div>
                            </div>
                          </div>
                        ) : demoAnswer ? (
                          <form
                            onSubmit={saveDemo}
                            className="outcome-inline-form"
                          >
                            <Field label="Tactic used">
                              <select
                                value={demoTactic}
                                onChange={(event) =>
                                  setDemoTactic(event.target.value)
                                }
                              >
                                {Object.entries(bootstrap.tactics).map(
                                  ([key, tactic]) => (
                                    <option value={key} key={key}>
                                      {tactic.label}
                                    </option>
                                  ),
                                )}
                              </select>
                            </Field>
                            <Field label="Outcome">
                              <select
                                value={demoOutcome}
                                onChange={(event) =>
                                  setDemoOutcome(event.target.value)
                                }
                              >
                                {bootstrap.outcomes.map((outcome) => (
                                  <option key={outcome}>{outcome}</option>
                                ))}
                              </select>
                            </Field>
                            <Field label="Rep note">
                              <input
                                value={demoNote}
                                onChange={(event) =>
                                  setDemoNote(event.target.value)
                                }
                                placeholder="Optional context from the deal"
                              />
                            </Field>
                            <Button
                              icon={busy === "demo-save" ? LoaderCircle : Check}
                              variant="dark"
                              type="submit"
                              disabled={busy === "demo-save"}
                            >
                              {busy === "demo-save"
                                ? "Saving..."
                                : "Save outcome"}
                            </Button>
                          </form>
                        ) : (
                          <EmptyState
                            icon={CircleHelp}
                            title="Ask DealMind before recording an outcome."
                          />
                        )}
                        {demoScene === 1 && currentDemoSave && (
                          <Button
                            icon={ArrowRight}
                            variant="accent"
                            className="next-scene"
                            onClick={() => {
                              setDemoScene(2);
                              const restored = demoResults["2"] || bootstrap.demo.results?.["2"] || null;
                              setDemoAnswer(restored);
                              setDemoQuestion(restored?.query || "How should I handle this pricing objection?");
                            }}
                          >
                            Create future similar deal
                          </Button>
                        )}
                      </Panel>
                    </>
                  )}
                </div>
                <aside className="demo-rail">
                  <div className="rail-heading">
                    <span>DEMO PROGRESS</span>
                    <span>{String(completedSteps).padStart(2, "0")}/09</span>
                  </div>
                  <div className="rail-track">
                    <span
                      style={{
                        height: `${Math.round((completedSteps / GUIDED_STEPS.length) * 100)}%`,
                      }}
                    />
                  </div>
                  <div className="rail-list">
                    {GUIDED_STEPS.map((label, index) => {
                      const result = index < 3 ? scene1Result : scene2Result || scene1Result;
                      const detail = [
                        scene1Result ? (progressFlags[0] ? "No similar deal recalled" : "Similar deals found") : "Waiting for cold-start recall",
                        scene1Result ? scene1Result.query : "Submit the pricing question",
                        scene1Result ? `${scene1Result.memories.length} facts found` : "Waiting for query",
                        result ? `${result.analysis.evidence.length} evidence points` : "Similar past deals",
                        result ? result.analysis.recommendation.label : "Evidence-led move",
                        demoSaved["1"] ? demoSaved["1"].outcome : "Add the result",
                        demoSaved["1"] ? "Experience retained" : "Save the recorded outcome",
                        demoScene === 2 ? "Contoso Freight loaded" : "Continue to future deal",
                        scene2Result ? (progressFlags[8] ? "Northwind experience used" : "New experience not matched") : "Waiting for future-deal recall",
                      ][index];
                      return (
                        <div className={`rail-step ${progressFlags[index] ? "done" : ""}`} key={label}>
                          <span>{String(index + 1).padStart(2, "0")}</span>
                          <div><strong>{label}</strong><small>{detail}</small></div>
                          {progressFlags[index] && <Check size={14} />}
                        </div>
                      );
                    })}
                  </div>
                  <div className="rail-callout">
                    <BrainCircuit size={17} />
                    <p>
                      Every recommendation shows whether history supports it or
                      it is still a playbook default.
                    </p>
                  </div>
                </aside>
              </div>
            </>
          )}

          {activeTab === "intelligence" && (
            <>
              <PageTitle
                eyebrow="LIVE OPPORTUNITY / 02"
                title="Deep deal intelligence"
                subtitle="Search deal history, surface risk, and build a playbook for the opportunity in front of you."
                right={
                  <span className="indexed-badge">
                    <Database size={15} />
                    {bootstrap.deals_count} records indexed
                  </span>
                }
              />
              <form onSubmit={analyzeDeal} className="deal-form panel">
                <div className="form-section-label">
                  <span>01</span>
                  <strong>Opportunity profile</strong>
                  <small>CORE DETAILS</small>
                </div>
                <div className="form-grid three">
                  <Field label="Customer">
                    <input
                      value={deal?.customer || ""}
                      onChange={(e) => updateDeal("customer", e.target.value)}
                      placeholder="Customer name"
                    />
                  </Field>
                  <Field label="Industry">
                    <select
                      value={deal?.industry || ""}
                      onChange={(e) => updateDeal("industry", e.target.value)}
                    >
                      {bootstrap.industries.map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Product">
                    <select
                      value={deal?.product || ""}
                      onChange={(e) => updateDeal("product", e.target.value)}
                    >
                      {bootstrap.products.map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Deal value (USD)">
                    <input
                      type="number"
                      min="0"
                      step="5000"
                      value={deal?.value || 0}
                      onChange={(e) =>
                        updateDeal("value", Number(e.target.value))
                      }
                    />
                  </Field>
                  <Field label="Sales stage">
                    <select
                      value={deal?.stage || ""}
                      onChange={(e) => updateDeal("stage", e.target.value)}
                    >
                      {bootstrap.stages.map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Competitor">
                    <input
                      value={deal?.competitor || ""}
                      onChange={(e) => updateDeal("competitor", e.target.value)}
                      placeholder="Competitor or none"
                    />
                  </Field>
                </div>
                <div className="form-section-label separated">
                  <span>02</span>
                  <strong>Buyer signals</strong>
                  <small>WHAT IS BLOCKING THE DEAL?</small>
                </div>
                <div className="form-grid three">
                  <Field label="Customer objection">
                    <textarea
                      rows="2"
                      value={deal?.objection || ""}
                      onChange={(e) => updateDeal("objection", e.target.value)}
                      placeholder="What is the buyer pushing back on?"
                    />
                  </Field>
                  <Field label="Stakeholder concern">
                    <textarea
                      rows="2"
                      value={deal?.stakeholder_concern || ""}
                      onChange={(e) =>
                        updateDeal("stakeholder_concern", e.target.value)
                      }
                      placeholder="Who is concerned, and about what?"
                    />
                  </Field>
                  <Field label="Pricing discussion">
                    <textarea
                      rows="2"
                      value={deal?.pricing_discussion || ""}
                      onChange={(e) =>
                        updateDeal("pricing_discussion", e.target.value)
                      }
                      placeholder="Discounts, terms, quotes, concessions"
                    />
                  </Field>
                </div>
                <div className="form-submit-row">
                  <span>
                    <ShieldCheck size={15} /> Analysis is grounded in recalled
                    Hindsight memories.
                  </span>
                  <Button
                    icon={busy === "analysis" ? LoaderCircle : Search}
                    variant="dark"
                    type="submit"
                    disabled={!configReady || busy === "analysis"}
                  >
                    {busy === "analysis"
                      ? "Searching history..."
                      : "Find similar deals"}
                  </Button>
                </div>
              </form>
              {!configReady && (
                <div className="inline-warning">
                  <AlertTriangle size={16} /> Configure Hindsight in the
                  environment file to run live deal analysis. The guided demo
                  remains available.
                </div>
              )}
              {report && (
                <div className="report-stack">
                  <div className="report-summary">
                    <div>
                      <span>ANALYSIS FOR</span>
                      <strong>
                        {report.deal.customer || "Unnamed opportunity"}
                      </strong>
                      <small>
                        {report.deal.industry} · {report.deal.stage} ·{" "}
                        {money(report.deal.value)}
                      </small>
                    </div>
                    <div className="risk-summary">
                      <span>DEAL RISK</span>
                      <strong
                        className={`risk-${report.risk_analysis?.level?.toLowerCase()}`}
                      >
                        {report.risk_analysis?.level || "UNKNOWN"}
                      </strong>
                      <b>{report.risk_analysis?.score ?? 0}/100</b>
                    </div>
                  </div>
                  <Panel
                    title="Risk analysis"
                    aside={
                      <span className="section-count">
                        {report.risk_analysis?.risk_factors?.length || 0} RISK
                        FACTORS
                      </span>
                    }
                  >
                    <p className="report-summary-text">
                      {report.risk_analysis?.summary}
                    </p>
                    <div className="factor-grid">
                      {report.risk_analysis?.risk_factors?.map((factor) => (
                        <article
                          className={`factor-card severity-${factor.severity.toLowerCase()}`}
                          key={factor.title}
                        >
                          <div>
                            <AlertTriangle size={16} />
                            <strong>{factor.title}</strong>
                            <span>{factor.severity}</span>
                          </div>
                          <p>{factor.rationale}</p>
                          {factor.evidence_citation && (
                            <small>{factor.evidence_citation}</small>
                          )}
                        </article>
                      ))}
                    </div>
                    {report.risk_analysis?.mitigating_factors?.length > 0 && (
                      <div className="mitigating-row">
                        <ShieldCheck size={16} />
                        <div>
                          <strong>Protective factors</strong>
                          <span>
                            {report.risk_analysis.mitigating_factors.join(
                              " · ",
                            )}
                          </span>
                        </div>
                      </div>
                    )}
                  </Panel>
                  {(() => {
                    const playbooks = playbookMap(report);
                    const evidence = report.retrieval?.evidence || [];
                    const hasSimilarDeals = evidence.length > 0;

                    return (
                      <>
                        <Panel
                          title="Recommended similar deals"
                          aside={
                            <span className="section-count">
                              {evidence.length} RECOMMENDED
                            </span>
                          }
                        >
                          {hasSimilarDeals ? (
                            <div className="historical-grid">
                              {evidence.map((item, index) => {
                                const record = item.record || {};
                                const playbook = playbooks[item.deal_id];
                                const reasons =
                                  item.match_reasons?.length
                                    ? item.match_reasons
                                    : recordRelevance(report.deal, record);
                                const memories = item.memories || [];
                                const worked = asList(playbook?.worked);
                                const avoid = asList(playbook?.avoid);
                                const actions = asList(
                                  playbook?.recommended_actions,
                                );

                                return (
                                  <article
                                    className="historical-card recommended-deal-card"
                                    key={item.deal_id}
                                  >
                                    <div className="recommended-deal-header">
                                      <div className="recommended-deal-title">
                                        <span className="deal-rank">
                                          {String(index + 1).padStart(2, "0")}
                                        </span>
                                        <div>
                                          <strong>
                                            {record.customer || item.deal_id}
                                          </strong>
                                          <span>
                                            {item.deal_id} · {record.industry} · {record.product}
                                          </span>
                                        </div>
                                      </div>
                                      <div className="recommended-deal-meta">
                                        <OutcomeTag outcome={record.outcome} />
                                        <strong>
                                          {similarityPercent(
                                            item.similarity_score,
                                          )}
                                        </strong>
                                      </div>
                                    </div>

                                    <div className="similarity-bar-row">
                                      <span>SIMILARITY</span>
                                      <ProgressLine
                                        value={Number(
                                          item.similarity_score || 0,
                                        )}
                                        color="teal"
                                      />
                                    </div>

                                    <div className="recommended-section">
                                      <span className="recommended-label">
                                        <Target size={14} /> WHY THIS DEAL MATCHED
                                      </span>
                                      <div className="compact-chips">
                                        {reasons.slice(0, 4).map((reason) => (
                                          <span key={reason}>{reason}</span>
                                        ))}
                                      </div>
                                    </div>

                                    <div className="recommended-outcome">
                                      <div>
                                        <span>WHAT HAPPENED</span>
                                        <strong>
                                          {record.approach ||
                                            "No approach recorded."}
                                        </strong>
                                      </div>
                                      <p>
                                        {record.outcome_reason ||
                                          "No outcome reason recorded."}
                                      </p>
                                    </div>

                                    {(actions.length || worked.length || avoid.length) ? (
                                      <div className="recommended-playbook">
                                        <span className="recommended-label">
                                          <BookOpen size={14} /> SUGGESTED NEXT STEPS
                                        </span>
                                        {actions.length ? (
                                          <ol>
                                            {actions.slice(0, 3).map((action) => (
                                              <li key={action}>{action}</li>
                                            ))}
                                          </ol>
                                        ) : worked.length ? (
                                          <div className="mini-list success-list">
                                            {worked.slice(0, 2).map((item) => (
                                              <span key={item}>{item}</span>
                                            ))}
                                          </div>
                                        ) : null}
                                        {avoid.length > 0 && (
                                          <div className="compact-warning">
                                            <AlertTriangle size={13} />
                                            <span>{avoid[0]}</span>
                                          </div>
                                        )}
                                      </div>
                                    ) : null}

                                    <details className="deal-memory-detail">
                                      <summary>
                                        <BrainCircuit size={14} />
                                        <span>Hindsight evidence · {memories.length} memories</span>
                                        <ChevronDown size={14} />
                                      </summary>
                                      <div className="deal-memory-content">
                                        {memories.length ? (
                                          <MemoryList memories={memories} />
                                        ) : (
                                          <small>
                                            This deal was attributed from Hindsight recall, but no deal-specific memory was returned.
                                          </small>
                                        )}
                                      </div>
                                    </details>

                                    <details className="deal-memory-detail">
                                      <summary>
                                        <History size={14} />
                                        <span>View deal details</span>
                                        <ChevronDown size={14} />
                                      </summary>
                                      <div className="deal-detail-grid">
                                        <div>
                                          <span>COMPETITOR</span>
                                          <strong>{record.competitor || "None recorded"}</strong>
                                        </div>
                                        <div>
                                          <span>STAGE</span>
                                          <strong>{record.stage || "Unknown"}</strong>
                                        </div>
                                        <div>
                                          <span>VALUE</span>
                                          <strong>{money(record.value)}</strong>
                                        </div>
                                        <div>
                                          <span>DATE</span>
                                          <strong>{record.date || "Unknown"}</strong>
                                        </div>
                                        <div>
                                          <span>OBJECTION</span>
                                          <strong>{record.objection || "None recorded"}</strong>
                                        </div>
                                        <div>
                                          <span>STAKEHOLDER</span>
                                          <strong>{record.stakeholder_concern || "None recorded"}</strong>
                                        </div>
                                      </div>
                                    </details>
                                  </article>
                                );
                              })}
                            </div>
                          ) : (
                            <EmptyState
                              icon={History}
                              title="No similar deals found"
                            >
                              No historical deal cleared the similarity threshold.
                              DealMind can still use company policy, product knowledge,
                              and the current opportunity context.
                            </EmptyState>
                          )}
                        </Panel>

                        <details className="analysis-details">
                          <summary>
                            <TrendingUp size={15} />
                            <span>View additional pattern analysis</span>
                            <ChevronDown size={15} />
                          </summary>
                          <div className="two-col-panels pattern-details-grid">
                            <Panel
                              title="Objection patterns"
                              aside={<Handshake size={16} className="panel-icon" />}
                            >
                              {report.objection_patterns?.length ? (
                                report.objection_patterns.map((pattern) => (
                                  <article
                                    className="pattern-card"
                                    key={pattern.category}
                                  >
                                    <div className="pattern-card-head">
                                      <strong>{pattern.category}</strong>
                                      <span>{pattern.similar_deals_count} PAST DEALS</span>
                                    </div>
                                    <div className="pattern-rate">
                                      <strong>{Math.round(pattern.win_rate * 100)}%</strong>
                                      <span>win rate · {pattern.won_count} won / {pattern.lost_count} lost / {pattern.stalled_count} stalled</span>
                                    </div>
                                    {pattern.description && <p>{pattern.description}</p>}
                                    {pattern.winning_approaches?.length > 0 && (
                                      <div className="mini-list success-list">
                                        <strong>What worked</strong>
                                        {pattern.winning_approaches.slice(0, 2).map((item) => (
                                          <span key={item}>{item}</span>
                                        ))}
                                      </div>
                                    )}
                                  </article>
                                ))
                              ) : (
                                <EmptyState icon={History} title="No objection patterns found." />
                              )}
                            </Panel>

                            <Panel
                              title="Competitor patterns"
                              aside={<TrendingUp size={16} className="panel-icon" />}
                            >
                              {report.competitor_patterns?.length ? (
                                report.competitor_patterns.map((pattern) => (
                                  <article
                                    className="pattern-card"
                                    key={pattern.competitor_name}
                                  >
                                    <div className="pattern-card-head">
                                      <strong>{pattern.competitor_name}</strong>
                                      <span>{pattern.matchups_count} MATCHUPS</span>
                                    </div>
                                    <div className="pattern-rate">
                                      <strong>{Math.round(pattern.win_rate * 100)}%</strong>
                                      <span>head-to-head win rate · {pattern.won_count} won / {pattern.lost_count} lost</span>
                                    </div>
                                    {pattern.playbook && <p>{pattern.playbook}</p>}
                                  </article>
                                ))
                              ) : (
                                <EmptyState icon={History} title="No competitor patterns found." />
                              )}
                            </Panel>
                          </div>
                        </details>

                      </>
                    );
                  })()}
                </div>
              )}
            </>
          )}

          {activeTab === "outcome" && (
            <>
              <PageTitle
                eyebrow="MEMORY CAPTURE / 03"
                title="Record a deal outcome"
                subtitle="Capture what the buyer faced, what your team tried, and what happened next."
                right={
                  <div className="outcome-legend">
                    <OutcomeTag outcome="Won" />
                    <OutcomeTag outcome="Lost" />
                    <OutcomeTag outcome="Stalled" />
                  </div>
                }
              />
              {savedOutcome && (
                <div className="saved-banner">
                  <BadgeCheck size={19} />
                  <div>
                    <strong>
                      {savedOutcome.deal_id} · {savedOutcome.customer} recorded
                      as {savedOutcome.outcome}
                    </strong>
                    <span>
                      Retained in Hindsight. Future evaluations can recall this
                      precedent.
                    </span>
                  </div>
                  <button
                    onClick={() => setSavedOutcome(null)}
                    aria-label="Dismiss"
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
              <form onSubmit={saveOutcome} className="panel outcome-form">
                <div className="form-section-label">
                  <span>01</span>
                  <strong>Deal record</strong>
                  <small>IDENTIFICATION & RESULT</small>
                </div>
                <div className="form-grid three">
                  <Field label="Deal ID">
                    <input
                      value={outcomeForm?.id || ""}
                      onChange={(e) => updateOutcome("id", e.target.value)}
                      required
                    />
                  </Field>
                  <Field label="Customer">
                    <input
                      value={outcomeForm?.customer || ""}
                      onChange={(e) =>
                        updateOutcome("customer", e.target.value)
                      }
                      required
                    />
                  </Field>
                  <Field label="Outcome">
                    <select
                      value={outcomeForm?.outcome || "Won"}
                      onChange={(e) => updateOutcome("outcome", e.target.value)}
                    >
                      {["Won", "Lost", "Stalled"].map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Industry">
                    <select
                      value={outcomeForm?.industry || ""}
                      onChange={(e) =>
                        updateOutcome("industry", e.target.value)
                      }
                    >
                      {bootstrap.industries.map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Product">
                    <select
                      value={outcomeForm?.product || ""}
                      onChange={(e) => updateOutcome("product", e.target.value)}
                    >
                      {bootstrap.products.map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Final value (USD)">
                    <input
                      type="number"
                      min="0"
                      step="5000"
                      value={outcomeForm?.value || 0}
                      onChange={(e) =>
                        updateOutcome("value", Number(e.target.value))
                      }
                    />
                  </Field>
                  <Field label="Final stage">
                    <select
                      value={outcomeForm?.stage || ""}
                      onChange={(e) => updateOutcome("stage", e.target.value)}
                    >
                      {bootstrap.stages.map((item) => (
                        <option key={item}>{item}</option>
                      ))}
                    </select>
                  </Field>
                  <Field label="Competitor">
                    <input
                      value={outcomeForm?.competitor || ""}
                      onChange={(e) =>
                        updateOutcome("competitor", e.target.value)
                      }
                    />
                  </Field>
                  <Field label="Closing date">
                    <input
                      type="date"
                      value={outcomeForm?.date || ""}
                      onChange={(e) => updateOutcome("date", e.target.value)}
                    />
                  </Field>
                </div>
                <div className="form-section-label separated">
                  <span>02</span>
                  <strong>Customer context</strong>
                  <small>BUYER SIGNALS</small>
                </div>
                <div className="form-grid two">
                  <Field label="Customer's final objection">
                    <textarea
                      rows="3"
                      value={outcomeForm?.objection || ""}
                      onChange={(e) =>
                        updateOutcome("objection", e.target.value)
                      }
                    />
                  </Field>
                  <Field label="Stakeholder concern">
                    <textarea
                      rows="3"
                      value={outcomeForm?.stakeholder_concern || ""}
                      onChange={(e) =>
                        updateOutcome("stakeholder_concern", e.target.value)
                      }
                    />
                  </Field>
                  <Field label="Final pricing terms">
                    <textarea
                      rows="3"
                      value={outcomeForm?.pricing_discussion || ""}
                      onChange={(e) =>
                        updateOutcome("pricing_discussion", e.target.value)
                      }
                    />
                  </Field>
                  <Field label="Outcome reason">
                    <textarea
                      rows="3"
                      value={outcomeForm?.outcome_reason || ""}
                      onChange={(e) =>
                        updateOutcome("outcome_reason", e.target.value)
                      }
                      placeholder="Why did the deal win, lose, or stall?"
                    />
                  </Field>
                </div>
                <div className="form-section-label separated">
                  <span>03</span>
                  <strong>Sales response</strong>
                  <small>WHAT YOUR TEAM DID</small>
                </div>
                <Field label="Sales approach used">
                  <textarea
                    rows="3"
                    value={outcomeForm?.approach || ""}
                    onChange={(e) => updateOutcome("approach", e.target.value)}
                    placeholder="The strategy or tactic your team executed"
                  />
                </Field>
                <div className="form-submit-row">
                  <span>
                    <Database size={15} /> Saving retains this deal as a future
                    precedent.
                  </span>
                  <Button
                    icon={busy === "outcome" ? LoaderCircle : Check}
                    variant="dark"
                    type="submit"
                    disabled={!configReady || busy === "outcome"}
                  >
                    {busy === "outcome"
                      ? "Saving memory..."
                      : "Save outcome to Hindsight"}
                  </Button>
                </div>
              </form>
            </>
          )}

          {activeTab === "loop" && (
            <>
              <PageTitle
                eyebrow="CONTINUOUS LEARNING / 04"
                title="Verify the learning loop"
                subtitle="Save one completed deal, then test whether a similar future opportunity recalls it."
                right={
                  <span className="loop-indicator">
                    <Activity size={16} /> END-TO-END CHECK
                  </span>
                }
              />
              <div className="loop-flow">
                <div>
                  <span>01</span>
                  <strong>Retain an outcome</strong>
                </div>
                <ArrowRight size={17} />
                <div>
                  <span>02</span>
                  <strong>Query a future deal</strong>
                </div>
                <ArrowRight size={17} />
                <div>
                  <span>03</span>
                  <strong>Verify recalled evidence</strong>
                </div>
                <ArrowRight size={17} />
                <div>
                  <span>04</span>
                  <strong>Inspect the playbook</strong>
                </div>
              </div>
              <form onSubmit={runLoop} className="loop-form">
                <Panel
                  title="Completed deal A"
                  aside={<span className="section-count">NEW MEMORY</span>}
                >
                  <div className="form-grid two">
                    <Field label="Deal ID">
                      <input
                        value={loopForm?.recorded_outcome.id || ""}
                        onChange={(e) =>
                          updateLoop("recorded_outcome", "id", e.target.value)
                        }
                      />
                    </Field>
                    <Field label="Customer">
                      <input
                        value={loopForm?.recorded_outcome.customer || ""}
                        onChange={(e) =>
                          updateLoop(
                            "recorded_outcome",
                            "customer",
                            e.target.value,
                          )
                        }
                      />
                    </Field>
                    <Field label="Outcome">
                      <select
                        value={loopForm?.recorded_outcome.outcome || "Won"}
                        onChange={(e) =>
                          updateLoop(
                            "recorded_outcome",
                            "outcome",
                            e.target.value,
                          )
                        }
                      >
                        {["Won", "Lost", "Stalled"].map((item) => (
                          <option key={item}>{item}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Competitor">
                      <input
                        value={loopForm?.recorded_outcome.competitor || ""}
                        onChange={(e) =>
                          updateLoop(
                            "recorded_outcome",
                            "competitor",
                            e.target.value,
                          )
                        }
                      />
                    </Field>
                    <Field label="Objection">
                      <input
                        value={loopForm?.recorded_outcome.objection || ""}
                        onChange={(e) =>
                          updateLoop(
                            "recorded_outcome",
                            "objection",
                            e.target.value,
                          )
                        }
                      />
                    </Field>
                    <Field label="Sales approach">
                      <input
                        value={loopForm?.recorded_outcome.approach || ""}
                        onChange={(e) =>
                          updateLoop(
                            "recorded_outcome",
                            "approach",
                            e.target.value,
                          )
                        }
                      />
                    </Field>
                    <Field label="Outcome reason" className="span-two">
                      <textarea
                        rows="2"
                        value={loopForm?.recorded_outcome.outcome_reason || ""}
                        onChange={(e) =>
                          updateLoop(
                            "recorded_outcome",
                            "outcome_reason",
                            e.target.value,
                          )
                        }
                      />
                    </Field>
                  </div>
                </Panel>
                <Panel
                  title="Future deal B"
                  aside={<span className="section-count">RECALL TEST</span>}
                >
                  <div className="form-grid two">
                    <Field label="Customer">
                      <input
                        value={loopForm?.future_deal.customer || ""}
                        onChange={(e) =>
                          updateLoop("future_deal", "customer", e.target.value)
                        }
                      />
                    </Field>
                    <Field label="Industry">
                      <select
                        value={loopForm?.future_deal.industry || ""}
                        onChange={(e) =>
                          updateLoop("future_deal", "industry", e.target.value)
                        }
                      >
                        {bootstrap.industries.map((item) => (
                          <option key={item}>{item}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Product">
                      <select
                        value={loopForm?.future_deal.product || ""}
                        onChange={(e) =>
                          updateLoop("future_deal", "product", e.target.value)
                        }
                      >
                        {bootstrap.products.map((item) => (
                          <option key={item}>{item}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Competitor">
                      <input
                        value={loopForm?.future_deal.competitor || ""}
                        onChange={(e) =>
                          updateLoop(
                            "future_deal",
                            "competitor",
                            e.target.value,
                          )
                        }
                      />
                    </Field>
                    <Field label="Objection">
                      <input
                        value={loopForm?.future_deal.objection || ""}
                        onChange={(e) =>
                          updateLoop("future_deal", "objection", e.target.value)
                        }
                      />
                    </Field>
                    <Field label="Deal stage">
                      <select
                        value={loopForm?.future_deal.stage || ""}
                        onChange={(e) =>
                          updateLoop("future_deal", "stage", e.target.value)
                        }
                      >
                        {bootstrap.stages.map((item) => (
                          <option key={item}>{item}</option>
                        ))}
                      </select>
                    </Field>
                  </div>
                </Panel>
                <div className="loop-submit">
                  <span>
                    <ShieldCheck size={16} /> Runs retain → recall →
                    recommendation against the configured bank.
                  </span>
                  <Button
                    icon={busy === "loop" ? LoaderCircle : FlaskConical}
                    variant="dark"
                    type="submit"
                    disabled={!configReady || busy === "loop"}
                  >
                    {busy === "loop"
                      ? "Running verification..."
                      : "Run end-to-end test"}
                  </Button>
                </div>
              </form>
              {loopReport && (
                <Panel
                  className={`loop-results ${loopReport.recalled_in_future_deal ? "loop-pass" : "loop-pending"}`}
                  title={
                    loopReport.recalled_in_future_deal
                      ? "Learning loop confirmed"
                      : "Outcome retained, recall not confirmed yet"
                  }
                  aside={
                    loopReport.recalled_in_future_deal ? (
                      <BadgeCheck size={20} />
                    ) : (
                      <AlertTriangle size={19} />
                    )
                  }
                >
                  <div className="loop-result-summary">
                    <div>
                      <span>SAVED DEAL</span>
                      <strong>{loopReport.saved_customer}</strong>
                      <small>
                        {loopReport.saved_deal_id} · {loopReport.saved_outcome}
                      </small>
                    </div>
                    <ArrowRight size={19} />
                    <div>
                      <span>FUTURE DEAL</span>
                      <strong>{loopReport.future_customer}</strong>
                      <small>
                        {loopReport.total_recalled_memories} memories recalled
                      </small>
                    </div>
                    <div className="loop-primary">
                      <span>PRIMARY ACTION</span>
                      <strong>
                        {
                          loopReport.intelligence_report.recommendations?.[0]
                            ?.headline
                        }
                      </strong>
                      <small>
                        Risk:{" "}
                        {loopReport.intelligence_report.risk_analysis?.level}
                      </small>
                    </div>
                  </div>
                  <div className="evidence-ids">
                    <span>RECALLED DEAL IDS</span>
                    {loopReport.recalled_evidence_ids?.length ? (
                      loopReport.recalled_evidence_ids.map((id) => (
                        <code key={id}>{id}</code>
                      ))
                    ) : (
                      <small>
                        No deal IDs attributed yet. Hindsight may still be
                        processing the retained memory.
                      </small>
                    )}
                  </div>
                </Panel>
              )}
            </>
          )}

          {activeTab === "chat" && (
            <>
              <PageTitle
                eyebrow="MEMORY ASSISTANT / 05"
                title="Ask DealMind"
                subtitle="Converse with deal history. Each answer includes the memories recalled to support it."
                right={
                  <span className="chat-status">
                    <span /> GROUNDED IN MEMORY
                  </span>
                }
              />
              <div className="chat-layout">
                <section className="chat-main panel">
                  <div className="chat-topline">
                    <div className="assistant-avatar">
                      <Bot size={18} />
                    </div>
                    <div>
                      <strong>DealMind Assistant</strong>
                      <span>Connected to {bootstrap.config.bank_id}</span>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => setChatHistory([])}
                    >
                      Clear conversation
                    </button>
                  </div>
                  <div className="chat-messages">
                    {chatHistory.length === 0 && (
                      <div className="chat-welcome">
                        <div className="welcome-glyph">
                          <BrainCircuit size={25} />
                        </div>
                        <h2>What should you learn from the last deal?</h2>
                        <p>
                          Ask about a competitor, objection, or customer
                          outcome.
                        </p>
                        <div className="prompt-chips">
                          {QUICK_PROMPTS.map((prompt) => (
                            <button
                              key={prompt}
                              onClick={() => sendChat(prompt)}
                              disabled={!configReady || Boolean(busy)}
                            >
                              <span>{prompt}</span>
                              <ArrowRight size={14} />
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {chatHistory.map((message, index) => (
                      <article
                        className={`chat-message message-${message.role}`}
                        key={`${message.role}-${index}`}
                      >
                        <div className="message-avatar">
                          {message.role === "user" ? (
                            "YOU"
                          ) : (
                            <BrainCircuit size={15} />
                          )}
                        </div>
                        <div className="message-content">
                          {message.role === "user" ? (
                            <p>{message.content}</p>
                          ) : (
                            <>
                              <div className="markdown-answer">
                                <ReactMarkdown>{message.answer}</ReactMarkdown>
                              </div>
                              <details className="chat-recall">
                                <summary>
                                  <Database size={14} />{" "}
                                  {message.recalled_memories?.length || 0}{" "}
                                  memories recalled <ChevronDown size={14} />
                                </summary>
                                <div>
                                  <p className="recall-query">
                                    QUERY · {message.query_sent}
                                  </p>
                                  <MemoryList
                                    memories={message.recalled_memories || []}
                                  />
                                </div>
                              </details>
                            </>
                          )}
                        </div>
                      </article>
                    ))}
                    {busy === "chat" && (
                      <div className="chat-loading">
                        <LoaderCircle size={16} className="spin" /> Searching
                        Hindsight memory...
                      </div>
                    )}
                  </div>
                  <form
                    className="chat-compose"
                    onSubmit={(event) => {
                      event.preventDefault();
                      sendChat();
                    }}
                  >
                    <input
                      value={chatInput}
                      onChange={(event) => setChatInput(event.target.value)}
                      placeholder="Ask about a deal, competitor, or playbook..."
                      aria-label="Chat message"
                      disabled={!configReady}
                    />
                    <button
                      type="submit"
                      aria-label="Send message"
                      disabled={
                        !configReady || !chatInput.trim() || busy === "chat"
                      }
                    >
                      <Send size={17} />
                    </button>
                  </form>
                </section>
                <aside className="chat-side">
                  <Panel title="Active deal" className="active-deal-panel">
                    <span className="active-customer">
                      {deal?.customer || "No customer selected"}
                    </span>
                    <div>
                      <span>INDUSTRY</span>
                      <strong>{deal?.industry}</strong>
                    </div>
                    <div>
                      <span>COMPETITOR</span>
                      <strong>{deal?.competitor || "None"}</strong>
                    </div>
                    <div>
                      <span>STAGE</span>
                      <strong>{deal?.stage}</strong>
                    </div>
                    <div>
                      <span>OBJECTION</span>
                      <strong>{deal?.objection || "None"}</strong>
                    </div>
                    <Button
                      icon={Target}
                      onClick={() => setActiveTab("intelligence")}
                    >
                      Edit deal context
                    </Button>
                  </Panel>
                  <div className="chat-evidence-note">
                    <BookOpen size={16} />
                    <strong>Evidence stays visible</strong>
                    <p>
                      Expand a response's recall details to see the facts
                      DealMind used.
                    </p>
                  </div>
                </aside>
              </div>
              {!configReady && (
                <div className="inline-warning">
                  <AlertTriangle size={16} /> Configure Hindsight to use chat
                  and live memory recall.
                </div>
              )}
            </>
          )}
        </div>
        <footer className="app-footer">
          <span>
            DEALMIND <i>·</i> DEAL INTELLIGENCE
          </span>
          <span>Historical evidence, not guesswork.</span>
        </footer>
      </main>
    </div>
  );
}

function TACTICS_LABEL(bootstrap, tactic) {
  return bootstrap.tactics[tactic]?.label || tactic;
}

function DEMO_SAVED_LABEL(saved) {
  return saved?.["1"]?.outcome || "recorded";
}

function createOutcomeForm(deal, count) {
  return {
    ...deal,
    id: `D-${String(count + 1).padStart(3, "0")}`,
    approach: "Presented a 3-year TCO model and engaged an executive sponsor.",
    outcome: "Won",
    outcome_reason: "",
    date: new Date().toISOString().slice(0, 10),
  };
}

function createLoopForm(deal) {
  return {
    recorded_outcome: {
      id: "D-099",
      customer: "Vanguard Freight Logistics",
      industry: "Logistics",
      product: "Enterprise Platform",
      value: 160000,
      stage: "Negotiation",
      competitor: "FreightIQ",
      objection: "FreightIQ is cheaper by 20%",
      stakeholder_concern: "Operations fears disruption",
      pricing_discussion: "Buyer asked for discount",
      approach: "TCO model showing hidden integration fees + reference call",
      outcome: "Won",
      outcome_reason:
        "Customer realized FreightIQ add-ons made it more expensive; signed list price",
    },
    future_deal: {
      customer: "Pacific Fleet Transport",
      industry: "Logistics",
      product: "Enterprise Platform",
      value: 155000,
      stage: "Negotiation",
      competitor: "FreightIQ",
      objection: "Buyer claims FreightIQ quote is 20% lower",
      stakeholder_concern: "Wants fast go-live",
      pricing_discussion: "Buyer pushing to match FreightIQ",
    },
  };
}

export default App;
