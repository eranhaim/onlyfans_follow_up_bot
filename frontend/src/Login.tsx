import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, setToken } from "./api";
import LanguageSwitcher from "./components/LanguageSwitcher";

export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const { t } = useTranslation();
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { token } = await api.login(password);
      setToken(token);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("auth.loginFailed"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-top">
        <LanguageSwitcher />
      </div>
      <form className="card login-card" onSubmit={submit}>
        <h1>{t("app.title")}</h1>
        <p className="muted">{t("auth.subtitle")}</p>
        <div className="field">
          <label htmlFor="password">{t("auth.password")}</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
          />
        </div>
        {error && <div className="error">{error}</div>}
        <button className="btn" type="submit" disabled={loading}>
          {loading ? t("auth.signingIn") : t("auth.signIn")}
        </button>
      </form>
    </div>
  );
}
