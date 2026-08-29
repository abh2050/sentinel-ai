/**
 * Dashboard Screenshot Capture
 *
 * Drives the running Mission Control UI through the full incident lifecycle and
 * writes the images embedded in README.md. Scripting this rather than taking
 * screenshots by hand means the documentation can be regenerated after any UI
 * change, and never silently drifts from what the app actually renders.
 *
 * Prerequisites: backend on :8000 and dashboard on :5173 (bash scripts/start.sh).
 *
 * Usage:
 *   npm run screenshots
 */
import { chromium } from 'playwright'
import { mkdir, rm } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(HERE, '..', '..', 'docs', 'screenshots')
const BASE_URL = process.env.SENTINEL_URL ?? 'http://localhost:5173'
const API_URL = process.env.SENTINEL_API ?? 'http://localhost:8000'
const VIEWPORT = { width: 1600, height: 1000 }

/** Poll an element until it appears, with a clear failure message. */
async function waitFor(page, selector, description, timeout = 25_000) {
  try {
    await page.waitForSelector(selector, { timeout, state: 'visible' })
  } catch {
    throw new Error(`Timed out waiting for ${description} (selector: ${selector})`)
  }
}

/** Let the 1.5s telemetry poll land so charts render with real data. */
const settle = (page, ms = 2500) => page.waitForTimeout(ms)

async function resetPlatform() {
  await fetch(`${API_URL}/api/chaos/reset`, { method: 'POST' })
  await fetch(`${API_URL}/api/ingestion/reset`, { method: 'POST' })
}

async function main() {
  // Fail fast with a useful message rather than a confusing browser timeout.
  try {
    const probe = await fetch(`${API_URL}/api/status`)
    if (!probe.ok) throw new Error(`status ${probe.status}`)
  } catch (err) {
    console.error(
      `\nCannot reach the SentinelAI API at ${API_URL} (${err.message}).\n` +
      `Start the platform first:  bash scripts/start.sh\n`
    )
    process.exit(1)
  }

  await rm(OUT_DIR, { recursive: true, force: true })
  await mkdir(OUT_DIR, { recursive: true })

  await resetPlatform()

  const browser = await chromium.launch()
  const page = await browser.newPage({
    viewport: VIEWPORT,
    deviceScaleFactor: 2, // Retina-density images stay sharp in the README.
    colorScheme: 'dark',
  })

  const shots = []
  const capture = async (name, options = {}) => {
    const path = join(OUT_DIR, `${name}.png`)
    await page.screenshot({ path, ...options })
    shots.push(name)
    console.log(`  captured ${name}.png`)
  }

  console.log('Capturing SentinelAI dashboard screenshots...')

  // ---- 1. Steady state -------------------------------------------------
  // Not 'networkidle': the dashboard polls telemetry every 1.5s, so the
  // network never goes idle and that wait would hang until it timed out.
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
  await waitFor(page, 'text=p95 Latency', 'the KPI metric cards')
  await settle(page, 4000) // Let the live charts accumulate a trend line.
  await capture('01-dashboard-healthy')

  // ---- 2. Ingestion pipeline ------------------------------------------
  await waitFor(page, 'text=Telemetry Ingestion Pipeline', 'the ingestion panel')
  await page.getByRole('button', { name: /Run Ingestion Cycle/i }).click()
  await waitFor(page, 'text=Acceptance Rate', 'the ingestion run report')
  await settle(page, 1200)

  const ingestionPanel = page
    .locator('div.rounded-xl', { hasText: 'Telemetry Ingestion Pipeline' })
    .first()
  await ingestionPanel.scrollIntoViewIfNeeded()
  await capture('02-ingestion-pipeline', { clip: await ingestionPanel.boundingBox() })

  // ---- 3. Incident injection ------------------------------------------
  // Trigger via the UI so the capture exercises the same path a user takes.
  await page.getByRole('button', { name: /Top-K Context Blowout/i }).click()
  await waitFor(page, 'text=INCIDENT', 'the incident status banner', 30_000)
  await settle(page, 3500) // Let the latency spike propagate into the charts.

  // The app auto-opens the PR modal ~1.8s after injection; close it so the
  // incident view itself is visible, then reopen it for the next shot.
  const modalClose = page.getByRole('button', { name: /Close pull request review/i })
  if (await modalClose.isVisible().catch(() => false)) {
    await modalClose.click()
    await settle(page, 800)
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  await settle(page, 1500)
  await capture('03-incident-detected')

  // ---- 4. Agent trace --------------------------------------------------
  const tracePanel = page
    .locator('div.rounded-xl', { hasText: 'Autonomous Incident Remediation Trace' })
    .first()
  if (await tracePanel.count()) {
    await tracePanel.scrollIntoViewIfNeeded()
    await settle(page, 1000)
    await capture('04-agent-trace', { clip: await tracePanel.boundingBox() })
  }

  // ---- 5. Pull request review -----------------------------------------
  const reviewButton = page.getByRole('button', { name: /Review PR|Review Pull Request/i }).first()
  if (await reviewButton.count()) {
    await reviewButton.click()
  }
  await waitFor(page, 'text=/Sandbox Validation|Validation Scorecard/i', 'the PR review modal')
  await settle(page, 1500)
  await capture('05-pull-request-review')

  await browser.close()

  console.log(`\nWrote ${shots.length} screenshots to docs/screenshots/`)
  await resetPlatform()
}

main().catch(async (err) => {
  console.error(`\nScreenshot capture failed: ${err.message}\n`)
  process.exit(1)
})
