#!/usr/bin/env node
import { chromium } from "playwright";

const [executablePath, url, resultAttribute, ...extraArgs] = process.argv.slice(2);
if (!executablePath || !url || !resultAttribute) {
  throw new Error("usage: browser_probe_dump.mjs <chromium> <url> <result-attribute>");
}

const screenshotArg = extraArgs.find((arg) => arg.startsWith("--screenshot="));
const timeoutArg = extraArgs.find((arg) => arg.startsWith("--xyg-probe-timeout-ms="));
const requestedTimeout = Number(timeoutArg?.slice(timeoutArg.indexOf("=") + 1));
const launchArgs = extraArgs.filter((arg) => arg !== screenshotArg && arg !== timeoutArg);
const browser = await chromium.launch({
  executablePath,
  headless: true,
  args: [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    ...launchArgs,
  ],
});
try {
  // Playwright owns the browser context, so Chromium's command-line scale
  // switch alone does not change window.devicePixelRatio for a new page.
  // Preserve the legacy dump-dom probe contract in the explicit context.
  const scaleArg = extraArgs.find((arg) => arg.startsWith("--force-device-scale-factor="));
  const requestedScale = Number(scaleArg?.slice(scaleArg.indexOf("=") + 1));
  const windowArg = extraArgs.find((arg) => arg.startsWith("--window-size="));
  const requestedWindow = windowArg
    ?.slice(windowArg.indexOf("=") + 1)
    .split(",")
    .map(Number);
  const width = requestedWindow?.length === 2 && Number.isFinite(requestedWindow[0])
    ? requestedWindow[0] : 640;
  const height = requestedWindow?.length === 2 && Number.isFinite(requestedWindow[1])
    ? requestedWindow[1] : 480;
  const page = await browser.newPage({
    viewport: { width, height },
    ...(Number.isFinite(requestedScale) && requestedScale > 0
      ? { deviceScaleFactor: requestedScale }
      : {}),
  });
  // Page errors explain a probe that never reports; surface them on timeout.
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(`pageerror: ${error?.stack || error}`));
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") {
      pageErrors.push(`console.${message.type()}: ${message.text()}`);
    }
  });
  await page.goto(url, { waitUntil: "load" });
  await page.waitForFunction(
    ([result, error]) => document.body?.hasAttribute(result) || document.body?.hasAttribute(error),
    [resultAttribute, `${resultAttribute}-error`],
    {
      timeout: Number.isFinite(requestedTimeout) && requestedTimeout > 0
        ? requestedTimeout
        : 10_000,
    },
  ).catch((error) => {
    const details = pageErrors.slice(-20).join("\n");
    throw new Error(`${error.message}${details ? `\npage errors:\n${details}` : ""}`);
  });
  if (screenshotArg) {
    await page.screenshot({ path: screenshotArg.slice(screenshotArg.indexOf("=") + 1) });
  }
  process.stdout.write(await page.content());
} finally {
  await browser.close();
}
