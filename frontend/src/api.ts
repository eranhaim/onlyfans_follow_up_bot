const TOKEN_KEY = "followup_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    window.location.reload();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export type FollowUpStep = {
  id: number;
  position: number;
  delay_hours: number;
  message_text: string;
  is_active: boolean;
};

export type DashboardStats = {
  connected: boolean;
  active_steps: number;
  tracked_conversations: number;
  pending_follow_ups: number;
  sent_last_24h: number;
};

export type Conversation = {
  id: number;
  telegram_user_id: number;
  display_name: string | null;
  last_user_message_at: string | null;
  steps_sent: number;
  last_follow_up_at: string | null;
  opted_out: boolean;
};

export type TelegramAccount = {
  id: number;
  name: string;
  phone: string | null;
  is_connected: boolean;
  created_at: string;
};

export const api = {
  login: (password: string) =>
    request<{ token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  stats: () => request<DashboardStats>("/api/stats"),

  listSteps: () => request<FollowUpStep[]>("/api/steps"),

  createStep: (data: { delay_hours: number; message_text: string; is_active: boolean }) =>
    request<FollowUpStep>("/api/steps", { method: "POST", body: JSON.stringify(data) }),

  updateStep: (id: number, data: Partial<FollowUpStep>) =>
    request<FollowUpStep>(`/api/steps/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  deleteStep: (id: number) => request<{ ok: boolean }>(`/api/steps/${id}`, { method: "DELETE" }),

  reorderSteps: (step_ids: number[]) =>
    request<FollowUpStep[]>("/api/steps/reorder", {
      method: "PUT",
      body: JSON.stringify({ step_ids }),
    }),

  listConversations: () => request<Conversation[]>("/api/conversations"),

  optOut: (id: number) =>
    request<{ ok: boolean }>(`/api/conversations/${id}/opt-out`, { method: "POST" }),

  telegramStatus: () =>
    request<{ connected: boolean; username?: string; first_name?: string }>("/api/telegram/status"),

  listTelegramAccounts: () => request<TelegramAccount[]>("/api/telegram/accounts"),

  deleteTelegramAccount: (id: number) =>
    request<{ ok: boolean }>(`/api/telegram/accounts/${id}`, { method: "DELETE" }),

  sendCode: (phone: string) =>
    request<{ phone_code_hash: string }>("/api/telegram/send-code", {
      method: "POST",
      body: JSON.stringify({ phone }),
    }),

  signIn: (phone: string, code: string, phone_code_hash: string, password?: string) =>
    request<{ ok: boolean }>("/api/telegram/sign-in", {
      method: "POST",
      body: JSON.stringify({ phone, code, phone_code_hash, password }),
    }),

  runNow: () => request<{ sent: number }>("/api/telegram/run-now", { method: "POST" }),
};
