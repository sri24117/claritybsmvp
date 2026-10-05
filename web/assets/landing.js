"use strict";
let selectedPlan = "routine14",
  serviceConfig = null;
const modalFocus = new Map();
async function jsonRequest(path, options = {}) {
  const controller = new AbortController(),
    timer = setTimeout(() => controller.abort(), 25000);
  try {
    const r = await fetch(path, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    if (!(r.headers.get("content-type") || "").includes("application/json"))
      throw Error("The service is temporarily unavailable.");
    const data = await r.json();
    if (!r.ok)
      throw Error(
        typeof data.detail === "string"
          ? data.detail
          : "Please check your details.",
      );
    return data;
  } catch (e) {
    if (e.name === "AbortError")
      throw Error(
        "Request timed out. Retry once; your submission will not be duplicated.",
      );
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
async function loadConfig() {
  try {
    serviceConfig = await jsonRequest("/api/public-config");
    if (
      typeof serviceConfig.intake_enabled !== "boolean" ||
      typeof serviceConfig.consent_version !== "string"
    )
      throw Error();
    document.getElementById("launchNotice").textContent =
      serviceConfig.intake_enabled
        ? serviceConfig.environment === "production"
          ? "Adult nutrition support · Professional review before payment"
          : "Development preview — use synthetic details only."
        : "New submissions and payments are paused while our service is being prepared.";
    document
      .querySelectorAll("form button[type=submit]")
      .forEach((b) => (b.disabled = !serviceConfig.intake_enabled));
  } catch (_) {
    document.getElementById("launchNotice").textContent =
      "The service is temporarily unavailable. Please check back soon.";
  }
}
function go(id) {
  document
    .getElementById(id)
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
}
function openModal(id, selector) {
  modalFocus.set(id, document.activeElement);
  document.getElementById(id).classList.add("show");
  for (const tag of ["main", "nav", "footer"])
    document.querySelector(tag).inert = true;
  document.body.style.overflow = "hidden";
  document.querySelector(selector)?.focus();
}
function closeModal(id) {
  document.getElementById(id).classList.remove("show");
  if (!document.querySelector(".modal.show")) {
    for (const tag of ["main", "nav", "footer"])
      document.querySelector(tag).inert = false;
    document.body.style.overflow = "";
  }
  modalFocus.get(id)?.focus();
}
function openIntake(type, plan = "routine14") {
  selectedPlan = ["routine14", "support30"].includes(plan) ? plan : "routine14";
  document.getElementById("reportIntake").style.display =
    type === "report" ? "block" : "none";
  document.getElementById("dietIntake").style.display =
    type === "diet" ? "block" : "none";
  document
    .getElementById("intakeModal")
    .setAttribute(
      "aria-labelledby",
      type === "report" ? "intakeTitle" : "dietIntakeTitle",
    );
  openModal("intakeModal", type === "report" ? "#riName" : "#diName");
}
function openEnquiry(service) {
  const services = {
    "Nutrition support": ["diet", "routine14"],
    "General Diet support": ["diet", "routine14"],
    "Sugar Report Clarity": ["report", "routine14"],
    "14-Day Food Routine": ["diet", "routine14"],
    "30-Day Dietitian Support": ["diet", "support30"],
  };
  const choice = services[service];
  if (!choice) return;
  if (serviceConfig?.intake_enabled) {
    openIntake(...choice);
    return;
  }
  const message =
    "Hi Bavitha, I'd like to enquire about " + service + " through Clarity Blood Sugar.";
  window.open(
    "https://wa.me/919848713385?text=" + encodeURIComponent(message),
    "_blank",
    "noopener,noreferrer",
  );
}

function closeIntake() {
  closeModal("intakeModal");
}
function closeInfo() {
  closeModal("infoModal");
}
function showResult(id, title, message, url) {
  const root = document.getElementById(id);
  root.replaceChildren();
  const h = document.createElement("h4"),
    p = document.createElement("p");
  h.textContent = title;
  p.textContent = message;
  root.append(h, p);
  if (url && /^\/portal#[\w-]{64}$/.test(url)) {
    const a = document.createElement("a");
    a.href = url;
    a.textContent = "Open and save my private access link →";
    root.append(a);
    const warning = document.createElement("p");
    warning.textContent =
      "Keep this link private. Anyone with it can access your case.";
    root.append(warning);
  }
  root.classList.add("show");
}
function value(id) {
  return document.getElementById(id).value.trim();
}
function numeric(id) {
  return value(id) === "" ? null : Number(value(id));
}
async function submitIntake(event, type) {
  event.preventDefault();
  const form = event.currentTarget,
    prefix = type === "inline" ? "in" : type === "report" ? "ri" : "di",
    result =
      type === "inline"
        ? "inlineResult"
        : type === "report"
          ? "reportResult"
          : "dietResult";
  if (form.dataset.busy === "true" || form.dataset.complete === "true") return;
  if (!serviceConfig?.intake_enabled) {
    showResult(
      result,
      "Submissions paused",
      "Please check back when the service opens.",
    );
    return;
  }
  if (!form.reportValidity()) return;
  const payload = {
    intake_key: form.dataset.requestId || crypto.randomUUID(),
    name: value(prefix + "Name"),
    phone: value(prefix + "Phone"),
    age: numeric(prefix + "Age"),
    health_screening: value(prefix + "Screen"),
    consent: document.getElementById(prefix + "Consent").checked,
    consent_version: serviceConfig.consent_version,
    whatsapp_opt_in: document.getElementById(prefix + "WhatsApp").checked,
  };
  if (type === "diet")
    Object.assign(payload, {
      plan: selectedPlan,
      goal: value("diGoal"),
      measurements: value("diMeasurements"),
      food_preference: value("diFood"),
      allergies: value("diAllergies"),
      daily_routine: value("diRoutine"),
    });
  else {
    Object.assign(payload, {
      hba1c: numeric(prefix + "A1c"),
      fasting_sugar: numeric(prefix + "Fbs"),
      post_meal_sugar: numeric(prefix + "Ppbs"),
      sugar_unit: "mg/dL",
      notes: value(prefix + "Notes"),
    });
    if (
      [payload.hba1c, payload.fasting_sugar, payload.post_meal_sugar].every(
        (v) => v === null,
      )
    ) {
      showResult(
        result,
        "One value is needed",
        "Enter a supported value exactly as printed.",
      );
      return;
    }
  }
  form.dataset.requestId = payload.intake_key;
  form.dataset.busy = "true";
  const button = form.querySelector("button[type=submit]"),
    old = button.textContent;
  button.disabled = true;
  button.textContent = "Saving your intake…";
  try {
    const data = await jsonRequest(
      type === "diet" ? "/api/intake/diet" : "/api/intake/report",
      { method: "POST", body: JSON.stringify(payload) },
    );
    if (
      !data.case_id ||
      data.review_required !== true ||
      !/^\/portal#[\w-]{64}$/.test(data.portal_url || "") ||
      typeof data.message !== "string"
    )
      throw Error("Unexpected response. Contact support.");
    form.dataset.complete = "true";
    showResult(result, "Intake received", data.message, data.portal_url);
    button.textContent = "Saved — open your private portal";
  } catch (e) {
    showResult(result, "Please try again", e.message);
    button.disabled = false;
    button.textContent = old;
  } finally {
    form.dataset.busy = "false";
  }
}
function openInfo(type) {
  const c = serviceConfig || {},
    support = c.support_email
      ? "Contact " + c.support_email + "."
      : "Contact Bavitha Sri on WhatsApp at 9848713385 for enquiries and support.";
  const info = {
    privacy: [
      "Privacy notice",
      (c.business_name || "Clarity Blood Sugar") +
        " collects your name, phone, adult age and submitted health or routine details to review suitability, prepare the requested service, take eligible payments and support check-ins. Authorised staff can access your case. Health inputs, plans and check-ins are encrypted in the application database. Razorpay processes enabled payments. Optional WhatsApp reminders use Meta and contain no report values, plan text or private access token. We do not use your health details for advertising or model training. Cases expire after " +
        (c.retention_days || 90) +
        " days from intake or plan activation, whichever is later. Delete your case in your private portal. Separate payment records and provider-held records may remain. Encrypted backups expire within seven days under the backup procedure. " +
        support,
    ],
    terms: [
      "Service terms",
      "Adults 18+ only. Nutrition support requires practitioner suitability review and plan approval. The ₹299 14-day service includes check-ins on days 3, 7 and 14 and one progress review. The ₹999 base 30-day service includes check-ins on days 3, 7, 14, 21 and 30, two progress reviews and one routine adjustment. Any additional support and its fee must be agreed separately before it begins; additional support is not included in this checkout. Support confirms availability before payment. This service does not diagnose, prescribe, change medicines, offer unlimited chat or handle emergencies. Contact support to request cancellation/refund; before first plan viewing, request a full refund. After viewing, support reviews undelivered services and any partial refund. Refunds are handled through the payment provider. " +
        support,
    ],
    contact: [
      "Contact and support",
      support +
        " Keep your case ID for support. Severe or worsening symptoms need urgent medical care. This service is not monitored for emergencies.",
    ],
    deletion: [
      "Delete your data",
      "Use Delete my data in your private portal. Your intake, plan, check-ins, queued tasks and access link are removed from the active database. Separate payment/provider records may remain; backups expire within seven days. Lost your access link? Contact support to verify your identity. " +
        support,
    ],
  }[type];
  if (!info) return;
  const root = document.getElementById("infoContent"),
    h = document.createElement("h2"),
    p = document.createElement("p");
  h.id = "infoTitle";
  h.textContent = info[0];
  p.textContent = info[1];
  root.replaceChildren(h, p);
  openModal("infoModal", "#infoModal .modal-close");
}
document.addEventListener("keydown", (e) => {
  const modal =
    document.querySelector("#infoModal.show") ||
    document.querySelector("#intakeModal.show");
  if (!modal) return;
  if (e.key === "Escape")
    modal.id === "infoModal" ? closeInfo() : closeIntake();
  if (e.key === "Tab") {
    const items = [
      ...modal.querySelectorAll("button:not(:disabled),input,select,a[href]"),
    ].filter((el) => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0],
      last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    }
    if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
});
loadConfig();
