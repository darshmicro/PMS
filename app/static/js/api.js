/* Thin fetch wrapper for the PMS API. Session auth is a signed cookie
   (app/core/session.py), so every request goes same-origin with
   credentials included and no bearer token to manage. */

const PMS = (() => {
  async function request(method, path, body) {
    const opts = {
      method,
      credentials: "same-origin",
      headers: {},
    };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    if (res.status === 401) {
      // Session missing/expired - back to login, preserving nothing sensitive.
      if (!location.pathname.endsWith("/login.html")) {
        location.href = "login.html";
      }
      throw new Error("Not authenticated");
    }
    let data = null;
    const text = await res.text();
    if (text) {
      try { data = JSON.parse(text); } catch (e) { data = text; }
    }
    if (!res.ok) {
      const detail = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
      const err = new Error(detail);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  return {
    get: (path) => request("GET", path),
    post: (path, body) => request("POST", path, body === undefined ? {} : body),
    put: (path, body) => request("PUT", path, body === undefined ? {} : body),
    me: () => request("GET", "/auth/me"),
    logout: () => request("POST", "/auth/logout"),
  };
})();
