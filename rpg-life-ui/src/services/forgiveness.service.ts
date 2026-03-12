import apiClient, { apiPath } from "@/lib/api";

export type ForgivenessPreset =
  | "balanced"
  | "hardcore"
  | "lenient"
  | "zen"
  | "adaptive"
  | "custom";

export const DEFAULT_FORGIVENESS_PRESET: ForgivenessPreset = "balanced";

export interface ForgivenessPresetInfo {
  preset: ForgivenessPreset;
  name: string;
  skill_decay_rate: number;
  skill_grace_days: number;
  insight_decay_rate: number;
  insight_grace_days: number;
  critical_threshold: number;
}

export interface ForgivenessConfig {
  preset: ForgivenessPreset;
  skill_decay_rate: number;
  skill_grace_period_days: number;
  insight_decay_rate: number;
  insight_grace_period_days: number;
  critical_staleness_threshold: number;
}

export interface UpdateForgivenessCustomParamsRequest {
  skill_decay_rate: number;
  skill_grace_days: number;
  insight_decay_rate: number;
  insight_grace_days: number;
}

interface ForgivenessRequestConfig {
  params?: Record<string, string>;
}

function getLocalFallbackBaseURL(): string | null {
  const baseURL = String(apiClient.defaults.baseURL ?? "");
  const isLocal8000 =
    baseURL.includes("localhost:8000") || baseURL.includes("127.0.0.1:8000");

  if (!isLocal8000) {
    return null;
  }

  const fallbackBaseURL = baseURL.replace(":8000", ":8002");
  return fallbackBaseURL === baseURL ? null : fallbackBaseURL;
}

function isSuccessfulStatus(status: number): boolean {
  return status >= 200 && status < 300;
}

function getErrorMessage(data: unknown, status: number): string {
  if (data && typeof data === "object") {
    const detail =
      "detail" in data && typeof data.detail === "string" ? data.detail : null;
    if (detail) {
      return detail;
    }

    const message =
      "message" in data && typeof data.message === "string" ? data.message : null;
    if (message) {
      return message;
    }
  }

  return status === 404 ? "Not Found" : `Request failed with status ${status}`;
}

async function getWithFallback<T>(
  path: string,
  config?: ForgivenessRequestConfig,
): Promise<T> {
  const response = await apiClient.get<T>(path, {
    ...config,
    validateStatus: () => true,
  });

  if (isSuccessfulStatus(response.status)) {
    return response.data;
  }

  const fallbackBaseURL = getLocalFallbackBaseURL();
  if (response.status === 404 && fallbackBaseURL) {
    const fallbackResponse = await apiClient.get<T>(`${fallbackBaseURL}${path}`, {
      ...config,
      validateStatus: () => true,
    });

    if (isSuccessfulStatus(fallbackResponse.status)) {
      return fallbackResponse.data;
    }

    throw new Error(
      getErrorMessage(fallbackResponse.data, fallbackResponse.status),
    );
  }

  throw new Error(getErrorMessage(response.data, response.status));
}

async function postWithFallback<T>(
  path: string,
  body: unknown,
  config?: ForgivenessRequestConfig,
): Promise<T> {
  const response = await apiClient.post<T>(path, body, {
    ...config,
    validateStatus: () => true,
  });

  if (isSuccessfulStatus(response.status)) {
    return response.data;
  }

  const fallbackBaseURL = getLocalFallbackBaseURL();
  if (response.status === 404 && fallbackBaseURL) {
    const fallbackResponse = await apiClient.post<T>(
      `${fallbackBaseURL}${path}`,
      body,
      {
        ...config,
        validateStatus: () => true,
      },
    );

    if (isSuccessfulStatus(fallbackResponse.status)) {
      return fallbackResponse.data;
    }

    throw new Error(
      getErrorMessage(fallbackResponse.data, fallbackResponse.status),
    );
  }

  throw new Error(getErrorMessage(response.data, response.status));
}

export const forgivenessService = {
  getPresets: async (): Promise<ForgivenessPresetInfo[]> =>
    getWithFallback<ForgivenessPresetInfo[]>(apiPath("/forgiveness/presets")),

  getConfig: async (userId: string): Promise<ForgivenessConfig> =>
    getWithFallback<ForgivenessConfig>(apiPath("/forgiveness/config"), {
      params: { user_id: userId },
    }),

  updatePreset: async (
    userId: string,
    preset: ForgivenessPreset,
  ): Promise<ForgivenessConfig> =>
    postWithFallback<ForgivenessConfig>(
      apiPath("/forgiveness/config/preset"),
      { preset },
      { params: { user_id: userId } },
    ),

  updateCustomParams: async (
    userId: string,
    payload: UpdateForgivenessCustomParamsRequest,
  ): Promise<ForgivenessConfig> =>
    postWithFallback<ForgivenessConfig>(
      apiPath("/forgiveness/config/custom"),
      payload,
      { params: { user_id: userId } },
    ),
};
