import { FormEvent, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, TelegramAccount, Video } from "./api";

export default function ModelTab() {
  const { t, i18n } = useTranslation();
  const [accounts, setAccounts] = useState<TelegramAccount[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<TelegramAccount | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  // Personality edit state
  const [editingPersonality, setEditingPersonality] = useState(false);
  const [personalityDraft, setPersonalityDraft] = useState("");
  const [nameDraft, setNameDraft] = useState("");
  const [savingPersonality, setSavingPersonality] = useState(false);

  // Video upload state
  const [tags, setTags] = useState("");
  const [description, setDescription] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const dateLocale = i18n.language === "he" ? "he-IL" : "en-US";

  async function loadAccounts() {
    try {
      const accs = await api.listTelegramAccounts();
      setAccounts(accs);
      if (accs.length > 0 && selectedAccount === null) {
        setSelectedAccount(accs[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  }

  async function loadVideos(accountId: number) {
    setLoading(true);
    try {
      setVideos(await api.listVideos(accountId));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("videos.loadFailed"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAccounts();
  }, []);

  useEffect(() => {
    if (selectedAccount !== null) {
      void loadVideos(selectedAccount.id);
    }
  }, [selectedAccount?.id]);

  function selectAccount(id: number) {
    const acc = accounts.find((a) => a.id === id) ?? null;
    setSelectedAccount(acc);
    setEditingPersonality(false);
    setError("");
    setInfo("");
  }

  function startEditPersonality() {
    if (!selectedAccount) return;
    setNameDraft(selectedAccount.name);
    setPersonalityDraft(selectedAccount.personality ?? "");
    setEditingPersonality(true);
  }

  async function savePersonality(e: FormEvent) {
    e.preventDefault();
    if (!selectedAccount) return;
    setSavingPersonality(true);
    setError("");
    try {
      const updated = await api.updateAccount(selectedAccount.id, {
        name: nameDraft,
        personality: personalityDraft,
      });
      setSelectedAccount(updated);
      setAccounts((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
      setEditingPersonality(false);
      setInfo(t("model.personalitySaved"));
      setTimeout(() => setInfo(""), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setSavingPersonality(false);
    }
  }

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    if (selectedAccount === null) return;
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError(t("videos.selectFile"));
      return;
    }
    setError("");
    setInfo("");
    try {
      await api.uploadVideo(selectedAccount.id, file, tags, description);
      setTags("");
      setDescription("");
      if (fileRef.current) fileRef.current.value = "";
      setInfo(t("videos.uploaded"));
      await loadVideos(selectedAccount.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("videos.uploadFailed"));
    }
  }

  async function removeVideo(video: Video) {
    if (!confirm(t("videos.deleteConfirm", { name: video.filename }))) return;
    setError("");
    try {
      await api.deleteVideo(video.id);
      if (selectedAccount) await loadVideos(selectedAccount.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("videos.deleteFailed"));
    }
  }

  return (
    <div>
      {/* Account selector */}
      <div className="card">
        <h2>{t("model.title")}</h2>
        <div className="field">
          <label>{t("model.selectAccount")}</label>
          <select
            value={selectedAccount?.id ?? ""}
            onChange={(e) => selectAccount(Number(e.target.value))}
          >
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.name}{acc.phone ? ` (${acc.phone})` : ""}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Personality section */}
      {selectedAccount && (
        <div className="card">
          <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
            <h2 style={{ margin: 0 }}>{t("model.personalityTitle")}</h2>
            {!editingPersonality && (
              <button className="btn secondary" onClick={startEditPersonality}>
                {t("model.editPersonality")}
              </button>
            )}
          </div>

          {!editingPersonality ? (
            selectedAccount.personality ? (
              <p style={{ whiteSpace: "pre-wrap", color: "#ccc", margin: 0 }}>
                {selectedAccount.personality}
              </p>
            ) : (
              <p className="muted">{t("model.noPersonality")}</p>
            )
          ) : (
            <form onSubmit={savePersonality}>
              <div className="field">
                <label>{t("model.nameLabel")}</label>
                <input
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  required
                />
              </div>
              <div className="field">
                <label>{t("model.personalityLabel")}</label>
                <textarea
                  value={personalityDraft}
                  onChange={(e) => setPersonalityDraft(e.target.value)}
                  placeholder={t("model.personalityPlaceholder")}
                  rows={6}
                />
              </div>
              <div className="row" style={{ gap: 8 }}>
                <button className="btn primary" type="submit" disabled={savingPersonality}>
                  {savingPersonality ? t("common.loading") : t("model.save")}
                </button>
                <button className="btn secondary" type="button" onClick={() => setEditingPersonality(false)}>
                  {t("model.cancel")}
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {/* Videos list */}
      <div className="card">
        <h2>{t("videos.bankTitle")}</h2>
        {loading ? (
          <p className="muted">{t("common.loading")}</p>
        ) : videos.length === 0 ? (
          <p className="muted">{t("videos.noVideos")}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t("videos.colFilename")}</th>
                <th>{t("videos.colTags")}</th>
                <th>{t("videos.colDescription")}</th>
                <th>{t("videos.colDate")}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {videos.map((video) => (
                <tr key={video.id}>
                  <td>{video.filename}</td>
                  <td>{video.tags || "—"}</td>
                  <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {video.description || "—"}
                  </td>
                  <td>{new Date(video.created_at).toLocaleDateString(dateLocale)}</td>
                  <td>
                    <button className="btn danger" onClick={() => removeVideo(video)}>
                      {t("videos.delete")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Upload form */}
      <form className="card" onSubmit={handleUpload}>
        <h2>{t("videos.uploadTitle")}</h2>
        <div className="field">
          <label>{t("videos.fileLabel")}</label>
          <input type="file" accept="video/*" ref={fileRef} required />
        </div>
        <div className="field">
          <label>{t("videos.tagsLabel")}</label>
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder={t("videos.tagsPlaceholder")}
          />
        </div>
        <div className="field">
          <label>{t("videos.descriptionLabel")}</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t("videos.descriptionPlaceholder")}
            rows={3}
          />
        </div>
        {error && <div className="error">{error}</div>}
        {info && <p className="muted">{info}</p>}
        <button className="btn" type="submit" disabled={selectedAccount === null}>
          {t("videos.uploadButton")}
        </button>
      </form>
    </div>
  );
}
