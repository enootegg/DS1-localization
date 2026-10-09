/**
 * Builds the localization files that Decima imports into the game's text resources.
 *
 * Step 1: Export translations from Crowdin → download CSV
 *         (or read a CSV given on the command line: node build-localization.js file.csv)
 * Step 2: Parse CSV → localization.json  (Director's Cut)
 * Step 3: Generate localization_ds_not_dc.json  (original Death Stranding)
 *
 * The Crowdin project holds the Director's Cut strings only. The original game shares most
 * of them (same file, same UUID), has 245 strings of its own, and lacks the ones the
 * Director's Cut added, so its file is derived:
 *
 *   data/source_show_ds.json     every string of the original game: English source + display mode
 *   data/ds_only_strings.json    the 245 strings that exist only in the original game, with a
 *                                "target" to fill in by hand; an empty one falls back to the
 *                                Director's Cut translation of the same English text, if any
 *   data/show_dc.json            Director's Cut strings whose display mode is not "auto"
 *                                (Crowdin doesn't carry the mode, so it is restored from here)
 *
 * Output: resources/Localization/localization.json
 *         resources/Localization/localization_ds_not_dc.json
 */

'use strict';

const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { ROOT, requireToken } = require('./env');

const PROJECT_ID = 749381;
const FILE_ID = 22;

const OUTPUT_DIR = path.join(ROOT, 'resources', 'Localization');
const VERSION_PATH = path.join(ROOT, 'version-info', 'version.txt');
const SOURCE_SHOW_DS_PATH = path.join(__dirname, 'data', 'source_show_ds.json');
const DS_ONLY_PATH = path.join(__dirname, 'data', 'ds_only_strings.json');
const SHOW_DC_PATH = path.join(__dirname, 'data', 'show_dc.json');

// ─── HTTP helpers ────────────────────────────────────────────────────────────

function httpsRequest(url, options = {}) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    const req = lib.request(url, options, (res) => {
      // Follow redirects
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        resolve(httpsRequest(res.headers.location, { method: 'GET' }));
        return;
      }
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        const body = Buffer.concat(chunks).toString('utf8');
        resolve({ status: res.statusCode, text: body });
      });
    });
    req.on('error', reject);
    if (options.body) req.write(options.body);
    req.end();
  });
}

async function httpsJSON(url, options = {}) {
  const { status, text } = await httpsRequest(url, options);
  return { status, body: JSON.parse(text) };
}

// ─── Step 1: Export from Crowdin ─────────────────────────────────────────────

async function exportFromCrowdin() {
  const token = requireToken();
  console.log('Step 1: Requesting Crowdin export...');

  const exportBody = JSON.stringify({ targetLanguageId: 'uk', fileIds: [FILE_ID] });
  const { status, body } = await httpsJSON(
    `https://api.crowdin.com/api/v2/projects/${PROJECT_ID}/translations/exports`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(exportBody),
      },
      body: exportBody,
    }
  );

  if (status !== 200) {
    throw new Error(`Crowdin export failed (${status}): ${JSON.stringify(body)}`);
  }

  const downloadUrl = body.data.url;
  console.log('Step 1: Downloading CSV...');

  const { text: csvText } = await httpsRequest(downloadUrl, { method: 'GET' });
  console.log(`Step 1: Downloaded ${csvText.length} bytes of CSV.`);

  return csvText;
}

// ─── Step 2: CSV → JSON (port of parser.py) ──────────────────────────────────

// Single-pass CSV parser matching Python's csv.DictReader behaviour exactly.
// Handles: BOM, \r\n / \r / \n line endings, quoted fields with embedded
// commas, newlines and escaped double-quotes ("").
function parseCSV(text) {
  // Strip UTF-8 BOM if present (Crowdin sometimes adds it)
  if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
  // Normalise line endings to \n (same as Python universal newlines)
  text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  const records = [];
  let pos = 0;
  const len = text.length;

  while (pos < len) {
    const fields = [];

    // Parse one record (row)
    recordLoop: while (true) {
      if (text[pos] === '"') {
        // Quoted field
        pos++; // skip opening quote
        let field = '';
        while (pos < len) {
          if (text[pos] === '"') {
            if (text[pos + 1] === '"') {
              field += '"'; // escaped quote
              pos += 2;
            } else {
              pos++; // skip closing quote
              break;
            }
          } else {
            field += text[pos++];
          }
        }
        fields.push(field);
      } else {
        // Unquoted field — read until comma or newline or end
        let field = '';
        while (pos < len && text[pos] !== ',' && text[pos] !== '\n') {
          field += text[pos++];
        }
        fields.push(field);
      }

      // After a field: comma → next field, newline/end → end of record
      if (pos >= len || text[pos] === '\n') {
        if (pos < len) pos++; // skip \n
        break recordLoop;
      }
      // Must be a comma
      pos++; // skip ','
    }

    if (fields.length > 1 || fields[0] !== '') {
      records.push(fields);
    }
  }

  return records;
}

function csvToJSON(csvText) {
  console.log('Step 2: Parsing CSV → JSON...');

  const rows = parseCSV(csvText);
  if (rows.length < 2) throw new Error('CSV has no data rows.');

  // header: Key, Source string, Translation, Context
  const header = rows[0];
  const keyIdx = header.indexOf('Key');
  const sourceIdx = header.indexOf('Source string');
  const translationIdx = header.indexOf('Translation');

  if (keyIdx === -1 || sourceIdx === -1 || translationIdx === -1) {
    throw new Error(`Unexpected CSV header: ${header.join(', ')}`);
  }

  const showDC = JSON.parse(fs.readFileSync(SHOW_DC_PATH, 'utf8'));
  const result = { source: 'English', target: 'English', files: {} };
  let restoredShow = 0;

  for (let i = 1; i < rows.length; i++) {
    const row = rows[i];
    if (!row[keyIdx]) continue;

    const key = row[keyIdx];
    const sourceStr = row[sourceIdx] || '';
    const translation = row[translationIdx] || '';

    // Split on LAST occurrence of @@@@
    const splitIdx = key.lastIndexOf('@@@@');
    if (splitIdx === -1) continue;

    const filename = key.slice(0, splitIdx);
    const stringId = key.slice(splitIdx + 4);

    if (!result.files[filename]) result.files[filename] = {};

    // Without this every line would be imported as "auto": lines the game shows regardless of
    // the subtitle setting (song credits, chapter cards) would vanish once subtitles are off.
    const show = (showDC[filename] && showDC[filename][stringId]) || 'auto';
    if (show !== 'auto') restoredShow++;

    result.files[filename][stringId] = {
      source: sourceStr,
      target: translation || sourceStr,
      show,
    };
  }

  const count = Object.values(result.files).reduce((n, f) => n + Object.keys(f).length, 0);
  console.log(`Step 2: Parsed ${count} strings across ${Object.keys(result.files).length} files.`);
  console.log(`Step 2: Restored the display mode of ${restoredShow} strings.`);

  return result;
}

// ─── Step 3: Generate DS version ─────────────────────────────────────────────

function buildDSVersion(dcLocalization) {
  console.log('Step 3: Building DS (non-DC) localization...');

  const sourceShowDS = JSON.parse(fs.readFileSync(SOURCE_SHOW_DS_PATH, 'utf8'));
  const dsOnly = JSON.parse(fs.readFileSync(DS_ONLY_PATH, 'utf8')).files;

  // English text → its Director's Cut translations, per file and across the whole game.
  // The original game repeats many Director's Cut strings under UUIDs of its own.
  const bySourceInFile = new Map();
  const bySource = new Map();
  const remember = (map, key, target) => {
    if (!map.has(key)) map.set(key, new Set());
    map.get(key).add(target);
  };
  for (const [filePath, strings] of Object.entries(dcLocalization.files)) {
    for (const data of Object.values(strings)) {
      if (data.target === data.source) continue; // not translated yet
      remember(bySourceInFile, `${filePath}\n${data.source}`, data.target);
      remember(bySource, data.source, data.target);
    }
  }
  const only = (set) => (set && set.size === 1 ? [...set][0] : null);

  const merged = { source: 'English', target: 'English', files: {} };
  const stats = { shared: 0, manual: 0, matched: 0, untranslated: 0 };
  const untranslated = [];

  for (const [filePath, strings] of Object.entries(sourceShowDS)) {
    const dcStrings = dcLocalization.files[filePath] || {};
    merged.files[filePath] = {};

    for (const [lineId, data] of Object.entries(strings)) {
      let target;

      if (dcStrings[lineId]) {
        target = dcStrings[lineId].target;
        stats.shared++;
      } else {
        const manual = dsOnly[filePath] && dsOnly[filePath][lineId] && dsOnly[filePath][lineId].target;
        const matched = only(bySourceInFile.get(`${filePath}\n${data.source}`)) || only(bySource.get(data.source));

        if (manual) {
          target = manual;
          stats.manual++;
        } else if (matched) {
          target = matched;
          stats.matched++;
        } else {
          target = data.source;
          stats.untranslated++;
          untranslated.push(`${filePath}@@@@${lineId}: ${JSON.stringify(data.source)}`);
        }
      }

      merged.files[filePath][lineId] = { source: data.source, target, show: data.show };
    }
  }

  const count = Object.values(merged.files).reduce((n, f) => n + Object.keys(f).length, 0);
  console.log(`Step 3: DS version has ${count} strings across ${Object.keys(merged.files).length} files.`);
  console.log(`Step 3: ${stats.shared} shared with DC; DS-only: ${stats.manual} from ds_only_strings.json, ` +
    `${stats.matched} matched by English text, ${stats.untranslated} left in English.`);

  fs.writeFileSync(path.join(OUTPUT_DIR, 'ds_untranslated.txt'), untranslated.join('\n') + '\n', 'utf8');
  console.log(`Step 3: The strings left in English are listed in ${path.join(OUTPUT_DIR, 'ds_untranslated.txt')}`);

  return merged;
}

// ─── Patch version string ─────────────────────────────────────────────────────

const VERSION_FILE_KEY = 'localized/sentences/ds_ui/ds_system/simpletext.core';

function patchVersionString(localization, displayVersion) {
  const fileStrings = localization.files[VERSION_FILE_KEY];
  if (!fileStrings) {
    console.warn('patchVersionString: file key not found, skipping.');
    return;
  }

  let patched = 0;
  for (const [id, data] of Object.entries(fileStrings)) {
    if (data.target && data.target.includes('Версія перекладу:')) {
      data.target = data.target.replace(/Версія перекладу: [\d.]+/, `Версія перекладу: ${displayVersion}`);
      patched++;
    }
  }

  console.log(`patchVersionString: patched ${patched} string(s) → "Версія перекладу: ${displayVersion}"`);
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  // Written by set-version.js (e.g. "0.40"). Without it the version text is left as translated.
  const displayVersion = fs.existsSync(VERSION_PATH) ? fs.readFileSync(VERSION_PATH, 'utf8').trim() : null;
  console.log(displayVersion ? `Display version: ${displayVersion}` : 'No version-info/version.txt: run set-version.js first to stamp the version.');

  const csvPath = process.argv[2];
  const csvText = csvPath ? fs.readFileSync(csvPath, 'utf8') : await exportFromCrowdin();

  const dcLocalization = csvToJSON(csvText);
  if (displayVersion) patchVersionString(dcLocalization, displayVersion);
  const dcPath = path.join(OUTPUT_DIR, 'localization.json');
  fs.writeFileSync(dcPath, JSON.stringify(dcLocalization, null, 4), 'utf8');
  console.log(`Wrote: ${dcPath}`);

  const dsLocalization = buildDSVersion(dcLocalization);
  if (displayVersion) patchVersionString(dsLocalization, displayVersion);
  const dsPath = path.join(OUTPUT_DIR, 'localization_ds_not_dc.json');
  fs.writeFileSync(dsPath, JSON.stringify(dsLocalization, null, 4), 'utf8');
  console.log(`Wrote: ${dsPath}`);

  console.log('Done! Both localization files are ready.');
}

main().catch((err) => {
  console.error('Build failed:', err);
  process.exit(1);
});
