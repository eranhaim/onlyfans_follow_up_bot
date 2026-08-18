import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, Conversation, DashboardStats } from "./api";

export default function DashboardTab() {
  const { t, i18n } = useTranslation();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState("");

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

  async function optIn(id: number) {
    await api.optIn(id);
    await load();
  }

  async function skipStep(id: number) {
    await api.skipStep(id);
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
                    {c.opted_out ? (
                      <button className="btn" onClick={() => void optIn(c.id)}>
                        {t("dashboard.optIn")}
                      </button>
                    ) : (
                      <>
                        <button className="btn secondary" onClick={() => void skipStep(c.id)}>
                          {t("dashboard.skipStep")}
                        </button>
                        <button className="btn danger" onClick={() => void optOut(c.id)}>
                          {t("dashboard.optOut")}
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {conversations.length === 0 && <p className="muted">{t("dashboard.noConversations")}</p>}
      </div>
    </div>
  );
}
