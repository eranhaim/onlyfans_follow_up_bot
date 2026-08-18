import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, FollowUpStage } from "./api";

export default function StagesTab() {
  const { t } = useTranslation();
  const [stages, setStages] = useState<FollowUpStage[]>([]);
  const [delayHours, setDelayHours] = useState("24");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadStages() {
    setLoading(true);
    try {
      setStages(await api.listStages());
    } catch (err) {
      setError(err instanceof Error ? err.message : t("stages.loadFailed"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadStages();
  }, []);

  async function addStage(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.createStage({
        delay_hours: Number(delayHours),
        system_prompt: systemPrompt,
        is_active: true,
      });
      setSystemPrompt("");
      await loadStages();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("stages.createFailed"));
    }
  }

  async function toggle(stage: FollowUpStage) {
    await api.updateStage(stage.id, { is_active: !stage.is_active });
    await loadStages();
  }

  async function remove(stage: FollowUpStage) {
    if (!confirm(t("stages.deleteConfirm"))) return;
    await api.deleteStage(stage.id);
    await loadStages();
  }

  async function move(stage: FollowUpStage, direction: -1 | 1) {
    const idx = stages.findIndex((s) => s.id === stage.id);
    const target = idx + direction;
    if (target < 0 || target >= stages.length) return;
    const ids = stages.map((s) => s.id);
    [ids[idx], ids[target]] = [ids[target], ids[idx]];
    setStages(await api.reorderStages(ids));
  }

  async function savePrompt(stage: FollowUpStage, newPrompt: string) {
    await api.updateStage(stage.id, { system_prompt: newPrompt });
    await loadStages();
  }

  return (
    <div>
      <div className="card">
        <h2>{t("stages.sequenceTitle")}</h2>
        <p className="muted">{t("stages.sequenceHint")}</p>
        {loading ? (
          <p className="muted">{t("common.loading")}</p>
        ) : stages.length === 0 ? (
          <p className="muted">{t("stages.noStages")}</p>
        ) : (
          stages.map((stage, index) => (
            <StageItem
              key={stage.id}
              stage={stage}
              index={index}
              total={stages.length}
              onToggle={() => toggle(stage)}
              onRemove={() => remove(stage)}
              onMoveUp={() => move(stage, -1)}
              onMoveDown={() => move(stage, 1)}
              onSavePrompt={(p) => savePrompt(stage, p)}
              t={t}
            />
          ))
        )}
      </div>

      <form className="card" onSubmit={addStage}>
        <h2>{t("stages.addTitle")}</h2>
        <div className="field">
          <label>{t("stages.delayLabel")}</label>
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
          <label>{t("stages.promptLabel")}</label>
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder={t("stages.promptPlaceholder")}
            rows={6}
          />
        </div>
        {error && <div className="error">{error}</div>}
        <button className="btn" type="submit">
          {t("stages.addButton")}
        </button>
      </form>
    </div>
  );
}

function StageItem({
  stage,
  index,
  total,
  onToggle,
  onRemove,
  onMoveUp,
  onMoveDown,
  onSavePrompt,
  t,
}: {
  stage: FollowUpStage;
  index: number;
  total: number;
  onToggle: () => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onSavePrompt: (prompt: string) => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  const [editing, setEditing] = useState(false);
  const [localPrompt, setLocalPrompt] = useState(stage.system_prompt);

  return (
    <div className="step-item">
      <div className="step-header">
        <strong>
          {t("stages.stage", { n: index + 1 })} ·{" "}
          {index === 0
            ? t("stages.afterLastMessage", { hours: stage.delay_hours })
            : t("stages.afterLastFollowUp", { hours: stage.delay_hours })}
        </strong>
        <div className="row">
          <span className={`badge ${stage.is_active ? "on" : "off"}`}>
            {stage.is_active ? t("stages.active") : t("stages.paused")}
          </span>
          <button className="btn secondary" onClick={onMoveUp} disabled={index === 0}>
            ↑
          </button>
          <button className="btn secondary" onClick={onMoveDown} disabled={index === total - 1}>
            ↓
          </button>
          <button className="btn secondary" onClick={onToggle}>
            {stage.is_active ? t("stages.pause") : t("stages.enable")}
          </button>
          <button className="btn secondary" onClick={() => setEditing(!editing)}>
            {editing ? t("stages.closePrompt") : t("stages.editPrompt")}
          </button>
          <button className="btn danger" onClick={onRemove}>
            {t("stages.delete")}
          </button>
        </div>
      </div>
      {editing && (
        <div style={{ marginTop: 8 }}>
          <textarea
            value={localPrompt}
            onChange={(e) => setLocalPrompt(e.target.value)}
            rows={5}
            style={{ width: "100%", marginBottom: 8 }}
          />
          <button
            className="btn secondary"
            onClick={() => {
              onSavePrompt(localPrompt);
              setEditing(false);
            }}
          >
            {t("stages.savePrompt")}
          </button>
        </div>
      )}
      {!editing && stage.system_prompt && (
        <p className="muted" style={{ margin: "4px 0 0", whiteSpace: "pre-wrap", fontSize: "0.85em" }}>
          {stage.system_prompt.length > 120
            ? stage.system_prompt.slice(0, 120) + "..."
            : stage.system_prompt}
        </p>
      )}
    </div>
  );
}
