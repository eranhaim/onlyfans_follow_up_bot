import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, FollowUpStep } from "./api";

export default function MessagesTab() {
  const { t } = useTranslation();
  const [steps, setSteps] = useState<FollowUpStep[]>([]);
  const [delayHours, setDelayHours] = useState("24");
  const [messageText, setMessageText] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      setSteps(await api.listSteps());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("messages.loadFailed"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function addStep(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createStep({
        delay_hours: Number(delayHours),
        message_text: messageText,
        is_active: true,
      });
      setMessageText("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("messages.createFailed"));
    }
  }

  async function toggle(step: FollowUpStep) {
    await api.updateStep(step.id, { is_active: !step.is_active });
    await load();
  }

  async function remove(step: FollowUpStep) {
    if (!confirm(t("messages.deleteConfirm"))) return;
    await api.deleteStep(step.id);
    await load();
  }

  async function move(step: FollowUpStep, direction: -1 | 1) {
    const idx = steps.findIndex((s) => s.id === step.id);
    const target = idx + direction;
    if (target < 0 || target >= steps.length) return;
    const ids = steps.map((s) => s.id);
    [ids[idx], ids[target]] = [ids[target], ids[idx]];
    setSteps(await api.reorderSteps(ids));
  }

  return (
    <div>
      <div className="card">
        <h2>{t("messages.sequenceTitle")}</h2>
        <p className="muted">{t("messages.sequenceHint")}</p>
        {loading ? (
          <p className="muted">{t("common.loading")}</p>
        ) : steps.length === 0 ? (
          <p className="muted">{t("messages.noMessages")}</p>
        ) : (
          steps.map((step, index) => (
            <div className="step-item" key={step.id}>
              <div className="step-header">
                <strong>
                  {t("messages.step", { n: index + 1 })} · {t("messages.afterHours", { hours: step.delay_hours })}
                </strong>
                <div className="row">
                  <span className={`badge ${step.is_active ? "on" : "off"}`}>
                    {step.is_active ? t("messages.active") : t("messages.paused")}
                  </span>
                  <button className="btn secondary" onClick={() => move(step, -1)} disabled={index === 0}>
                    ↑
                  </button>
                  <button
                    className="btn secondary"
                    onClick={() => move(step, 1)}
                    disabled={index === steps.length - 1}
                  >
                    ↓
                  </button>
                  <button className="btn secondary" onClick={() => toggle(step)}>
                    {step.is_active ? t("messages.pause") : t("messages.enable")}
                  </button>
                  <button className="btn danger" onClick={() => remove(step)}>
                    {t("messages.delete")}
                  </button>
                </div>
              </div>
              <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{step.message_text}</p>
            </div>
          ))
        )}
      </div>

      <form className="card" onSubmit={addStep}>
        <h2>{t("messages.addTitle")}</h2>
        <div className="field">
          <label>{t("messages.delayLabel")}</label>
          <input
            type="number"
            min="0.1"
            step="0.1"
            value={delayHours}
            onChange={(e) => setDelayHours(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label>{t("messages.textLabel")}</label>
          <textarea
            value={messageText}
            onChange={(e) => setMessageText(e.target.value)}
            placeholder={t("messages.textPlaceholder")}
            required
          />
        </div>
        {error && <div className="error">{error}</div>}
        <button className="btn" type="submit">
          {t("messages.addButton")}
        </button>
      </form>
    </div>
  );
}
