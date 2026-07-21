import { FormEvent, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, TelegramAccount, Video } from "./api";

export default function VideosTab() {
  const { t, i18n } = useTranslation();
  const [accounts, setAccounts] = useState<TelegramAccount[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<number | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const [tags, setTags] = useState("");
  const [description, setDescription] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const dateLocale = i18n.language === "he" ? "he-IL" : "en-US";

  async function loadAccounts() {
    try {
      const accs = await api.listTelegramAccounts();
      setAccounts(accs);
      if (accs.length > 0 && selectedAccount === null) {
        setSelectedAccount(accs[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("common.error"));
    }
  }

  async function loadVideos() {
    if (selectedAccount === null) return;
    setLoading(true);
    try {
      setVideos(await api.listVideos(selectedAccount));
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
      void loadVideos();
    }
  }, [selectedAccount]);

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
      await api.uploadVideo(selectedAccount, file, tags, description);
      setTags("");
      setDescription("");
      if (fileRef.current) fileRef.current.value = "";
      setInfo(t("videos.uploaded"));
      await loadVideos();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("videos.uploadFailed"));
    }
  }

  async function removeVideo(video: Video) {
    if (!confirm(t("videos.deleteConfirm", { name: video.filename }))) return;
    setError("");
    try {
      await api.deleteVideo(video.id);
      await loadVideos();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("videos.deleteFailed"));
    }
  }

  return (
    <div>
      <div className="card">
        <h2>{t("videos.title")}</h2>
        <div className="field">
          <label>{t("videos.selectAccount")}</label>
          <select
            value={selectedAccount ?? ""}
            onChange={(e) => setSelectedAccount(Number(e.target.value))}
          >
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.name} ({acc.phone || "—"})
              </option>
            ))}
          </select>
        </div>
      </div>

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
        <button className="btn" type="submit">
          {t("videos.uploadButton")}
        </button>
      </form>
    </div>
  );
}
