import { FormEvent, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, simulator, SimState, SimMessage, SimConversation, TelegramAccount } from "./api";

// ---- Sub-components ----

function StageProgressBar({ stages, stepsCompleted }: { stages: SimState["stages"]; stepsCompleted: number }) {
  const active = stages.filter((s) => s.is_active);
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "12px 0" }}>
      {active.map((stage, i) => {
        const done = i < stepsCompleted;
        const current = i === stepsCompleted;
        return (
          <div
            key={stage.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              padding: "4px 10px",
              borderRadius: 20,
              fontSize: 13,
              background: done ? "#1a3a1a" : current ? "#1e3a5f" : "#1e2230",
              border: `1px solid ${done ? "#2d6a2d" : current ? "#2a5298" : "#2a2f3d"}`,
              color: done ? "#4caf50" : current ? "#7eb8f7" : "#666",
              fontWeight: current ? 600 : 400,
            }}
          >
            {done ? "✓" : current ? "▶" : "○"}
            <span>Stage {i + 1}</span>
            <span style={{ opacity: 0.6, fontSize: 11 }}>{stage.delay_hours}h</span>
          </div>
        );
      })}
    </div>
  );
}

function ChatBubble({ msg }: { msg: SimMessage }) {
  const isUser = msg.role === "user";
  const time = new Date(msg.sim_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
        maxWidth: "75%",
        alignSelf: isUser ? "flex-end" : "flex-start",
      }}
    >
      {!isUser && msg.stage_position !== null && (
        <span style={{ fontSize: 11, color: "#7eb8f7", marginBottom: 2 }}>
          Stage {(msg.stage_position ?? 0) + 1}
          {msg.video_filename && <span style={{ marginLeft: 6 }}>🎬 {msg.video_filename}</span>}
        </span>
      )}
      <div
        style={{
          padding: "8px 12px",
          borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isUser ? "#2a2f3d" : "#1e3a5f",
          color: "#e8eaed",
          fontSize: 14,
          lineHeight: 1.5,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {msg.content}
      </div>
      <span style={{ fontSize: 11, color: "#555", marginTop: 2 }}>{time}</span>
    </div>
  );
}

// ---- Main Component ----

type DebugInfo = {
  // LangGraph mode
  analysis?: { tone?: string; entry_point?: string; angle?: string; avoid?: string; language?: string };
  attempts?: string[];
  retry_count?: number;
  last_validation?: { pass?: boolean; reason?: string };
  final_message?: string;
  // Fallback mode
  system_prompt?: string;
  chat_history?: { role: string; content: string }[];
  raw_response?: string;
};

export default function SimulatorTab() {
  const { t } = useTranslation();
  const [accounts, setAccounts] = useState<TelegramAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [conversations, setConversations] = useState<SimConversation[]>([]);
  const [selectedConvId, setSelectedConvId] = useState<number | "new" | null>(null);
  const [session, setSession] = useState<SimState | null>(null);
  const [userInput, setUserInput] = useState("");
  const [advanceHours, setAdvanceHours] = useState("24");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [debugInfo, setDebugInfo] = useState<DebugInfo | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listTelegramAccounts().then((accs) => {
      setAccounts(accs);
      if (accs.length > 0) setSelectedAccountId(accs[0].id);
    }).catch(() => setError(t("common.error")));
  }, []);

  useEffect(() => {
    simulator.listConversations()
      .then(setConversations)
      .catch(() => {});
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages]);

  // Auto-start session when fan selected
  useEffect(() => {
    if (selectedAccountId !== null && selectedConvId !== null && !session && !loading) {
      void startSession();
    }
  }, [selectedConvId]);

  async function startSession() {
    if (selectedAccountId === null || selectedConvId === null) return;
    setError("");
    setLoading(true);
    try {
      const convId = selectedConvId === "new" ? undefined : selectedConvId;
      const state = await simulator.start(selectedAccountId, convId);
      setSession(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(false);
    }
  }

  async function resetSession() {
    if (session) {
      await simulator.deleteSession(session.session_id).catch(() => {});
    }
    setSession(null);
    setUserInput("");
    setError("");
  }

  async function sendMessage(e: FormEvent) {
    e.preventDefault();
    if (!session || !userInput.trim()) return;
    setError("");
    setLoading(true);
    try {
      const state = await simulator.sendMessage(session.session_id, userInput.trim());
      setSession(state);
      setUserInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(false);
    }
  }

  async function advanceTime(hours: number) {
    if (!session) return;
    setError("");
    setLoading(true);
    try {
      const state = await simulator.advance(session.session_id, hours);
      setSession(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setLoading(false);
    }
  }

  async function showDebug() {
    try {
      const info = await simulator.getLastDebug();
      setDebugInfo(info as DebugInfo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No debug info yet — trigger a bot message first");
    }
  }

  const simTimeLabel = session
    ? new Date(session.sim_now).toLocaleString([], { dateStyle: "short", timeStyle: "short" })
    : null;

  const activeStages = session?.stages.filter((s) => s.is_active) ?? [];
  const totalActive = activeStages.length;

  return (
    <div className="card" style={{ maxWidth: 700 }}>
      <h2>{t("simulator.title")}</h2>

      {/* Account + conversation selector */}
      {!session && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 12 }}>
          <div className="field" style={{ margin: 0 }}>
            <label>{t("simulator.selectModel")}</label>
            <select
              value={selectedAccountId ?? ""}
              onChange={(e) => { setSelectedAccountId(Number(e.target.value)); setSelectedConvId(null); }}
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}{a.phone ? ` (${a.phone})` : ""}
                </option>
              ))}
            </select>
          </div>

          <div className="field" style={{ margin: 0 }}>
            <label>{t("simulator.selectFan")}</label>
            <select
              value={selectedConvId ?? ""}
              onChange={(e) => {
                const val = e.target.value === "new" ? "new" as const : Number(e.target.value);
                setSelectedConvId(val);
              }}
            >
              <option value="">{t("simulator.chooseFan")}</option>
              <option value="new">➕ {t("simulator.newFan")}</option>
              {conversations
                .filter((c) => selectedAccountId === null || c.account_id === selectedAccountId)
                .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.display_name}
                </option>
              ))}
            </select>
          </div>

          {loading && <p className="muted">{t("common.loading")}</p>}
        </div>
      )}

      {error && <p style={{ color: "#f44", marginBottom: 8 }}>{error}</p>}

      {session && (
        <>
          {/* Header */}
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <div style={{ fontSize: 13, color: "#aaa" }}>
              {session.fan_display_name && (
                <span style={{ color: "#7eb8f7", fontWeight: 600, marginRight: 8 }}>
                  👤 {session.fan_display_name}
                </span>
              )}
              {session.fan_profile?.personality_type && (
                <span style={{ color: "#888" }}>· {typeof session.fan_profile.personality_type === "string" ? session.fan_profile.personality_type : JSON.stringify(session.fan_profile.personality_type)}</span>
              )}
            </div>
            <button className="btn secondary" onClick={resetSession} style={{ padding: "4px 12px" }}>
              {t("simulator.reset")}
            </button>
          </div>

          {/* Status bar */}
          <div
            style={{
              display: "flex",
              gap: 16,
              flexWrap: "wrap",
              fontSize: 13,
              color: "#aaa",
              marginBottom: 4,
              padding: "6px 10px",
              background: "#1a1d28",
              borderRadius: 8,
            }}
          >
            <span>🕐 {simTimeLabel}</span>
            <span>
              {t("simulator.stageOf", { current: Math.min(session.steps_sent + 1, totalActive), total: totalActive })}
            </span>
            {session.sequence_complete ? (
              <span style={{ color: "#4caf50" }}>✓ {t("simulator.complete")}</span>
            ) : session.hours_until_next !== null ? (
              <span>{t("simulator.nextIn", { hours: session.hours_until_next })}</span>
            ) : (
              <span style={{ color: "#666" }}>{t("simulator.sendFirstMessage")}</span>
            )}
          </div>

          {/* Stage progress */}
          <StageProgressBar stages={session.stages} stepsCompleted={session.steps_sent} />

          {/* Chat window */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 10,
              overflowY: "auto",
              maxHeight: 420,
              padding: 12,
              background: "#12141f",
              borderRadius: 10,
              border: "1px solid #2a2f3d",
              marginBottom: 12,
            }}
          >
            {session.messages.length === 0 && (
              <p style={{ color: "#555", margin: "auto", fontSize: 13 }}>{t("simulator.noMessages")}</p>
            )}
            {session.messages.map((msg, i) => (
              <ChatBubble key={i} msg={msg} />
            ))}
            <div ref={chatEndRef} />
          </div>

          {/* User input */}
          <form onSubmit={sendMessage} style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <input
              type="text"
              placeholder={t("simulator.inputPlaceholder")}
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              disabled={loading}
              style={{ flex: 1 }}
            />
            <button className="btn primary" type="submit" disabled={loading || !userInput.trim()}>
              {t("simulator.send")}
            </button>
          </form>

          {/* Fast-forward */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontSize: 13, color: "#aaa" }}>{t("simulator.fastForward")}:</span>
            {[
              { label: "5m", hours: 5 / 60 },
              { label: "15m", hours: 15 / 60 },
              { label: "1h", hours: 1 },
              { label: "6h", hours: 6 },
              { label: "24h", hours: 24 },
              { label: "48h", hours: 48 },
            ].map((item) => (
              <button
                key={item.label}
                className="btn secondary"
                style={{ padding: "4px 10px", fontSize: 13 }}
                onClick={() => advanceTime(item.hours)}
                disabled={loading}
              >
                +{item.label}
              </button>
            ))}
            <input
              type="number"
              min="0.01"
              step="0.1"
              value={advanceHours}
              onChange={(e) => setAdvanceHours(e.target.value)}
              disabled={loading}
              style={{ width: 70 }}
            />
            <button
              className="btn secondary"
              onClick={() => advanceTime(Number(advanceHours))}
              disabled={loading || !advanceHours}
            >
              +{advanceHours}h
            </button>
            <button
              className="btn secondary"
              onClick={showDebug}
              style={{ padding: "4px 10px", fontSize: 13, marginLeft: "auto", color: "#f0b429" }}
            >
              🔍 Debug
            </button>
          </div>

          {/* Debug modal */}
          {debugInfo && (
            <div
              style={{
                position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
                display: "flex", alignItems: "center", justifyContent: "center",
                zIndex: 1000,
              }}
              onClick={() => setDebugInfo(null)}
            >
              <div
                style={{
                  background: "#1a1d28", border: "1px solid #2a2f3d", borderRadius: 12,
                  padding: 20, maxWidth: 700, width: "90%", maxHeight: "80vh",
                  overflowY: "auto", fontFamily: "monospace", fontSize: 12,
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
                  <strong style={{ color: "#f0b429" }}>🔍 LangGraph Debug</strong>
                  <button className="btn secondary" onClick={() => setDebugInfo(null)} style={{ padding: "2px 10px" }}>✕</button>
                </div>

                {debugInfo.analysis && typeof debugInfo.analysis === "object" && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ color: "#7eb8f7", marginBottom: 6 }}>① ANALYZE</div>
                    <div style={{ background: "#12141f", padding: 10, borderRadius: 6 }}>
                      {Object.entries(debugInfo.analysis).map(([k, v]) => (
                        <div key={k} style={{ marginBottom: 3 }}>
                          <span style={{ color: "#888" }}>{k}: </span>
                          <span style={{ color: "#ccc" }}>{String(v ?? "")}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {Array.isArray(debugInfo.attempts) && debugInfo.attempts.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ color: "#7eb8f7", marginBottom: 6 }}>② GENERATE ({debugInfo.retry_count ?? debugInfo.attempts.length} attempt{debugInfo.attempts.length !== 1 ? "s" : ""})</div>
                    {debugInfo.attempts.map((a, i) => (
                      <div key={i} style={{ background: "#12141f", padding: 10, borderRadius: 6, marginBottom: 6 }}>
                        <div style={{ color: "#666", fontSize: 11, marginBottom: 4 }}>Attempt {i + 1}</div>
                        <div style={{ color: "#ccc" }}>{String(a ?? "")}</div>
                      </div>
                    ))}
                  </div>
                )}

                {debugInfo.last_validation && typeof debugInfo.last_validation === "object" && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ color: "#7eb8f7", marginBottom: 6 }}>③ VALIDATE</div>
                    <div style={{ background: "#12141f", padding: 10, borderRadius: 6 }}>
                      <span style={{ color: debugInfo.last_validation.pass ? "#4caf50" : "#f44" }}>
                        {debugInfo.last_validation.pass ? "✓ PASSED" : "✗ FAILED"}
                      </span>
                      {debugInfo.last_validation.reason && (
                        <span style={{ color: "#888", marginLeft: 8 }}>{String(debugInfo.last_validation.reason)}</span>
                      )}
                    </div>
                  </div>
                )}

                {debugInfo.final_message && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ color: "#7eb8f7", marginBottom: 6 }}>④ FINAL MESSAGE</div>
                    <pre style={{ background: "#12141f", padding: 10, borderRadius: 6, whiteSpace: "pre-wrap", color: "#4caf50" }}>
                      {String(debugInfo.final_message)}
                    </pre>
                  </div>
                )}

                {/* Fallback: old debug format */}
                {debugInfo.system_prompt && (
                  <>
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ color: "#7eb8f7", marginBottom: 4 }}>SYSTEM PROMPT</div>
                      <pre style={{ background: "#12141f", padding: 10, borderRadius: 6, whiteSpace: "pre-wrap", wordBreak: "break-word", color: "#ccc" }}>
                        {String(debugInfo.system_prompt)}
                      </pre>
                    </div>
                    <div>
                      <div style={{ color: "#7eb8f7", marginBottom: 4 }}>RAW RESPONSE</div>
                      <pre style={{ background: "#12141f", padding: 10, borderRadius: 6, whiteSpace: "pre-wrap", color: "#4caf50" }}>
                        {String(debugInfo.raw_response ?? "")}
                      </pre>
                    </div>
                  </>
                )}

                {/* Empty state */}
                {!debugInfo.analysis && !debugInfo.system_prompt && !debugInfo.final_message && (
                  <div style={{ color: "#666", textAlign: "center", padding: 20 }}>
                    No debug data yet — trigger a bot follow-up first (+24h or +48h)
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
