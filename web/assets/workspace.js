"use strict";
const { $, el, date, message } = C;
let sessionEpoch = 0;
let user = null,
  csrf = "",
  cases = [],
  selected = null,
  users = [];
async function api(path, method = "GET", data) {
  const epoch = sessionEpoch;
  try {
    const result = await C.api(path, method, data, { "X-CSRF-Token": csrf });
    if (epoch !== sessionEpoch)
      throw Error("Session changed. Please sign in again.");
    return result;
  } catch (e) {
    if (
      epoch === sessionEpoch &&
      e.status === 401 &&
      path !== "/api/auth/login"
    )
      showLogin();
    throw e;
  }
}
function showLogin() {
  sessionEpoch += 1;
  user = null;
  cases = [];
  users = [];
  csrf = "";
  selected = null;
  $("workspace").hidden = true;
  $("loginPanel").hidden = false;
  $("logout").hidden = true;
  $("refresh").hidden = true;
  $("signedInAs").textContent = "";
  $("caseDetail").hidden = true;
  $("caseList").replaceChildren();
  $("intakeDetails").replaceChildren();
  $("planText").value = "";
  $("caseDetail")
    .querySelectorAll("input,textarea")
    .forEach((input) => {
      input.value = "";
      if (input.type === "checkbox") input.checked = false;
    });
  for (const id of [
    "caseName",
    "caseId",
    "planSummary",
    "contactStatus",
    "signatureInfo",
    "paymentInfo",
    "jobs",
    "checkins",
    "recoveredLink",
    "versionInfo",
  ])
    $(id).textContent = "";
}
async function signedIn(data) {
  sessionEpoch += 1;
  user = data.user;
  csrf = data.csrf;
  $("loginPanel").hidden = true;
  $("workspace").hidden = false;
  $("logout").hidden = false;
  $("refresh").hidden = false;
  $("signedInAs").textContent = user.name + " · " + user.role;
  $("password").value = "";
  await refresh();
}
async function refresh() {
  [cases, users] = await Promise.all([
    api("/api/staff/cases"),
    api("/api/staff/users"),
  ]);
  const health = await api("/api/health");
  $("systemHealth").textContent =
    "Database: " +
    health.database +
    " · Worker: " +
    health.worker +
    " · Notifications: " +
    health.notification_mode +
    " · Payments: " +
    health.payment_mode +
    " · Payment actions: " +
    health.payment_actions;
  renderQueue();
  if (selected && cases.some((c) => c.id === selected.id))
    await selectCase(selected.id);
}
function renderQueue() {
  const query = $("filter").value.toLowerCase(),
    root = $("caseList");
  root.replaceChildren();
  const list = cases.filter((c) =>
    [c.name, c.lane, c.status, c.product]
      .join(" ")
      .toLowerCase()
      .includes(query),
  );
  $("queueCount").textContent = list.length + " cases (newest 200)";
  for (const c of list) {
    const b = el(
      "button",
      undefined,
      "case-button" + (selected?.id === c.id ? " selected" : ""),
    );
    b.append(
      el("strong", c.name),
      el(
        "small",
        c.product +
          " · " +
          c.status.replaceAll("_", " ") +
          (c.paid ? " · paid" : ""),
      ),
    );
    b.addEventListener("click", () =>
      selectCase(c.id).catch((e) => message(e.message, true)),
    );
    root.append(b);
  }
  if (!list.length) root.append(el("p", "No cases to show.", "muted"));
}
async function selectCase(id) {
  selected = await api("/api/staff/cases/" + id);
  const c = selected;
  $("emptyCase").hidden = true;
  $("caseDetail").hidden = false;
  $("caseName").textContent = c.intake.name;
  $("caseId").textContent = c.id + " · " + date(c.created_at);
  $("caseStatus").textContent = c.status.replaceAll("_", " ");
  $("planSummary").textContent = c.product + " · Adult age " + c.intake.age;
  $("assignment").hidden = user.role !== "admin";
  $("assignee").replaceChildren();
  for (const u of users) {
    const opt = el(
      "option",
      u.name + (u.credential ? " · verified practitioner" : " · operations"),
    );
    opt.value = u.id;
    opt.selected = c.assigned_to === u.id;
    $("assignee").append(opt);
  }
  const root = $("intakeDetails");
  root.replaceChildren();
  for (const [k, v] of Object.entries(c.intake)) {
    if (k === "intake_key") continue;
    const row = el("div", undefined, "intake-row");
    row.append(
      el("b", k.replaceAll("_", " ")),
      el("span", v === null ? "Not provided" : String(v)),
    );
    root.append(row);
  }
  root.append(el("p", "Consent recorded: " + date(c.consent_at), "muted"));
  $("contactStatus").textContent = c.contact_verified
    ? "Verified · " + (c.contact_verification.note || "")
    : "Verify contact ownership before approval or messaging.";
  $("verificationNote").value = "";
  $("recoveryNote").value = "";
  $("recoveredLink").textContent = "";
  $("reviewNote").value = c.review.note || "";
  $("disposition").value = c.status === "referred" ? "referred" : "eligible";
  $("planText").value = c.plan;
  $("confirmReviewed").checked = false;
  $("versionInfo").textContent =
    "Saved version " +
    c.version +
    " · Approved version " +
    c.approved_version +
    ". Approval applies to saved content.";
  $("signatureInfo").textContent = c.signature.name
    ? "Reviewed by " +
      c.signature.name +
      " · " +
      c.signature.credential +
      " · " +
      date(c.signature.at)
    : "No current approval.";
  for (const id of ["reviewForm", "draftForm", "approveForm"])
    $(id)
      .querySelectorAll("button")
      .forEach((b) => (b.disabled = !user.credential));
  $("paymentInfo").textContent =
    "Payment: " +
    c.payment_status +
    " · Attempt: " +
    (c.payment_attempt_id || "none") +
    " · Refunded: ₹" +
    c.refunded_amount / 100 +
    " · Portal since: " +
    date(c.activated_at) +
    " · First patient view: " +
    date(c.viewed_at);
  $("reconcileButton").hidden =
    c.product === "report" || c.payment_status === "none";
  renderJobs(c);
  renderCheckins(c);
  renderQueue();
}
function taskForm(row, title, buttonTitle, callback) {
  const form = el("form"),
    field = C.field(title, "note-" + crypto.randomUUID(), "textarea", {
      required: "",
      minlength: "20",
      maxlength: "1000",
    }),
    button = el("button", buttonTitle, "secondary");
  button.type = "submit";
  form.append(field.label, button);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    run(button, () => callback(field.input.value));
  });
  row.append(form);
}
function renderJobs(c) {
  const root = $("jobs");
  root.replaceChildren();
  if (!c.jobs.length)
    root.append(
      el(
        "p",
        "Tasks are scheduled when the approved plan becomes available.",
        "muted",
      ),
    );
  for (const j of c.jobs) {
    const row = el("div", undefined, "task");
    row.append(
      el(
        "strong",
        (j.day ? "Day " + j.day + " check-in" : "Plan notification") +
          " · " +
          j.state,
      ),
      el("p", "Due " + date(j.due_at) + " · " + j.reason, "muted"),
    );
    if (["manual", "failed", "uncertain"].includes(j.state))
      taskForm(
        row,
        "Evidence of actual completion",
        "Confirm completion",
        (note) =>
          api(
            "/api/staff/cases/" + c.id + "/jobs/" + j.id + "/manual-complete",
            "POST",
            { note },
          ),
      );
    root.append(row);
  }
}
function renderCheckins(c) {
  const root = $("checkins");
  root.replaceChildren();
  if (!c.checkins.length)
    root.append(el("p", "No submitted check-ins yet.", "muted"));
  for (const check of c.checkins) {
    const row = el("div", undefined, "task");
    row.append(
      el(
        "strong",
        "Day " + check.day + " · " + check.data.adherence.replaceAll("_", " "),
      ),
      el("p", check.data.note || "No additional note."),
      el("small", date(check.created_at)),
    );
    if (check.reviewed_at)
      row.append(
        el(
          "p",
          "Reviewed " +
            date(check.reviewed_at) +
            " · " +
            (check.data.review?.note || ""),
          "muted",
        ),
      );
    else if (user.credential)
      taskForm(
        row,
        "Patient-visible feedback / action taken",
        "Record review",
        (note) =>
          api(
            "/api/staff/cases/" + c.id + "/checkins/" + check.id + "/review",
            "POST",
            { note },
          ),
      );
    root.append(row);
  }
}
async function run(button, fn) {
  await C.busy(button, async () => {
    await fn();
    message("Saved.");
    if (user) await refresh();
  });
}
function bind(id, fn) {
  $(id).addEventListener("submit", (e) => {
    e.preventDefault();
    run($(id).querySelector("button"), fn);
  });
}
bind("loginForm", async () =>
  signedIn(
    await api("/api/auth/login", "POST", {
      email: $("email").value,
      password: $("password").value,
    }),
  ),
);
bind("verifyForm", () =>
  api("/api/staff/cases/" + selected.id + "/verify-contact", "POST", {
    note: $("verificationNote").value,
  }),
);
bind("reviewForm", () =>
  api("/api/staff/cases/" + selected.id + "/review", "POST", {
    disposition: $("disposition").value,
    note: $("reviewNote").value,
  }),
);
bind("draftForm", () =>
  api("/api/staff/cases/" + selected.id + "/plan", "PUT", {
    text: $("planText").value,
  }),
);
bind("approveForm", () => {
  if ($("planText").value !== selected.plan)
    throw Error("Save your edits before approving.");
  return api("/api/staff/cases/" + selected.id + "/approve", "POST", {
    version: selected.version,
    confirm_reviewed: $("confirmReviewed").checked,
  });
});
$("recoverForm").addEventListener("submit", (e) => {
  e.preventDefault();
  C.busy($("recoverForm").querySelector("button"), async () => {
    const data = await api(
      "/api/staff/cases/" + selected.id + "/rotate-access-link",
      "POST",
      { note: $("recoveryNote").value },
    );
    $("recoveredLink").textContent = data.portal_url;
    message(
      "Old link revoked. Share the replacement privately after verifying identity.",
    );
  });
});
$("assignButton").addEventListener("click", () =>
  run($("assignButton"), () =>
    api("/api/staff/cases/" + selected.id + "/assign", "POST", {
      user_id: $("assignee").value,
    }),
  ),
);
$("reconcileButton").addEventListener("click", () =>
  run($("reconcileButton"), () =>
    api("/api/staff/cases/" + selected.id + "/payment-reconcile", "POST"),
  ),
);
$("logout").addEventListener("click", () =>
  run($("logout"), async () => {
    await api("/api/auth/logout", "POST");
    showLogin();
  }),
);
$("refresh").addEventListener("click", () =>
  refresh().catch((e) => message(e.message, true)),
);
$("filter").addEventListener("input", renderQueue);
api("/api/auth/me")
  .then(signedIn)
  .catch(() => {
    if (!user) showLogin();
  });
