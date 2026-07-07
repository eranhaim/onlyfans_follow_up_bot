import { useState } from "react";
import { useTranslation } from "react-i18next";
import { clearToken, getToken } from "./api";
import LanguageSwitcher from "./components/LanguageSwitcher";
import DashboardTab from "./DashboardTab";
import Login from "./Login";
import MessagesTab from "./MessagesTab";
import TelegramTab from "./TelegramTab";

type Tab = "dashboard" | "messages" | "telegram";

export default function App() {
  const { t } = useTranslation();
  const [authed, setAuthed] = useState(!!getToken());
  const [tab, setTab] = useState<Tab>("dashboard");

  if (!authed) {
    return <Login onSuccess={() => setAuthed(true)} />;
  }

  return (
    <div className="app-shell">
      <div className="row app-header">
        <h1 style={{ margin: 0 }}>{t("app.title")}</h1>
        <div className="row">
          <LanguageSwitcher />
          <button
            className="btn secondary"
            onClick={() => {
              clearToken();
              setAuthed(false);
            }}
          >
            {t("auth.logout")}
          </button>
        </div>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === "dashboard" ? "active" : ""}`} onClick={() => setTab("dashboard")}>
          {t("tabs.dashboard")}
        </button>
        <button className={`tab ${tab === "messages" ? "active" : ""}`} onClick={() => setTab("messages")}>
          {t("tabs.messages")}
        </button>
        <button className={`tab ${tab === "telegram" ? "active" : ""}`} onClick={() => setTab("telegram")}>
          {t("tabs.telegram")}
        </button>
      </div>

      {tab === "dashboard" && <DashboardTab />}
      {tab === "messages" && <MessagesTab />}
      {tab === "telegram" && <TelegramTab />}
    </div>
  );
}
