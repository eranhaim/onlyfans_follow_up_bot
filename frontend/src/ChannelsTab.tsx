import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ChannelAccount, TelegramChannel, ChannelSubscriber } from "./api";

export default function ChannelsTab() {
  const { t, i18n } = useTranslation();

  // Channel accounts
  const [channelAccounts, setChannelAccounts] = useState<ChannelAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [loadingAccounts, setLoadingAccounts] = useState(true);

  // Sign-in flow
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [phoneCodeHash, setPhoneCodeHash] = useState("");
  const [password, setPassword] = useState("");
  const [needs2FA, setNeeds2FA] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [verifying, setVerifying] = useState(false);

  // Channels
  const [channels, setChannels] = useState<TelegramChannel[]>([]);
  const [loadingChannels, setLoadingChannels] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Subscribers panel
  const [subscribersChannel, setSubscribersChannel] = useState<TelegramChannel | null>(null);
  const [subscribers, setSubscribers] = useState<ChannelSubscriber[]>([]);
  const [loadingSubs, setLoadingSubs] = useState(false);
  const [subsError, setSubsError] = useState("");

  const [removingAccount, setRemovingAccount] = useState<number | null>(null);
  const [togglingChannel, setTogglingChannel] = useState<number | null>(null);
  const [removingChannel, setRemovingChannel] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const dateLocale = i18n.language === "he" ? "he-IL" : "en-US";

  async function loadAccounts() {
    setLoadingAccounts(true);
    try {
      const accs = await api.listChannelAccounts();
      setChannelAccounts(accs);
      if (accs.length > 0 && selectedAccountId == null) {
        setSelectedAccountId(accs[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("channels.loadFailed"));
    } finally {
      setLoadingAccounts(false);
    }
  }

  async function loadChannels() {
    if (selectedAccountId == null) {
      setChannels([]);
      return;
    }
    setLoadingChannels(true);
    try {
      setChannels(await api.listChannels(selectedAccountId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("channels.loadFailed"));
    } finally {
      setLoadingChannels(false);
    }
  }

  useEffect(() => {
    void loadAccounts();
  }, []);

  useEffect(() => {
    if (selectedAccountId != null) {
      void loadChannels();
      // Auto-sync when selecting an account
      void syncChannels();
    }
  }, [selectedAccountId]);

  // --- Sign-in ---

  async function requestCode(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    setSendingCode(true);
    try {
      const res = await api.channelSendCode(phone);
      setPhoneCodeHash(res.phone_code_hash);
      setInfo(t("channels.codeSent"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("channels.sendCodeFailed"));
    } finally {
      setSendingCode(false);
    }
  }

  async function verifyCode(e: FormEvent) {
    e.preventDefault();
    setError("");
    setVerifying(true);
    try {
      await api.channelSignIn(phone, code, phoneCodeHash, needs2FA ? password : undefined);
      setInfo(t("channels.connected"));
      setCode("");
      setPhoneCodeHash("");
      setPhone("");
      setPassword("");
      setNeeds2FA(false);
      await loadAccounts();
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("channels.signInFailed");
      if (msg.toLowerCase().includes("two-factor") || msg.toLowerCase().includes("password")) {
        setNeeds2FA(true);
        setError(t("channels.2faRequired"));
      } else {
        setError(msg);
      }
    } finally {
      setVerifying(false);
    }
  }

  async function removeAccount(account: ChannelAccount) {
    if (!confirm(t("channels.removeAccountConfirm", { phone: account.phone || account.name }))) return;
    setError("");
    setRemovingAccount(account.id);
    try {
      await api.deleteChannelAccount(account.id);
      setInfo(t("channels.accountRemoved"));
      if (selectedAccountId === account.id) setSelectedAccountId(null);
      await loadAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("channels.removeAccountFailed"));
    } finally {
      setRemovingAccount(null);
    }
  }

  // --- Channels ---

  async function syncChannels() {
    if (selectedAccountId == null) return;
    setSyncing(true);
    setError("");
    setInfo("");
    try {
      const res = await api.syncChannels(selectedAccountId);
      setInfo(t("channels.syncComplete", { count: res.synced }));
      await loadChannels();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("channels.syncFailed"));
    } finally {
      setSyncing(false);
    }
  }

  async function toggleActive(channel: TelegramChannel) {
    setTogglingChannel(channel.id);
    try {
      await api.updateChannel(channel.id, { is_active: !channel.is_active });
      await loadChannels();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setTogglingChannel(null);
    }
  }

  async function removeChannel(channel: TelegramChannel) {
    if (!confirm(t("channels.removeConfirm", { title: channel.title }))) return;
    setRemovingChannel(channel.id);
    try {
      await api.deleteChannel(channel.id);
      await loadChannels();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("channels.removeFailed"));
    } finally {
      setRemovingChannel(null);
    }
  }

  function exportSubscribersCsv() {
    if (!subscribers.length || !subscribersChannel) return;
    const header = "Name,Username,User ID";
    const rows = subscribers.map((sub) => {
      const name = [sub.first_name, sub.last_name].filter(Boolean).join(" ") || "";
      const username = sub.username ? `@${sub.username}` : "";
      return `"${name.replace(/"/g, '""')}","${username}",${sub.user_id}`;
    });
    const csv = [header, ...rows].join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${subscribersChannel.title}_subscribers.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function viewSubscribers(channel: TelegramChannel) {
    setSubscribersChannel(channel);
    setSubscribers([]);
    setSubsError("");
    setLoadingSubs(true);
    try {
      setSubscribers(await api.getChannelSubscribers(channel.id));
    } catch (err) {
      setSubsError(err instanceof Error ? err.message : t("channels.subscribersFailed"));
    } finally {
      setLoadingSubs(false);
    }
  }

  return (
    <div>
      <h2>{t("channels.title")}</h2>

      {error && <div className="error" style={{ marginBottom: 12 }}>{error}</div>}
      {info && <p className="muted" style={{ marginBottom: 12 }}>{info}</p>}

      {/* Channel Accounts */}
      <div className="card">
        <h2>{t("channels.linkedAccounts")}</h2>
        {loadingAccounts ? (
          <p className="muted">{t("common.loading")}</p>
        ) : channelAccounts.length === 0 ? (
          <p className="muted">{t("channels.noAccounts")}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t("channels.colPhone")}</th>
                <th>{t("channels.colName")}</th>
                <th>{t("channels.colStatus")}</th>
                <th>{t("channels.colAdded")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {channelAccounts.map((acc) => (
                <tr key={acc.id}>
                  <td>{acc.phone || t("common.dash")}</td>
                  <td>{acc.name}</td>
                  <td>
                    <span className={`badge ${acc.is_connected ? "on" : "off"}`}>
                      {acc.is_connected ? t("channels.statusLinked") : t("channels.statusStored")}
                    </span>
                  </td>
                  <td>{new Date(acc.created_at).toLocaleString(dateLocale)}</td>
                  <td>
                    <button className="btn danger" onClick={() => void removeAccount(acc)} disabled={removingAccount === acc.id}>
                      {removingAccount === acc.id ? t("common.loading") : t("channels.removeAccount")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Sign-in form */}
      <div className="card">
        <h2>{t("channels.phoneTitle")}</h2>
        <p className="muted">{t("channels.connectHint")}</p>
        <form onSubmit={requestCode}>
          <div className="field">
            <label>{t("channels.phoneLabel")}</label>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder={t("channels.phonePlaceholder")}
              required
            />
          </div>
          <button className="btn secondary" type="submit" disabled={sendingCode}>
            {sendingCode ? t("common.loading") : t("channels.sendCode")}
          </button>
        </form>

        {phoneCodeHash && (
          <form onSubmit={verifyCode} style={{ marginTop: 16 }}>
            <div className="field">
              <label>{t("channels.codeLabel")}</label>
              <input value={code} onChange={(e) => setCode(e.target.value)} required />
            </div>
            {needs2FA && (
              <div className="field">
                <label>{t("channels.2faLabel")}</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
            )}
            <button className="btn" type="submit" disabled={verifying}>
              {verifying ? t("common.loading") : t("channels.verify")}
            </button>
          </form>
        )}
      </div>

      {/* Channels list */}
      {channelAccounts.length > 0 && (
        <div className="card">
          <div className="row" style={{ marginBottom: 16, gap: 12, alignItems: "center" }}>
            <label>{t("channels.selectAccount")}</label>
            <select
              value={selectedAccountId ?? ""}
              onChange={(e) => setSelectedAccountId(Number(e.target.value))}
            >
              {channelAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.phone || "—"})
                </option>
              ))}
            </select>
            <button
              className="btn"
              onClick={() => void syncChannels()}
              disabled={syncing || selectedAccountId == null}
            >
              {syncing ? t("channels.syncing") : t("channels.syncButton")}
            </button>
          </div>

          {loadingChannels ? (
            <p className="muted">{t("common.loading")}</p>
          ) : channels.length === 0 ? (
            <p className="muted">{t("channels.noChannels")}</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>{t("channels.colTitle")}</th>
                  <th>{t("channels.colUsername")}</th>
                  <th>{t("channels.colSubscribers")}</th>
                  <th>{t("channels.colChannelStatus")}</th>
                  <th>{t("channels.colActions")}</th>
                </tr>
              </thead>
              <tbody>
                {channels.map((ch) => (
                  <tr key={ch.id}>
                    <td>{ch.title}</td>
                    <td>{ch.username ? `@${ch.username}` : t("common.dash")}</td>
                    <td>{ch.subscribers_count.toLocaleString(dateLocale)}</td>
                    <td>
                      <span className={`badge ${ch.is_active ? "on" : "off"}`}>
                        {ch.is_active ? t("channels.active") : t("channels.inactive")}
                      </span>
                    </td>
                    <td>
                      <div className="row" style={{ gap: 6 }}>
                        <button className="btn secondary" onClick={() => void viewSubscribers(ch)}>
                          {t("channels.viewSubscribers")}
                        </button>
                        <button className="btn secondary" onClick={() => void toggleActive(ch)} disabled={togglingChannel === ch.id}>
                          {togglingChannel === ch.id ? t("common.loading") : ch.is_active ? t("channels.deactivate") : t("channels.activate")}
                        </button>
                        <button className="btn danger" onClick={() => void removeChannel(ch)} disabled={removingChannel === ch.id}>
                          {removingChannel === ch.id ? t("common.loading") : t("channels.remove")}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Subscribers panel */}
      {subscribersChannel && (
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <h2>{t("channels.subscribersTitle", { title: subscribersChannel.title })}</h2>
            <div className="row" style={{ gap: 8 }}>
              {subscribers.length > 0 && (
                <button className="btn" onClick={() => exportSubscribersCsv()}>
                  {t("channels.exportCsv")}
                </button>
              )}
              <button
                className="btn secondary"
                onClick={() => setSubscribersChannel(null)}
              >
                {t("channels.close")}
              </button>
            </div>
          </div>

          {loadingSubs ? (
            <p className="muted">{t("channels.loadingSubscribers")}</p>
          ) : subsError ? (
            <div className="error">{subsError}</div>
          ) : subscribers.length === 0 ? (
            <p className="muted">{t("channels.noSubscribers")}</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>{t("channels.colSubName")}</th>
                  <th>{t("channels.colUsernameSub")}</th>
                  <th>{t("channels.colUserId")}</th>
                </tr>
              </thead>
              <tbody>
                {subscribers.map((sub) => (
                  <tr key={sub.user_id}>
                    <td>
                      {[sub.first_name, sub.last_name].filter(Boolean).join(" ") || t("common.dash")}
                    </td>
                    <td>{sub.username ? `@${sub.username}` : t("common.dash")}</td>
                    <td>{sub.user_id}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
