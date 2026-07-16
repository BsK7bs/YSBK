import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

let _accessToken = null;
let _onUnauthorized = null;
let _refreshHandler = null;
let _isRefreshing = false;
let _queue = [];

export function setAccessToken(token) {
  _accessToken = token || null;
}

export function setOnUnauthorized(fn) {
  _onUnauthorized = fn;
}

export function setRefreshHandler(fn) {
  _refreshHandler = fn;
}

async function _refreshOnce() {
  if (_isRefreshing) {
    return new Promise((resolve, reject) => _queue.push({ resolve, reject }));
  }
  _isRefreshing = true;
  try {
    if (!_refreshHandler) throw new Error("no refresh handler");
    const newToken = await _refreshHandler();
    _queue.forEach(({ resolve }) => resolve(newToken));
    _queue = [];
    return newToken;
  } catch (err) {
    _queue.forEach(({ reject }) => reject(err));
    _queue = [];
    throw err;
  } finally {
    _isRefreshing = false;
  }
}

api.interceptors.request.use((cfg) => {
  if (_accessToken) {
    cfg.headers = cfg.headers || {};
    cfg.headers.Authorization = `Bearer ${_accessToken}`;
  }
  return cfg;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config || {};
    const status = error.response?.status;
    if (status === 401 && !original._retry && _refreshHandler) {
      original._retry = true;
      try {
        const newToken = await _refreshOnce();
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return api.request(original);
      } catch (e) {
        if (_onUnauthorized) _onUnauthorized();
        return Promise.reject(error);
      }
    }
    return Promise.reject(error);
  },
);

export function wsUrl(pathWithQuery) {
  // Derive ws(s)://host/api/... from REACT_APP_BACKEND_URL
  const backend = BACKEND_URL || window.location.origin;
  const url = new URL(backend);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return `${url.origin}/api${pathWithQuery}`;
}
