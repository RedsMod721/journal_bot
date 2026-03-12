import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8002";
export const API_PREFIX = import.meta.env.VITE_API_PREFIX || "/api";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor (add auth token when available)
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("auth_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor (handle errors globally)
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("auth_token");
      // Optional: redirect to login
      // window.location.href = "/login";
    }

    const isNetworkError = !error.response && error.code;
    const message = isNetworkError
      ? `Network error: cannot reach API at ${API_BASE_URL}. Is backend running?`
      : error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message ||
        "An error occurred";

    return Promise.reject(new Error(message));
  }
);

export function apiPath(path: string): string {
  const normalizedPrefix = API_PREFIX.endsWith("/")
    ? API_PREFIX.slice(0, -1)
    : API_PREFIX;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedPrefix}${normalizedPath}`;
}

export default apiClient;
