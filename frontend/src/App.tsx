import { useState } from "react";
import { clearToken, getToken } from "./api";
import DashboardTab from "./DashboardTab";
import Login from "./Login";
import MessagesTab from "./MessagesTab";
import TelegramTab from "./TelegramTab";

type Tab = "dashboard" | "messages" | "telegram";

export default function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [tab, setTab] = useState<Tab>("dashboard");

  if (!authed) {
    return <Login onSuccess={() => setAuthed(true)} />;
  }

  return (
    <div className="app-shell">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h1 style={{ margin: 0 }}>Follow-Up Bot</h1>
        <button
          className="btn secondary"
          onClick={() => {
            clearToken();
            setAuthed(false);
          }}
        >
          Log out
        </button>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === "dashboard" ? "active" : ""}`} onClick={() => setTab("dashboard")}>
          Dashboard
        </button>
        <button className={`tab ${tab === "messages" ? "active" : ""}`} onClick={() => setTab("messages")}>
          Messages
        </button>
        <button className={`tab ${tab === "telegram" ? "active" : ""}`} onClick={() => setTab("telegram")}>
          Telegram
        </button>
      </div>

      {tab === "dashboard" && <DashboardTab />}
      {tab === "messages" && <MessagesTab />}
      {tab === "telegram" && <TelegramTab />}
    </div>
  );
}
