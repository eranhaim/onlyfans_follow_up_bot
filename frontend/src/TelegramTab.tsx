import { FormEvent, useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { api, TelegramAccount } from "./api";

export default function TelegramTab() {
  const { t, i18n } = useTranslation();
  const [connected, setConnected] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<TelegramAccount[]>([]);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [phoneCodeHash, setPhoneCodeHash] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [running, setRunning] = useState(false);
  const [loadingAccounts, setLoadingAccounts] = useState(true);

  const dateLocale = i18n.language === "he" ? "he-IL" : "en-US";

  async function loadAccounts() {
    setLoadingAccounts(true);
    try {
      setAccounts(await api.listTelegramAccounts());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("telegram.loadFailed"));
    } finally {
      setLoadingAccounts(false);
    }
  }

  async function refresh() {
    try {
      const status = await api.telegramStatus();
      setConnected(status.connected);
      setUsername(status.username || status.first_name || null);
      await loadAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("telegram.loadFailed"));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function requestCode(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    try {
      const res = await api.sendCode(phone);
      setPhoneCodeHash(res.phone_code_hash);
      setInfo(t("telegram.codeSent"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("telegram.sendCodeFailed"));
    }
  }

  async function verifyCode(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.signIn(phone, code, phoneCodeHash);
      setInfo(t("telegram.connected"));
      setCode("");
      setPhoneCodeHash("");
      setPhone("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("telegram.signInFailed"));
    }
  }

  async function removeAccount(account: TelegramAccount) {
    if (!confirm(t("telegram.removeConfirm", { phone: account.phone || account.name }))) return;
    setError("");
    try {
      await api.deleteTelegramAccount(account.id);
      setInfo(t("telegram.removed"));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("telegram.removeFailed"));
    }
  }

  async function runNow() {
    setRunning(true);
    setError("");
    try {
      const res = await api.runNow();
      setInfo(t("telegram.runComplete", { count: res.sent }));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("telegram.runFailed"));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <div className="card">
        <h2>{t("telegram.accountTitle")}</h2>
        {connected ? (
          <p>
            {username ? (
              <Trans i18nKey="telegram.connectedAs" values={{ username }} components={{ strong: <strong /> }} />
            ) : (
              <Trans i18nKey="telegram.connectedAsFallback" components={{ strong: <strong /> }} />
            )}
          </p>
        ) : (
          <p className="muted">
            <Trans i18nKey="telegram.connectHint" components={{ code: <code /> }} />
          </p>
        )}
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn secondary" onClick={() => void refresh()}>
            {t("telegram.refreshStatus")}
          </button>
          <button className="btn" onClick={() => void runNow()} disabled={running || !connected}>
            {running ? t("telegram.running") : t("telegram.runNow")}
          </button>
        </div>
        {info && <p className="muted" style={{ marginTop: 12 }}>{info}</p>}
        {error && <div className="error">{error}</div>}
      </div>

      <div className="card">
        <h2>{t("telegram.linkedAccounts")}</h2>
        {loadingAccounts ? (
          <p className="muted">{t("common.loading")}</p>
        ) : accounts.length === 0 ? (
          <p className="muted">{t("telegram.noAccounts")}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t("telegram.colPhone")}</th>
                <th>{t("telegram.colName")}</th>
                <th>{t("telegram.colStatus")}</th>
                <th>{t("telegram.colAdded")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.id}>
                  <td>{account.phone || t("common.dash")}</td>
                  <td>{account.name}</td>
                  <td>
                    <span className={`badge ${account.is_connected ? "on" : "off"}`}>
                      {account.is_connected ? t("telegram.statusLinked") : t("telegram.statusStored")}
                    </span>
                  </td>
                  <td>{new Date(account.created_at).toLocaleString(dateLocale)}</td>
                  <td>
                    <button className="btn danger" onClick={() => void removeAccount(account)}>
                      {t("telegram.remove")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>{t("telegram.phoneTitle")}</h2>
        <p className="muted">{t("telegram.addAccountHint")}</p>
        <form onSubmit={requestCode}>
          <div className="field">
            <label>{t("telegram.phoneLabel")}</label>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder={t("telegram.phonePlaceholder")}
              required
            />
          </div>
          <button className="btn secondary" type="submit">
            {t("telegram.sendCode")}
          </button>
        </form>

        {phoneCodeHash && (
          <form onSubmit={verifyCode} style={{ marginTop: 16 }}>
            <div className="field">
              <label>{t("telegram.codeLabel")}</label>
              <input value={code} onChange={(e) => setCode(e.target.value)} required />
            </div>
            <button className="btn" type="submit">
              {t("telegram.verify")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
