import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";

export default function TelegramTab() {
  const [connected, setConnected] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [phoneCodeHash, setPhoneCodeHash] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [running, setRunning] = useState(false);

  async function refresh() {
    try {
      const status = await api.telegramStatus();
      setConnected(status.connected);
      setUsername(status.username || status.first_name || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load status");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function requestCode(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    try {
      const res = await api.sendCode(phone);
      setPhoneCodeHash(res.phone_code_hash);
      setInfo("Code sent. Check Telegram and enter it below.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send code");
    }
  }

  async function verifyCode(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.signIn(phone, code, phoneCodeHash);
      setInfo("Connected!");
      setCode("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
    }
  }

  async function runNow() {
    setRunning(true);
    setError("");
    try {
      const res = await api.runNow();
      setInfo(`Scheduler run complete. Sent ${res.sent} message(s).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <div className="card">
        <h2>Telegram account</h2>
        {connected ? (
          <p>
            Connected as <strong>{username ? `@${username}` : "model account"}</strong>
          </p>
        ) : (
          <p className="muted">
            Connect the model&apos;s Telegram account. You need API credentials in the server{" "}
            <code>.env</code> (<code>TELEGRAM_API_ID</code>, <code>TELEGRAM_API_HASH</code>).
          </p>
        )}
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn secondary" onClick={refresh}>
            Refresh status
          </button>
          <button className="btn" onClick={runNow} disabled={running || !connected}>
            {running ? "Running…" : "Run follow-ups now"}
          </button>
        </div>
        {info && <p className="muted" style={{ marginTop: 12 }}>{info}</p>}
        {error && <div className="error">{error}</div>}
      </div>

      {!connected && (
        <div className="card">
          <h2>Connect with phone</h2>
          <form onSubmit={requestCode}>
            <div className="field">
              <label>Phone number (international format)</label>
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+1234567890"
                required
              />
            </div>
            <button className="btn secondary" type="submit">
              Send login code
            </button>
          </form>

          {phoneCodeHash && (
            <form onSubmit={verifyCode} style={{ marginTop: 16 }}>
              <div className="field">
                <label>Code from Telegram</label>
                <input value={code} onChange={(e) => setCode(e.target.value)} required />
              </div>
              <button className="btn" type="submit">
                Verify & connect
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}
