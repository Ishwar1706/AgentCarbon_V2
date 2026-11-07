const BASE = (import.meta.env.VITE_API_URL || "") + "/api/v1";
let token = localStorage.getItem("ac_token") || "";
let onUnauthorized = () => {};

export const setToken = (t) => {
  token = t || "";
  t ? localStorage.setItem("ac_token", t) : localStorage.removeItem("ac_token");
};
export const setUnauthorizedHandler = (fn) => (onUnauthorized = fn);

async function request(method, path, { params, body, form, raw } = {}) {
  // company not chosen yet (still loading): skip instead of sending a request the API must reject
  if (params && "company_id" in params && !params.company_id) return null;
  const url = new URL(BASE + path, window.location.origin);
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  });
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(url, { method, headers, body: payload });
  if (res.status === 401 && token && !path.startsWith("/auth/login")) onUnauthorized();
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data);
    } catch {}
    throw new Error(message);
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

export const api = {
  get: (p, params) => request("GET", p, { params }),
  post: (p, body, params) => request("POST", p, { body, params }),
  patch: (p, body, params) => request("PATCH", p, { body, params }),
  del: (p, params) => request("DELETE", p, { params }),
  upload: (p, form, params) => request("POST", p, { form, params }),
  login: async (email, password) => {
    const form = new URLSearchParams({ username: email, password });
    const res = await fetch(BASE + "/auth/login", { method: "POST", body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Sign-in failed");
    return data;
  },
  blob: async (p, params) => (await request("GET", p, { params, raw: true })).blob(),
};

export async function downloadFile(path, params, filename) {
  const blob = await api.blob(path, params);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
export async function openFile(path, params, type = "text/html") {
  const blob = await api.blob(path, params);
  window.open(URL.createObjectURL(new Blob([blob], { type })), "_blank");
}
