/**
 * Playwright global setup — runs once before the test session.
 * Copies the live database to shiso_test.db so E2E tests have a
 * realistic, populated database without touching production data.
 */
import { cpSync, existsSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// Script location: shiso/shiso/dashboard/frontend/tests/e2e/global-setup.js
// Repo root is 5 levels up:
//   tests/ → frontend/ → dashboard/ → shiso/ → (repo root at shiso/)
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const SHISO_ROOT = resolve(SCRIPT_DIR, '../../../../../')
const DATA_DIR = resolve(SHISO_ROOT, 'data')
const src = resolve(DATA_DIR, 'shiso.db')
const dst = resolve(DATA_DIR, 'shiso_test.db')

export default async function globalSetup() {
  // Validate SHISO_ROOT has expected structure (should contain shiso/ subdir)
  if (!existsSync(resolve(SHISO_ROOT, 'shiso'))) {
    throw new Error(
      `[global-setup] SHISO_ROOT "${SHISO_ROOT}" does not look like the shiso repo`
    )
  }

  if (existsSync(src)) {
    cpSync(src, dst, { force: true })
    console.log(`[global-setup] Copied ${src} → ${dst}`)
  } else {
    console.warn(`[global-setup] Source DB not found at ${src}, skipping copy`)
  }
}
