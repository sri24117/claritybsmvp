// Optional real-browser QA. Install playwright, @sparticuz/chromium and tar-fs for this test only.
const fs = require("fs"),
  path = require("path"),
  zlib = require("zlib"),
  os = require("os"),
  assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
process.chdir(path.resolve(__dirname, ".."));
const { chromium: PW, expect } = require(
  process.env.CLARITY_PLAYWRIGHT_MODULE || "playwright/test",
);
const chromiumModule =
  process.env.CLARITY_CHROMIUM_MODULE || require.resolve("@sparticuz/chromium");
const chromium = require(chromiumModule).default;
const tar = require(process.env.CLARITY_TAR_MODULE || "tar-fs");
async function prepareBrowser() {
  const source = path.resolve(path.dirname(chromiumModule), "../bin"),
    target = fs.mkdtempSync(path.join(os.tmpdir(), "claritybs-browser-")),
    binary = path.join(target, "chromium");
  fs.writeFileSync(
    binary,
    zlib.brotliDecompressSync(
      fs.readFileSync(path.join(source, "chromium.br")),
    ),
    { mode: 0o700 },
  );
  for (const [archive, folder] of [
    ["fonts.tar.br", "fonts"],
    ["swiftshader.tar.br", ""],
  ]) {
    const dest = path.join(target, folder);
    fs.mkdirSync(dest, { recursive: true });
    await new Promise((resolve, reject) => {
      const extract = tar.extract(dest, { chown: false });
      extract.on("finish", resolve);
      extract.on("error", reject);
      extract.end(
        zlib.brotliDecompressSync(fs.readFileSync(path.join(source, archive))),
      );
    });
  }
  return { target, binary };
}
(async () => {
  const server = spawn(
    process.env.CLARITY_TEST_PYTHON || "python",
    ["tests/preview_server.py"],
    { stdio: "ignore" },
  );
  let browser;
  try {
    for (let i = 0; i < 100; i++) {
      try {
        const r = await fetch("http://localhost:8000/health/live");
        if (r.ok) break;
      } catch (_) {}
      await new Promise((r) => setTimeout(r, 100));
    }
    const { target, binary } = await prepareBrowser();
    browser = await PW.launch({
      headless: true,
      executablePath: binary,
      args: chromium.args.filter(
        (a) => !["--single-process", "--in-process-gpu"].includes(a),
      ),
      env: {
        ...process.env,
        FONTCONFIG_PATH: "/etc/fonts",
        LD_LIBRARY_PATH: target,
      },
    });
    const context = await browser.newContext({
        viewport: { width: 1440, height: 1000 },
      }),
      errors = [];
    context.on("page", (p) => p.on("pageerror", (e) => errors.push(e.message)));
    const page = await context.newPage();
    await page.goto("http://localhost:8000/", { waitUntil: "networkidle" });
    await expect(page.locator("#launchNotice")).toContainText("synthetic");
    await expect(page.locator("#reportForm button[type=submit]")).toBeEnabled();
    fs.mkdirSync("test-results", { recursive: true });
    await page.screenshot({
      path: "test-results/landing-desktop.png",
      fullPage: true,
    });
    for (const [id, value] of Object.entries({
      inName: "Synthetic Browser Person",
      inPhone: "+919999999999",
      inAge: "35",
      inA1c: "6.4",
      inNotes: "Synthetic browser QA only",
    }))
      await page.locator("#" + id).fill(value);
    await page.locator("#inScreen").selectOption("review");
    await page.locator("#inConsent").check();
    await page.locator("#reportForm button[type=submit]").click();
    await expect(page.locator("#inlineResult")).toContainText(
      "Intake received",
    );
    const url = await page.locator("#inlineResult a").getAttribute("href");
    assert.match(url, /^\/portal#[\w-]{64}$/);
    const portal = await context.newPage();
    await portal.goto("http://localhost:8000" + url, {
      waitUntil: "networkidle",
    });
    await expect(portal.locator("#status")).toContainText("awaiting review");
    const staff = await context.newPage();
    await staff.goto("http://localhost:8000/app");
    await staff.locator("#email").fill("preview@example.test");
    await staff.locator("#password").fill("Synthetic-preview-2026");
    await staff.locator("#loginForm button").click();
    await expect(staff.locator("#caseList")).toContainText(
      "Synthetic Browser Person",
    );
    await staff
      .locator(".case-button")
      .filter({ hasText: "Synthetic Browser Person" })
      .click();
    await staff
      .locator("#verificationNote")
      .fill(
        "Synthetic browser test: contact verified through a simulated callback, not a real patient.",
      );
    await staff.locator("#verifyForm button").click();
    await expect(staff.locator("#contactStatus")).toContainText("Verified");
    await staff
      .locator("#reviewNote")
      .fill(
        "Synthetic suitability review for browser validation. No real clinical advice provided.",
      );
    await staff.locator("#reviewForm button").click();
    await expect(staff.locator("#caseStatus")).toContainText("eligible");
    await staff
      .locator("#planText")
      .fill(
        "SYNTHETIC BROWSER TEST CONTENT. This demonstrates reviewed publication and is not a recommendation for a real person.",
      );
    await staff.locator("#draftForm button").click();
    await expect(staff.locator("#versionInfo")).toContainText(
      "Saved version 1",
    );
    await staff.locator("#confirmReviewed").check();
    await staff.locator("#approveForm button").click();
    await expect(staff.locator("#signatureInfo")).toContainText(
      "Preview Practitioner",
    );
    await portal.locator("#refreshPortal").click();
    await expect(portal.locator("#plan")).toContainText(
      "SYNTHETIC BROWSER TEST CONTENT",
    );
    await portal.screenshot({
      path: "test-results/portal-desktop.png",
      fullPage: true,
    });
    await staff.screenshot({
      path: "test-results/workspace-desktop.png",
      fullPage: true,
    });
    const mobile = await context.newPage();
    await mobile.setViewportSize({ width: 390, height: 844 });
    await mobile.goto("http://localhost:8000/", { waitUntil: "networkidle" });
    await mobile.screenshot({
      path: "test-results/landing-mobile.png",
      fullPage: true,
    });
    const overflowing = await mobile.evaluate(() =>
      [...document.querySelectorAll("main *")]
        .filter((e) => e.getBoundingClientRect().right > innerWidth + 1)
        .slice(0, 12)
        .map((e) => ({
          tag: e.tagName,
          class: e.className,
          id: e.id,
          right: e.getBoundingClientRect().right,
          width: e.getBoundingClientRect().width,
        })),
    );
    if (overflowing.length) console.log("Overflow diagnostics:", overflowing);
    assert.equal(
      await mobile.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      true,
      "Mobile overflow",
    );
    await mobile.locator(".nav-cta").click();
    await expect(mobile.locator("#riName")).toBeFocused();
    await mobile.keyboard.press("Escape");
    await expect(mobile.locator(".nav-cta")).toBeFocused();
    await mobile.locator(".price button").nth(1).click();
    for (const [id, value] of Object.entries({
      diName: "Synthetic Diet Person",
      diPhone: "+919999999998",
      diAge: "30",
      diFood: "Vegetarian",
      diAllergies: "None",
      diRoutine: "Synthetic shift work pattern",
    }))
      await mobile.locator("#" + id).fill(value);
    await mobile
      .locator("#diGoal")
      .selectOption({ label: "Healthier everyday eating" });
    await mobile.locator("#diScreen").selectOption("review");
    await mobile.locator("#diConsent").check();
    await mobile.locator("#dietForm button[type=submit]").click();
    await expect(mobile.locator("#dietResult")).toContainText(
      "Intake received",
    );
    await portal.locator("#forgetDevice").click();
    await expect(portal.locator("#patientPanel")).toBeHidden();
    await expect(portal.locator("#plan")).toBeEmpty();
    await staff.locator("#logout").click();
    await expect(staff.locator("#loginPanel")).toBeVisible();
    await expect(staff.locator("#caseName")).toBeEmpty();
    assert.equal(errors.length, 0, errors.join("\n"));
    console.log(
      "Browser QA passed: desktop report intake, portal, practitioner review/approval/publication, mobile diet intake, focus restore and no overflow.",
    );
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
