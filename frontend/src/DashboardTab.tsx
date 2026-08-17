import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, Conversation, DashboardStats, FanProfile } from "./api";

/** Safely render a profile value — LLM sometimes returns objects instead of strings */
function str(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function FanProfilePanel({ conversationId, onClose }: { conversationId: number; onClose: () => void }) {
  const { t } = useTranslation();
  const [profile, setProfile] = useState<FanProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.fanProfile(conversationId)
      .then(setProfile)
      .catch(() => setProfile({}))
      .finally(() => setLoading(false));
  }, [conversationId]);

  return (
    <div style={{
      position: "fixed", top: 0, left: 0, bottom: 0, width: 320,
      background: "#1a1d28", borderRight: "1px solid #2a2f3d",
      padding: 24, zIndex: 100, overflowY: "auto",
    }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 20 }}>
        <h3 style={{ margin: 0 }}>{t("dashboard.fanProfile")}</h3>
        <button className="btn secondary" style={{ padding: "2px 10px" }} onClick={onClose}>✕</button>
      </div>

      {loading ? (
        <p className="muted">{t("common.loading")}</p>
      ) : !profile || Object.keys(profile).length === 0 ? (
        <p className="muted">{t("dashboard.noProfile")}</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {profile.personality_type && (
            <div>
              <div style={{ fontSize: 11, color: "#7eb8f7", marginBottom: 4 }}>{t("dashboard.profilePersonality")}</div>
              <div style={{ color: "#e8eaed" }}>{str(profile.personality_type)}</div>
            </div>
          )}
          {profile.triggers && (
            <div>
              <div style={{ fontSize: 11, color: "#7eb8f7", marginBottom: 4 }}>{t("dashboard.profileTriggers")}</div>
              <div style={{ color: "#e8eaed" }}>{str(profile.triggers)}</div>
            </div>
          )}
          {profile.language && (
            <div>
              <div style={{ fontSize: 11, color: "#7eb8f7", marginBottom: 4 }}>{t("dashboard.profileLanguage")}</div>
              <div style={{ color: "#e8eaed" }}>{str(profile.language)}</div>
            </div>
          )}
          {profile.notes && (
            <div>
              <div style={{ fontSize: 11, color: "#7eb8f7", marginBottom: 4 }}>{t("dashboard.profileNotes")}</div>
              <div style={{ color: "#e8eaed", whiteSpace: "pre-wrap" }}>{str(profile.notes)}</div>
            </div>
          )}
          {profile.updated_at && (
            <div style={{ fontSize: 11, color: "#555", marginTop: 8 }}>
              {t("dashboard.profileUpdated")}: {new Date(profile.updated_at).toLocaleString()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function DashboardTab() {
  const { t, i18n } = useTranslation();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState("");
  const [selectedConvId, setSelectedConvId] = useState<number | null>(null);

  const dateLocale = i18n.language === "he" ? "he-IL" : "en-US";

  function fmt(dt: string | null) {
    if (!dt) return t("common.dash");
    return new Date(dt).toLocaleString(dateLocale);
  }

  async function load() {
    try {
      const [s, c] = await Promise.all([api.stats(), api.listConversations()]);
      setStats(s);
      setConversations(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("dashboard.loadFailed"));
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 30000);
    return () => clearInterval(id);
  }, []);

  async function optOut(id: number) {
    if (!confirm(t("dashboard.optOutConfirm"))) return;
    await api.optOut(id);
    await load();
  }

  return (
    <div>
      {stats && (
        <div className="stats" style={{ marginBottom: 16 }}>
          <div className="stat">
            <strong>{stats.connected ? t("common.yes") : t("common.no")}</strong>
            {t("dashboard.telegramConnected")}
          </div>
          <div className="stat">
            <strong>{stats.active_stages}</strong>
            {t("dashboard.activeStages")}
          </div>
          <div className="stat">
            <strong>{stats.tracked_conversations}</strong>
            {t("dashboard.trackedChats")}
          </div>
          <div className="stat">
            <strong>{stats.pending_follow_ups}</strong>
            {t("dashboard.dueNow")}
          </div>
          <div className="stat">
            <strong>{stats.sent_last_24h}</strong>
            {t("dashboard.sent24h")}
          </div>
        </div>
      )}

      <div className="card">
        <h2>{t("dashboard.recentConversations")}</h2>
        {error && <div className="error">{error}</div>}
        <table>
          <thead>
            <tr>
              <th>{t("dashboard.user")}</th>
              <th>{t("dashboard.lastMessage")}</th>
              <th>{t("dashboard.stepsSent")}</th>
              <th>{t("dashboard.lastFollowUp")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {conversations.map((c) => (
              <tr key={c.id}>
                <td>
                  {c.display_name || c.telegram_user_id}
                  {c.opted_out && <span className="badge off"> {t("dashboard.optedOut")}</span>}
                </td>
                <td>{fmt(c.last_user_message_at)}</td>
                <td>{c.steps_sent}</td>
                <td>{fmt(c.last_follow_up_at)}</td>
                <td>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button
                      className="btn secondary"
                      onClick={() => setSelectedConvId(c.id === selectedConvId ? null : c.id)}
                    >
                      {t("dashboard.details")}
                    </button>
                    {!c.opted_out && (
                      <button className="btn danger" onClick={() => void optOut(c.id)}>
                        {t("dashboard.optOut")}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {conversations.length === 0 && <p className="muted">{t("dashboard.noConversations")}</p>}
      </div>

      {selectedConvId !== null && (
        <FanProfilePanel
          conversationId={selectedConvId}
          onClose={() => setSelectedConvId(null)}
        />
      )}
    </div>
  );
}
