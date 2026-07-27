import { FormEvent, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, simulator, SimState, SimMessage, TelegramAccount } from "./api";

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

export default function SimulatorTab() {
  const { t } = useTranslation();
  const [accounts, setAccounts] = useState<TelegramAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [session, setSession] = useState<SimState | null>(null);
  const [userInput, setUserInput] = useState("");
  const [advanceHours, setAdvanceHours] = useState("24");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listTelegramAccounts().then((accs) => {
      setAccounts(accs);
      if (accs.length > 0) setSelectedAccountId(accs[0].id);
    }).catch(() => setError(t("common.error")));
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages]);

  async function startSession() {
    if (selectedAccountId === null) return;
    setError("");
    setLoading(true);
    try {
      const state = await simulator.start(selectedAccountId);
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

  const simTimeLabel = session
    ? new Date(session.sim_now).toLocaleString([], { dateStyle: "short", timeStyle: "short" })
    : null;

  const activeStages = session?.stages.filter((s) => s.is_active) ?? [];
  const totalActive = activeStages.length;

  return (
    <div className="card" style={{ maxWidth: 700 }}>
      <h2>{t("simulator.title")}</h2>

      {/* Account selector + controls */}
      <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        <select
          value={selectedAccountId ?? ""}
          onChange={(e) => setSelectedAccountId(Number(e.target.value))}
          disabled={!!session}
          style={{ flex: 1 }}
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}{a.phone ? ` (${a.phone})` : ""}
            </option>
          ))}
        </select>
        {!session ? (
          <button className="btn primary" onClick={startSession} disabled={loading || selectedAccountId === null}>
            {loading ? t("common.loading") : t("simulator.start")}
          </button>
        ) : (
          <button className="btn secondary" onClick={resetSession}>
            {t("simulator.reset")}
          </button>
        )}
      </div>

      {error && <p style={{ color: "#f44", marginBottom: 8 }}>{error}</p>}

      {session && (
        <>
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
              <span>
                {t("simulator.nextIn", { hours: session.hours_until_next })}
              </span>
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
            {[1, 6, 24, 48].map((h) => (
              <button
                key={h}
                className="btn secondary"
                style={{ padding: "4px 10px", fontSize: 13 }}
                onClick={() => advanceTime(h)}
                disabled={loading}
              >
                +{h}h
              </button>
            ))}
            <input
              type="number"
              min="0.1"
              step="0.5"
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
          </div>
        </>
      )}
    </div>
  );
}
