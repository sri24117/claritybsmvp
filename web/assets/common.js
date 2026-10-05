"use strict";
window.C = {
  $(id) {
    return document.getElementById(id);
  },
  el(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  },
  date(n) {
    return n ? new Date(n * 1000).toLocaleString() : "—";
  },
  message(text, error = false) {
    const e = document.getElementById("message");
    e.textContent = text;
    e.classList.toggle("error", error);
  },
  async api(path, method = "GET", data, headers = {}) {
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), 30000);
    try {
      const r = await fetch(path, {
        method,
        credentials: "same-origin",
        signal: controller.signal,
        headers: { "Content-Type": "application/json", ...headers },
        ...(data === undefined ? {} : { body: JSON.stringify(data) }),
      });
      if (!(r.headers.get("content-type") || "").includes("application/json"))
        throw Error("Service temporarily unavailable.");
      const body = await r.json();
      if (!r.ok) {
        const e = Error(
          typeof body.detail === "string"
            ? body.detail
            : "Request could not be completed.",
        );
        e.status = r.status;
        throw e;
      }
      return body;
    } catch (e) {
      if (e.name === "AbortError")
        throw Error("Request timed out. Refresh before retrying a change.");
      throw e;
    } finally {
      clearTimeout(timer);
    }
  },
  async busy(button, fn) {
    button.disabled = true;
    try {
      await fn();
    } catch (e) {
      this.message(e.message, true);
    } finally {
      button.disabled = false;
    }
  },
  field(label, id, tag = "input", attributes = {}) {
    const l = this.el("label", label),
      e = this.el(tag);
    e.id = id;
    for (const [k, v] of Object.entries(attributes)) e.setAttribute(k, v);
    l.htmlFor = id;
    l.append(e);
    return { label: l, input: e };
  },
};
