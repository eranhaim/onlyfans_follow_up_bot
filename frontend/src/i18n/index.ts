import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import he from "./locales/he.json";

export const LANG_STORAGE_KEY = "followup_lang";

export type AppLanguage = "he" | "en";

function readStoredLanguage(): AppLanguage {
  const stored = localStorage.getItem(LANG_STORAGE_KEY);
  return stored === "en" ? "en" : "he";
}

function applyDocumentLanguage(lng: AppLanguage) {
  document.documentElement.lang = lng;
  document.documentElement.dir = lng === "he" ? "rtl" : "ltr";
}

const initialLanguage = readStoredLanguage();
applyDocumentLanguage(initialLanguage);

void i18n.use(initReactI18next).init({
  resources: {
    he: { translation: he },
    en: { translation: en },
  },
  lng: initialLanguage,
  fallbackLng: "he",
  interpolation: { escapeValue: false },
});

i18n.on("languageChanged", (lng) => {
  const lang: AppLanguage = lng === "en" ? "en" : "he";
  localStorage.setItem(LANG_STORAGE_KEY, lang);
  applyDocumentLanguage(lang);
});

export default i18n;
