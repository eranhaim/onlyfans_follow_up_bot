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
  if (!options.body || !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
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

// --- Types ---

export type FollowUpStage = {
  id: number;
  account_id: number;
  position: number;
  delay_hours: number;
  system_prompt: string;
  is_active: boolean;
};

export type Video = {
  id: number;
  account_id: number;
  filename: string;
  tags: string;
  description: string;
  created_at: string;
};

export type DashboardStats = {
  connected: boolean;
  active_stages: number;
  tracked_conversations: number;
  pending_follow_ups: number;
  sent_last_24h: number;
};

export type Conversation = {
  id: number;
  account_id: number;
  telegram_user_id: number;
  display_name: string | null;
  last_user_message_at: string | null;
  steps_sent: number;
  last_follow_up_at: string | null;
  opted_out: boolean;
};

export type FanProfile = {
  personality_type?: string;
  triggers?: string;
  language?: string;
  notes?: string;
  updated_at?: string;
};

export type TelegramAccount = {
  id: number;
  name: string;
  phone: string | null;
  is_connected: boolean;
  personality: string | null;
  created_at: string;
};

export type ChannelAccount = {
  id: number;
  name: string;
  phone: string | null;
  is_connected: boolean;
  created_at: string;
};

export type TelegramChannel = {
  id: number;
  channel_account_id: number;
  channel_id: number;
  title: string;
  username: string | null;
  subscribers_count: number;
  is_active: boolean;
  created_at: string;
};

export type ChannelSubscriber = {
  user_id: number;
  first_name: string | null;
  last_name: string | null;
  username: string | null;
};

// --- API ---

export const api = {
  login: (password: string) =>
    request<{ token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  stats: () => request<DashboardStats>("/api/stats"),

  // Stages
  listStages: (accountId?: number) =>
    request<FollowUpStage[]>(
      accountId != null ? `/api/stages?account_id=${accountId}` : "/api/stages"
    ),

  createStage: (data: { account_id: number; delay_hours: number; system_prompt: string; is_active: boolean }) =>
    request<FollowUpStage>("/api/stages", { method: "POST", body: JSON.stringify(data) }),

  updateStage: (id: number, data: Partial<FollowUpStage>) =>
    request<FollowUpStage>(`/api/stages/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  deleteStage: (id: number) => request<{ ok: boolean }>(`/api/stages/${id}`, { method: "DELETE" }),

  reorderStages: (stage_ids: number[]) =>
    request<FollowUpStage[]>("/api/stages/reorder", {
      method: "PUT",
      body: JSON.stringify({ stage_ids }),
    }),

  // Videos
  listVideos: (accountId?: number) =>
    request<Video[]>(
      accountId != null ? `/api/videos?account_id=${accountId}` : "/api/videos"
    ),

  uploadVideo: (accountId: number, file: File, tags: string, description: string) => {
    const formData = new FormData();
    formData.append("account_id", String(accountId));
    formData.append("tags", tags);
    formData.append("description", description);
    formData.append("file", file);
    return request<Video>("/api/videos", { method: "POST", body: formData });
  },

  updateVideo: (id: number, data: { tags?: string; description?: string }) =>
    request<Video>(`/api/videos/${id}`, { method: "PATCH", body: JSON.stringify(data) }),

  deleteVideo: (id: number) => request<{ ok: boolean }>(`/api/videos/${id}`, { method: "DELETE" }),

  // Conversations
  listConversations: (accountId?: number) =>
    request<Conversation[]>(
      accountId != null ? `/api/conversations?account_id=${accountId}` : "/api/conversations"
    ),

  optOut: (id: number) =>
    request<{ ok: boolean }>(`/api/conversations/${id}/opt-out`, { method: "POST" }),

  optIn: (id: number) =>
    request<{ ok: boolean }>(`/api/conversations/${id}/opt-in`, { method: "POST" }),

  skipStep: (id: number) =>
    request<{ ok: boolean }>(`/api/conversations/${id}/skip-step`, { method: "POST" }),

  fanProfile: (id: number) =>
    request<FanProfile>(`/api/conversations/${id}/fan-profile`),

  // Telegram
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

  updateAccount: (id: number, data: { name?: string; personality?: string }) =>
    request<TelegramAccount>(`/api/telegram/accounts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  runNow: () => request<{ sent: number }>("/api/telegram/run-now", { method: "POST" }),

  // Channel Accounts
  listChannelAccounts: () => request<ChannelAccount[]>("/api/channel-accounts"),

  channelSendCode: (phone: string) =>
    request<{ phone_code_hash: string }>("/api/channel-accounts/send-code", {
      method: "POST",
      body: JSON.stringify({ phone }),
    }),

  channelSignIn: (phone: string, code: string, phone_code_hash: string, password?: string) =>
    request<{ ok: boolean }>("/api/channel-accounts/sign-in", {
      method: "POST",
      body: JSON.stringify({ phone, code, phone_code_hash, password }),
    }),

  deleteChannelAccount: (id: number) =>
    request<{ ok: boolean }>(`/api/channel-accounts/${id}`, { method: "DELETE" }),

  // Channels
  listChannels: (channelAccountId?: number) =>
    request<TelegramChannel[]>(
      channelAccountId != null ? `/api/channels?channel_account_id=${channelAccountId}` : "/api/channels"
    ),

  syncChannels: (channelAccountId: number) =>
    request<{ ok: boolean; synced: number }>(`/api/channels/sync?channel_account_id=${channelAccountId}`, {
      method: "POST",
    }),

  getChannelSubscribers: (channelId: number) =>
    request<ChannelSubscriber[]>(`/api/channels/${channelId}/subscribers`),

  updateChannel: (channelId: number, data: { is_active?: boolean }) =>
    request<TelegramChannel>(`/api/channels/${channelId}?${new URLSearchParams(
      Object.entries(data).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])
    )}`, { method: "PATCH" }),

  deleteChannel: (channelId: number) =>
    request<{ ok: boolean }>(`/api/channels/${channelId}`, { method: "DELETE" }),
};

// --- Simulator Types ---

export type SimMessage = {
  role: "user" | "bot";
  content: string;
  stage_position: number | null;
  video_id: number | null;
  video_filename: string | null;
  sim_time: string;
};

export type SimConversation = {
  id: number;
  display_name: string;
  account_name: string;
  steps_sent: number;
};

export type SimState = {
  session_id: string;
  account_id: number;
  stages: FollowUpStage[];
  videos: Video[];
  messages: SimMessage[];
  steps_sent: number;
  sim_now: string;
  last_user_message_at: string | null;
  last_follow_up_at: string | null;
  next_stage_index: number | null;
  next_follow_up_due_at: string | null;
  hours_until_next: number | null;
  sequence_complete: boolean;
  fan_display_name: string | null;
  fan_profile: FanProfile | null;
};

export const simulator = {
  listConversations: () =>
    request<SimConversation[]>(`/api/simulator/conversations`),

  start: (account_id: number, conversation_id?: number) =>
    request<SimState>("/api/simulator/start", {
      method: "POST",
      body: JSON.stringify({ account_id, conversation_id: conversation_id ?? null }),
    }),

  getSession: (session_id: string) =>
    request<SimState>(`/api/simulator/${session_id}`),

  sendMessage: (session_id: string, content: string) =>
    request<SimState>(`/api/simulator/${session_id}/message`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  advance: (session_id: string, hours: number) =>
    request<SimState>(`/api/simulator/${session_id}/advance`, {
      method: "POST",
      body: JSON.stringify({ hours }),
    }),

  deleteSession: (session_id: string) =>
    request<{ ok: boolean }>(`/api/simulator/${session_id}`, { method: "DELETE" }),

  getLastDebug: () =>
    request<Record<string, unknown>>("/api/simulator/debug/last-prompt"),
};
