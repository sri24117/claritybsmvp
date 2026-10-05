"use strict";
const fs = require("fs"),
  vm = require("vm"),
  assert = require("node:assert/strict"),
  crypto = require("node:crypto");
class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.value = "";
    this.checked = false;
    this.dataset = {};
    this.style = {};
    this.textContent = "";
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  append(...items) {
    this.children.push(...items);
  }
  replaceChildren(...items) {
    this.children = items;
  }
  setAttribute() {}
  focus() {}
  reportValidity() {
    return true;
  }
  querySelector() {
    return this.button || (this.button = new Element("button"));
  }
}
function context(response, type = "application/json") {
  const elements = new Map(),
    requests = [],
    document = {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, new Element());
        return elements.get(id);
      },
      createElement(tag) {
        return new Element(tag);
      },
      querySelector() {
        return new Element();
      },
      querySelectorAll() {
        return [];
      },
      addEventListener() {},
      body: new Element("body"),
    };
  const ctx = vm.createContext({
    document,
    crypto: crypto.webcrypto,
    AbortController,
    setTimeout,
    clearTimeout,
    Map,
    fetch: async (path, options = {}) => {
      requests.push({ path, options });
      return {
        ok: true,
        headers: {
          get: () =>
            path === "/api/public-config" ? "application/json" : type,
        },
        json: async () =>
          path === "/api/public-config"
            ? {
                intake_enabled: true,
                consent_version: "2026-09-30-v1",
                environment: "test",
              }
            : response,
      };
    },
  });
  vm.runInContext(fs.readFileSync("web/assets/landing.js", "utf8"), ctx);
  vm.runInContext(
    "serviceConfig={intake_enabled:true,consent_version:'2026-09-30-v1'}",
    ctx,
  );
  return { ctx, document, requests };
}
function fill(d, p) {
  for (const [key, value] of Object.entries({
    Name: "Synthetic Person",
    Phone: "+919999999999",
    Age: "35",
    Screen: "review",
    A1c: "6.4",
    Fbs: "",
    Ppbs: "",
    Notes: "Synthetic context",
    Goal: "Healthier everyday eating",
    Measurements: "",
    Food: "Vegetarian",
    Allergies: "None",
    Routine: "Synthetic routine",
  }))
    d.getElementById(p + key).value = value;
  d.getElementById(p + "Consent").checked = true;
}
(async () => {
  for (const [type, prefix, id, result] of [
    ["inline", "in", "reportForm", "inlineResult"],
    ["report", "ri", "reportIntakeForm", "reportResult"],
    ["diet", "di", "dietForm", "dietResult"],
  ]) {
    const { ctx, document, requests } = context({
      case_id: "synthetic",
      review_required: true,
      portal_url: "/portal#" + "A".repeat(64),
      message: "Synthetic saved intake",
    });
    fill(document, prefix);
    const form = document.getElementById(id);
    ctx.event = { preventDefault() {}, currentTarget: form };
    await vm.runInContext(`submitIntake(event,'${type}')`, ctx);
    const posts = requests.filter((r) => r.options.method === "POST");
    assert.equal(posts.length, 1);
    assert.equal(
      posts[0].path,
      type === "diet" ? "/api/intake/diet" : "/api/intake/report",
    );
    const data = JSON.parse(posts[0].options.body);
    assert.equal(data.age, 35);
    assert.equal(data.consent, true);
    assert.equal(data.health_screening, "review");
    assert.equal(data.review_required, undefined);
    assert.equal(form.dataset.complete, "true");
    assert.equal(document.getElementById(result).children[2].tagName, "a");
    await vm.runInContext(`submitIntake(event,'${type}')`, ctx);
    assert.equal(requests.filter((r) => r.options.method === "POST").length, 1);
  }
  for (const contentType of ["application/json", "text/html"]) {
    const { ctx, document, requests } = context({}, contentType);
    fill(document, "di");
    const form = document.getElementById("dietForm");
    ctx.event = { preventDefault() {}, currentTarget: form };
    await vm.runInContext("submitIntake(event,'diet')", ctx);
    assert.equal(form.dataset.complete, undefined);
    assert.equal(
      requests.some((r) => r.path === "/api/checkout"),
      false,
    );
    assert.equal(form.querySelector().disabled, false);
  }
  {
    const { ctx, document } = context({});
    vm.runInContext(
      "showResult('reportResult','<img onerror=attack()>','<script>attack()</script>')",
      ctx,
    );
    assert.equal(
      document.getElementById("reportResult").children[0].textContent,
      "<img onerror=attack()>",
    );
    assert.equal(
      document.getElementById("reportResult").children[0].tagName,
      "h4",
    );
  }
  const html = fs.readFileSync("web/index.html", "utf8"),
    ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(
    /Hyderabad|upload can be connected|Generate Free Explanation|API_BASE/i.test(
      html,
    ),
    false,
  );
  assert.match(html, /prefers-reduced-motion/);
  assert.match(html, /Instrument\+Serif/);
  for (const name of ["common", "landing", "workspace", "portal"])
    assert.equal(
      fs
        .readFileSync("web/assets/" + name + ".js", "utf8")
        .includes("innerHTML"),
      false,
    );
  console.log(
    "Frontend checks passed: both report forms, diet, idempotent retries, response validation, safe rendering and HTML integrity.",
  );
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
