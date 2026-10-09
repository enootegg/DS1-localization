/**
 * Loads KEY=value pairs from the repository's .env into process.env for local runs.
 * Variables that are already set (as they are in CI, from secrets) are left alone.
 */

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');

function loadEnv() {
  const file = path.join(ROOT, '.env');
  if (!fs.existsSync(file)) return;

  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (!match || process.env[match[1]] !== undefined) continue;
    process.env[match[1]] = match[2].replace(/^(['"])(.*)\1$/, '$2');
  }
}

function requireToken() {
  loadEnv();
  if (!process.env.CROWDIN_TOKEN) {
    console.error('Error: CROWDIN_TOKEN is not set (environment variable or .env in the repository root).');
    process.exit(1);
  }
  return process.env.CROWDIN_TOKEN;
}

module.exports = { ROOT, loadEnv, requireToken };
