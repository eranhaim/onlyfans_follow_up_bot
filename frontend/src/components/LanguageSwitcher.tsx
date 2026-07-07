import { useTranslation } from "react-i18next";
import type { AppLanguage } from "../i18n";

export default function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const current = i18n.language === "en" ? "en" : "he";

  function setLanguage(lang: AppLanguage) {
    void i18n.changeLanguage(lang);
  }

  return (
    <div className="lang-switcher" role="group" aria-label={t("common.language")}>
      <button
        type="button"
        className={`lang-btn ${current === "he" ? "active" : ""}`}
        onClick={() => setLanguage("he")}
      >
        {t("common.hebrew")}
      </button>
      <button
        type="button"
        className={`lang-btn ${current === "en" ? "active" : ""}`}
        onClick={() => setLanguage("en")}
      >
        {t("common.english")}
      </button>
    </div>
  );
}
