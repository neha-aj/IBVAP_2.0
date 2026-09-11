import { tokenStorage } from "../utils/tokenStorage";

// "127.0.0.1", not "localhost" -- on this Docker Desktop setup, nginx's
// published port only ever binds an IPv4 socket, but browsers (and curl)
// resolve "localhost" to IPv6 (::1) first. That connection gets accepted at
// the OS/Docker-proxy level (so it doesn't fail fast) but never reaches the
// container, which black-holes every request until it times out as a
// generic "Failed to fetch" -- no CORS or backend problem at all. Pin the
// literal IPv4 address so this can't happen again, regardless of a given
// machine's IPv6 config.
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8080/api/v1";

// A handful of URLs the backend returns (camera stream mjpegUrl) are relative
// to the gateway's own root, not `/api/v1` -- e.g. `/stream/{id}/mjpeg`. This
// is that root, for building an absolute URL to hand to a plain <img src>.
export const GATEWAY_ORIGIN = new URL(BASE_URL).origin;

// Thrown for every non-2xx response, normalized from the backend's RFC7807
// problem+json body (API Spec §10) so calling code can branch on `.status`
// without re-parsing the response shape itself.
export class ApiError extends Error {
  constructor({ status, title, detail, type, traceId }) {
    super(detail || title || "Request failed");
    this.name = "ApiError";
    this.status = status;
    this.title = title;
    this.detail = detail;
    this.type = type;
    this.traceId = traceId;
  }
}

function buildUrl(path, params) {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, value);
      }
    }
  }
  // BASE_URL is already absolute (http://...), so strip the origin the
  // `URL` constructor added when resolving a relative second argument.
  return BASE_URL.startsWith("http") ? url.toString() : url.pathname + url.search;
}

async function parseError(response) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON error body (e.g. nginx's own 502/504 HTML page) -- fall
    // through to the generic status-only error below.
  }
  return new ApiError({
    status: response.status,
    title: body?.title || response.statusText,
    detail: body?.detail,
    type: body?.type,
    traceId: body?.traceId,
  });
}

let refreshInFlight = null;

// One-shot, de-duplicated token refresh: several requests failing with 401
// at once (e.g. a page that fires multiple GETs on mount) must not each
// trigger their own /auth/refresh call.
async function refreshAccessToken() {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refreshToken = tokenStorage.getRefreshToken();
      if (!refreshToken) throw new Error("No refresh token");
      const response = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refreshToken }),
      });
      if (!response.ok) throw new Error("Refresh failed");
      const data = await response.json();
      tokenStorage.setTokens({ accessToken: data.accessToken, refreshToken: data.refreshToken });
      return data.accessToken;
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

function isAuthEndpoint(path) {
  return path.startsWith("/auth/login") || path.startsWith("/auth/refresh");
}

async function request(method, path, { params, body, isFormData = false, retry = true } = {}) {
  const headers = {};
  // FormData (file upload) must NOT get a manual Content-Type -- the
  // browser sets one itself with the correct multipart boundary.
  if (!isFormData) headers["Content-Type"] = "application/json";
  const accessToken = tokenStorage.getAccessToken();
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const response = await fetch(buildUrl(path, params), {
    method,
    headers,
    body: isFormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401 && retry && !isAuthEndpoint(path)) {
    try {
      await refreshAccessToken();
      return request(method, path, { params, body, isFormData, retry: false });
    } catch {
      tokenStorage.clear();
      // AuthContext listens for this to clear its state and redirect to
      // /login -- api.js can't import the context directly without a
      // circular dependency (the context itself calls this client).
      window.dispatchEvent(new CustomEvent("ibvap:auth-expired"));
      throw new ApiError({ status: 401, title: "Session expired", detail: "Please log in again." });
    }
  }

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return null;
  return response.json();
}

export const api = {
  get: (path, params) => request("GET", path, { params }),
  post: (path, body) => request("POST", path, { body }),
  postForm: (path, formData) => request("POST", path, { body: formData, isFormData: true }),
  put: (path, body) => request("PUT", path, { body }),
  patch: (path, body) => request("PATCH", path, { body }),
  delete: (path) => request("DELETE", path),
};
