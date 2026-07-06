import { useEffect, useState } from "react";
import { api, Conversation, DashboardStats } from "./api";

function fmt(dt: string | null) {
  if (!dt) return "—";
  return new Date(dt).toLocaleString();
}

export default function DashboardTab() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState("");

  async function load() {
    try {
      const [s, c] = await Promise.all([api.stats(), api.listConversations()]);
      setStats(s);
      setConversations(c);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);

  async function optOut(id: number) {
    await api.optOut(id);
    await load();
  }

  return (
    <div>
      {stats && (
        <div className="stats" style={{ marginBottom: 16 }}>
          <div className="stat">
            <strong>{stats.connected ? "Yes" : "No"}</strong>
            Telegram connected
          </div>
          <div className="stat">
            <strong>{stats.tracked_conversations}</strong>
            Tracked chats
          </div>
          <div className="stat">
            <strong>{stats.pending_follow_ups}</strong>
            Due now
          </div>
          <div className="stat">
            <strong>{stats.sent_last_24h}</strong>
            Sent (24h)
          </div>
        </div>
      )}

      <div className="card">
        <h2>Recent conversations</h2>
        {error && <div className="error">{error}</div>}
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Last message</th>
              <th>Steps sent</th>
              <th>Last follow-up</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {conversations.map((c) => (
              <tr key={c.id}>
                <td>
                  {c.display_name || c.telegram_user_id}
                  {c.opted_out && <span className="badge off"> opted out</span>}
                </td>
                <td>{fmt(c.last_user_message_at)}</td>
                <td>{c.steps_sent}</td>
                <td>{fmt(c.last_follow_up_at)}</td>
                <td>
                  {!c.opted_out && (
                    <button className="btn secondary" onClick={() => optOut(c.id)}>
                      Opt out
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {conversations.length === 0 && <p className="muted">No conversations tracked yet.</p>}
      </div>
    </div>
  );
}
