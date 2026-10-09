/**
 * Fetches Crowdin approval progress and derives the release version from it.
 * Version format: "0.{approvalProgress}" (e.g. 40% → "0.40"), except a fully
 * approved translation (100%) which becomes "1.0".
 * Writes version-info/{version,progress}.txt: build-localization.js stamps the
 * version into the in-game text, and the CI release step names the release after it.
 */

'use strict';

const https = require('https');
const fs = require('fs');
const path = require('path');
const { ROOT, requireToken } = require('./env');

const CROWDIN_TOKEN = requireToken();
const PROJECT_ID = 749381;
const FILE_ID = 22;

function httpsRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, options, (res) => {
      let body = '';
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(body) });
        } catch {
          resolve({ status: res.statusCode, body });
        }
      });
    });
    req.on('error', reject);
    if (options.body) req.write(options.body);
    req.end();
  });
}

async function main() {
  console.log('Fetching Crowdin approval progress...');

  const url = `https://api.crowdin.com/api/v2/projects/${PROJECT_ID}/files/${FILE_ID}/languages/progress`;
  const { status, body } = await httpsRequest(url, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${CROWDIN_TOKEN}`,
      'Content-Type': 'application/json',
    },
  });

  if (status !== 200) {
    console.error(`Crowdin API error (${status}):`, body);
    process.exit(1);
  }

  const progress = body.data[0].data.approvalProgress;
  const version = progress >= 100 ? '1.0' : `0.${progress}`;

  console.log(`Approval progress: ${progress}% → version: ${version}`);

  // Progress is written separately: it can no longer be derived from the
  // version number once 100% maps to 1.0 instead of 0.100.
  const infoDir = path.join(ROOT, 'version-info');
  fs.mkdirSync(infoDir, { recursive: true });
  fs.writeFileSync(path.join(infoDir, 'version.txt'), `${version}\n`, 'utf8');
  fs.writeFileSync(path.join(infoDir, 'progress.txt'), `${progress}\n`, 'utf8');

  console.log(`Wrote version-info: version=${version}, progress=${progress}`);
}

main().catch((err) => {
  console.error('Unexpected error:', err);
  process.exit(1);
});
