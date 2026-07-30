import { useState } from "react";
import { useTranslation } from "react-i18next";
import { clearToken, getToken } from "./api";
import LanguageSwitcher from "./components/LanguageSwitcher";
import DashboardTab from "./DashboardTab";
import Login from "./Login";
import ModelTab from "./ModelTab";
import SimulatorTab from "./SimulatorTab";
import StagesTab from "./StagesTab";
import TelegramTab from "./TelegramTab";

type Tab = "dashboard" | "stages" | "videos" | "telegram" | "simulator";

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
        <button className={`tab ${tab === "stages" ? "active" : ""}`} onClick={() => setTab("stages")}>
          {t("tabs.stages")}
        </button>
        <button className={`tab ${tab === "videos" ? "active" : ""}`} onClick={() => setTab("videos")}>
          {t("tabs.model")}
        </button>
        <button className={`tab ${tab === "telegram" ? "active" : ""}`} onClick={() => setTab("telegram")}>
          {t("tabs.telegram")}
        </button>
        <button className={`tab ${tab === "simulator" ? "active" : ""}`} onClick={() => setTab("simulator")}>
          {t("tabs.simulator")}
        </button>
      </div>

      {tab === "dashboard" && <DashboardTab />}
      {tab === "stages" && <StagesTab />}
      {tab === "videos" && <ModelTab />}
      {tab === "telegram" && <TelegramTab />}
      {tab === "simulator" && <SimulatorTab />}
    </div>
  );
}
