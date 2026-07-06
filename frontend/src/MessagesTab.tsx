import { FormEvent, useEffect, useState } from "react";
import { api, FollowUpStep } from "./api";

export default function MessagesTab() {
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
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
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
      setError(err instanceof Error ? err.message : "Failed to create");
    }
  }

  async function toggle(step: FollowUpStep) {
    await api.updateStep(step.id, { is_active: !step.is_active });
    await load();
  }

  async function remove(step: FollowUpStep) {
    if (!confirm("Delete this follow-up message?")) return;
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
        <h2>Follow-up sequence</h2>
        <p className="muted">
          Messages send in order when a customer goes quiet. Each step fires after the delay (hours)
          from the customer&apos;s last message.
        </p>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : steps.length === 0 ? (
          <p className="muted">No messages yet. Add your first one below.</p>
        ) : (
          steps.map((step, index) => (
            <div className="step-item" key={step.id}>
              <div className="step-header">
                <strong>
                  Step {index + 1} · after {step.delay_hours}h
                </strong>
                <div className="row">
                  <span className={`badge ${step.is_active ? "on" : "off"}`}>
                    {step.is_active ? "Active" : "Paused"}
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
                    {step.is_active ? "Pause" : "Enable"}
                  </button>
                  <button className="btn danger" onClick={() => remove(step)}>
                    Delete
                  </button>
                </div>
              </div>
              <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{step.message_text}</p>
            </div>
          ))
        )}
      </div>

      <form className="card" onSubmit={addStep}>
        <h2>Add message</h2>
        <div className="field">
          <label>Send after (hours of inactivity)</label>
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
          <label>Message text</label>
          <textarea
            value={messageText}
            onChange={(e) => setMessageText(e.target.value)}
            placeholder="Hey! Still interested?"
            required
          />
        </div>
        {error && <div className="error">{error}</div>}
        <button className="btn" type="submit">
          Add to sequence
        </button>
      </form>
    </div>
  );
}
