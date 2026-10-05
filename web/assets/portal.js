"use strict";
const { $, date, message } = C,
  pattern = /^[\w-]{64}$/;
let token = "",
  accessEpoch = 0;
try {
  token = pattern.test(location.hash.slice(1))
    ? location.hash.slice(1)
    : sessionStorage.getItem("clarity_access") || "";
  if (pattern.test(token)) sessionStorage.setItem("clarity_access", token);
  else token = "";
} catch (_) {
  token = pattern.test(location.hash.slice(1)) ? location.hash.slice(1) : "";
}
history.replaceState(null, "", "/portal");
function api(path, method = "GET", data) {
  return C.api(path, method, data, { Authorization: "Bearer " + token });
}
function accessNeeded() {
  $("accessPanel").hidden = false;
  $("patientPanel").hidden = true;
}
function clear() {
  accessEpoch += 1;
  token = "";
  try {
    sessionStorage.removeItem("clarity_access");
  } catch (_) {}
  $("plan").textContent = "";
  $("signature").textContent = "";
  $("feedbackHistory").replaceChildren();
  for (const id of [
    "caseId",
    "reviewNote",
    "paymentStatus",
    "completed",
    "nextCheckin",
    "expiry",
    "product",
  ])
    $(id).textContent = "";
  $("checkinNote").value = "";
  $("welcome").textContent = "Your next step, made clear.";
  accessNeeded();
}
async function refresh() {
  const epoch = accessEpoch;
  if (!token) {
    accessNeeded();
    return;
  }
  try {
    const c = await api("/api/portal");
    if (epoch !== accessEpoch || !token) return;
    $("accessPanel").hidden = true;
    $("patientPanel").hidden = false;
    $("welcome").textContent = "Hello, " + c.name + ".";
    $("status").textContent = c.status.replaceAll("_", " ");
    $("product").textContent = c.product;
    $("caseId").textContent = "Case " + c.case_id;
    $("reviewNote").textContent =
      c.review_note ||
      "Your intake is awaiting practitioner review. Support confirms availability before payment. No plan is published without approval.";
    $("paymentStatus").textContent = c.paid
      ? "Payment confirmed by the provider."
      : c.amount === 0
        ? "This report review is free."
        : c.can_pay
          ? "Your routine is approved. Payment ₹" + c.amount / 100 + "."
          : !c.payment_enabled
            ? "Online payment is unavailable. Contact support before starting a paid service."
            : "Payment becomes available after contact verification and plan approval.";
    $("payButton").hidden = !c.can_pay;
    $("planPanel").hidden = !c.plan;
    $("plan").textContent = c.plan;
    $("signature").textContent = c.signature.name
      ? "Reviewed by " +
        c.signature.name +
        " · " +
        c.signature.credential +
        " · Version " +
        c.plan_version +
        " · " +
        date(c.signature.at)
      : "";
    $("whatsappOptIn").checked = c.whatsapp_opt_in;
    $("expiry").textContent =
      "Case expiry: " +
      new Date(c.expires_at * 1000).toLocaleDateString() +
      ". Delete sooner if you wish.";
    $("checkinPanel").hidden = !c.checkin_days.length;
    $("completed").textContent =
      "Completed: " + (c.completed_days.join(", ") || "none yet");
    const remaining = c.checkin_days.filter(
        (d) => !c.completed_days.includes(d),
      ),
      due = remaining.filter(
        (d) => Date.now() >= (c.activated_at + d * 86400) * 1000,
      );
    $("day").replaceChildren();
    for (const day of due) {
      const opt = C.el("option", "Day " + day);
      opt.value = day;
      $("day").append(opt);
    }
    $("checkinForm").hidden = !due.length;
    const history = c.checkin_history || [];
    $("feedbackPanel").hidden = history.length === 0;
    $("feedbackHistory").replaceChildren();
    for (const check of history) {
      const row = C.el("div", undefined, "task");
      row.append(
        C.el(
          "strong",
          "Day " + check.day + " · " + check.adherence.replaceAll("_", " "),
        ),
      );
      if (check.note) row.append(C.el("p", check.note));
      row.append(
        C.el(
          "p",
          check.feedback || "Your practitioner has not yet posted feedback.",
          "muted",
        ),
      );
      if (check.reviewed_at)
        row.append(C.el("small", "Reviewed " + date(check.reviewed_at)));
      $("feedbackHistory").append(row);
    }
    $("nextCheckin").textContent =
      remaining.length && !due.length
        ? "Next check-in: " +
          new Date(
            (c.activated_at + remaining[0] * 86400) * 1000,
          ).toLocaleDateString()
        : remaining.length
          ? ""
          : "All scheduled check-ins submitted.";
  } catch (e) {
    if (epoch !== accessEpoch) return;
    message(e.message, true);
    accessNeeded();
  }
}
$("refreshPortal").addEventListener("click", refresh);
$("forgetDevice").addEventListener("click", () => {
  clear();
  message("Access cleared from this device. Use your saved link to return.");
});
$("accessForm").addEventListener("submit", (e) => {
  e.preventDefault();
  try {
    const url = new URL($("accessLink").value.trim());
    if (
      url.origin !== location.origin ||
      url.pathname !== "/portal" ||
      !pattern.test(url.hash.slice(1))
    )
      throw Error();
    token = url.hash.slice(1);
    accessEpoch += 1;
    try {
      sessionStorage.setItem("clarity_access", token);
    } catch (_) {}
    $("accessLink").value = "";
    message("");
    refresh();
  } catch (_) {
    message("Paste a valid private access link for this website.", true);
  }
});
$("copyLink").addEventListener("click", () =>
  C.busy($("copyLink"), async () => {
    await navigator.clipboard.writeText(location.origin + "/portal#" + token);
    message("Private link copied. Store it safely.");
  }),
);
$("payButton").addEventListener("click", () =>
  C.busy($("payButton"), async () => {
    const data = await api("/api/checkout", "POST"),
      url = new URL(data.checkout_url);
    if (url.protocol !== "https:" || url.hostname !== "rzp.io")
      throw Error("Unexpected payment link. Contact support.");
    location.assign(url.href);
  }),
);
$("checkinForm").addEventListener("submit", (e) => {
  e.preventDefault();
  C.busy(e.currentTarget.querySelector("button"), async () => {
    const data = await api("/api/portal/checkins", "POST", {
      day: Number($("day").value),
      adherence: $("adherence").value,
      note: $("checkinNote").value,
    });
    $("checkinNote").value = "";
    message(data.message);
    await refresh();
  });
});
$("preferenceForm").addEventListener("submit", (e) => {
  e.preventDefault();
  C.busy(e.currentTarget.querySelector("button"), async () => {
    await api("/api/portal/notification-preference", "POST", {
      whatsapp_opt_in: $("whatsappOptIn").checked,
    });
    message("Preference saved.");
  });
});
$("deleteData").addEventListener("click", () =>
  C.busy($("deleteData"), async () => {
    if (
      !confirm(
        "Delete your intake, plan, check-ins and access link? This cannot be undone. Separate payment records may remain.",
      )
    )
      return;
    const data = await api("/api/portal/data", "DELETE");
    clear();
    message(data.message);
  }),
);
C.api("/api/public-config")
  .then(
    (c) =>
      ($("support").textContent = c.support_email
        ? "Support: " + c.support_email
        : "Support details will be published before launch."),
  )
  .catch(() => {});
refresh();
