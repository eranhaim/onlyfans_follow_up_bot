import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, TelegramAccount } from "./api";

export default function TelegramTab() {
  const { t, i18n } = useTranslation();
  const [accounts, setAccounts] = useState<TelegramAccount[]>([]);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [phoneCodeHash, setPhoneCodeHash] = useState("");
  const [password, setPassword] = useState("");
  const [needs2FA, setNeeds2FA] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [running, setRunning] = useState(false);
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [sendingCode, setSendingCode] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [removing, setRemoving] = useState<number | null>(null);

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
    setRefreshing(true);
    try {
      await loadAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("telegram.loadFailed"));
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function requestCode(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    setSendingCode(true);
    try {
      const res = await api.sendCode(phone);
      setPhoneCodeHash(res.phone_code_hash);
      setInfo(t("telegram.codeSent"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("telegram.sendCodeFailed"));
    } finally {
      setSendingCode(false);
    }
  }

  async function verifyCode(e: FormEvent) {
    e.preventDefault();
    setError("");
    setVerifying(true);
    try {
      await api.signIn(phone, code, phoneCodeHash, needs2FA ? password : undefined);
      setInfo(t("telegram.connected"));
      setCode("");
      setPhoneCodeHash("");
      setPhone("");
      setPassword("");
      setNeeds2FA(false);
      await refresh();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("telegram.signInFailed");
      if (msg.toLowerCase().includes("two-factor") || msg.toLowerCase().includes("password")) {
        setNeeds2FA(true);
        setError(t("telegram.2faRequired"));
      } else {
        setError(msg);
      }
    } finally {
      setVerifying(false);
    }
  }

  async function removeAccount(account: TelegramAccount) {
    if (!confirm(t("telegram.removeConfirm", { phone: account.phone || account.name }))) return;
    setError("");
    setRemoving(account.id);
    try {
      await api.deleteTelegramAccount(account.id);
      setInfo(t("telegram.removed"));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("telegram.removeFailed"));
    } finally {
      setRemoving(null);
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
        <h2>{t("telegram.linkedAccounts")}</h2>
        <div className="row" style={{ marginBottom: 12 }}>
          <button className="btn secondary" onClick={() => void refresh()} disabled={refreshing}>
            {refreshing ? t("common.loading") : t("telegram.refreshStatus")}
          </button>
          <button className="btn" onClick={() => void runNow()} disabled={running || accounts.length === 0}>
            {running ? t("telegram.running") : t("telegram.runNow")}
          </button>
        </div>
        {info && <p className="muted" style={{ marginBottom: 8 }}>{info}</p>}
        {error && <div className="error">{error}</div>}
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
                    <button className="btn danger" onClick={() => void removeAccount(account)} disabled={removing === account.id}>
                      {removing === account.id ? t("common.loading") : t("telegram.remove")}
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
          <button className="btn secondary" type="submit" disabled={sendingCode}>
            {sendingCode ? t("common.loading") : t("telegram.sendCode")}
          </button>
        </form>

        {phoneCodeHash && (
          <form onSubmit={verifyCode} style={{ marginTop: 16 }}>
            <div className="field">
              <label>{t("telegram.codeLabel")}</label>
              <input value={code} onChange={(e) => setCode(e.target.value)} required />
            </div>
            {needs2FA && (
              <div className="field">
                <label>{t("telegram.2faLabel")}</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
            )}
            <button className="btn" type="submit" disabled={verifying}>
              {verifying ? t("common.loading") : t("telegram.verify")}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
