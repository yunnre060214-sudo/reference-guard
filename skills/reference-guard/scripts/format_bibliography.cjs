#!/usr/bin/env node
/* SPDX-License-Identifier: AGPL-3.0-or-later
 * Source is distributed with the unmodified citeproc-js dependency.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const assetRoot = path.resolve(__dirname, '..', 'assets');
const styles = {gbt2025: 'styles/gbt2025-numeric.csl', apa7: 'styles/apa7.csl', ieee: 'styles/ieee.csl'};
const sha256 = data => crypto.createHash('sha256').update(data).digest('hex');

function readAsset(relative, manifest) {
  const data = fs.readFileSync(path.join(assetRoot, relative));
  if (!manifest.files[relative] || sha256(data) !== manifest.files[relative].sha256) {
    throw new Error('Asset integrity mismatch: ' + relative);
  }
  return data.toString('utf8');
}

function parseArgs(args) {
  const result = {};
  for (let i = 0; i < args.length; i++) {
    const key = args[i];
    if (key === '--help') return {help: true};
    if (!['--input', '--output', '--style', '--style-file'].includes(key) || !args[i + 1] || args[i + 1].startsWith('--')) {
      throw new Error('Unknown or incomplete argument: ' + key);
    }
    if (result[key]) throw new Error('Duplicate argument: ' + key);
    result[key] = args[++i];
  }
  if (!result['--input'] || Boolean(result['--style']) === Boolean(result['--style-file'])) {
    throw new Error('Supply --input and exactly one of --style or --style-file');
  }
  if (result['--style'] && !styles[result['--style']]) throw new Error('Unsupported built-in style');
  return result;
}

function render(items, args) {
  if (!Array.isArray(items) || !items.length) throw new Error('Input must be a nonempty CSL-JSON array');
  const records = new Map();
  const warnings = [];
  const normalizations = [];
  for (const item of items) {
    if (!item || typeof item.id !== 'string' || !item.id || typeof item.type !== 'string' || !item.type || typeof item.title !== 'string' || !item.title.trim()) {
      throw new Error('Every item needs a nonempty string id, type, and title');
    }
    if (records.has(item.id)) throw new Error('Duplicate item ID: ' + item.id);
    const record = JSON.parse(JSON.stringify(item));
    if (args['--style'] === 'gbt2025') {
      if (['article', 'dataset'].includes(item.type) && typeof item.version === 'string' && /^[vV]\d/.test(item.version)) {
        record.version = item.version.slice(1);
        normalizations.push({id: item.id, detail: 'Remove an existing numeric V label before the style supplies that same version label.'});
      }
      if (item.DOI && !item.URL) warnings.push(item.id + ': URL access path missing for the generated OL reference; DOI alone is not that path.');
      if (item.type === 'standard' && !item.number) warnings.push(item.id + ': required standard number missing.');
      if (['book', 'report'].includes(item.type) && !item.issued) warnings.push(item.id + ': no publication date supplied; verify source availability and allowed omission.');
      if (item.type === 'report') {
        const form = item['publication-form'];
        if (form !== undefined && !['book', 'standalone'].includes(form)) throw new Error(item.id + ': publication-form must be book or standalone for a report');
        if (form === undefined && (item.publisher || item['publisher-place'])) throw new Error(item.id + ': verified publication-form is required; publisher alone cannot classify a report');
        if (form === 'book') {
          if (record.issued && Array.isArray(record.issued['date-parts'])) {
            record.issued['date-parts'] = record.issued['date-parts'].map(parts => parts.slice(0, 1));
            normalizations.push({id: item.id, detail: 'Book-form report: display sourced publication year; original date remains in input.'});
          }
        } else {
          delete record.publisher;
          delete record['publisher-place'];
          normalizations.push({id: item.id, detail: 'Standalone report layout; source publisher fields remain in input, outside this reference pattern.'});
        }
      }
    }
    records.set(item.id, record);
  }
  const manifest = JSON.parse(fs.readFileSync(path.join(assetRoot, 'manifest.json'), 'utf8'));
  readAsset('vendor/citeproc_commonjs.js', manifest);
  const CSL = require(path.join(assetRoot, 'vendor', 'citeproc_commonjs.js'));
  const styleFile = args['--style'] ? styles[args['--style']] : null;
  const style = styleFile ? readAsset(styleFile, manifest) : fs.readFileSync(args['--style-file'], 'utf8');
  if (!style.includes('<bibliography') || style.includes('rel="independent-parent"')) {
    throw new Error('Supply an independent CSL style with a bibliography');
  }
  const locales = {
    'zh-CN': readAsset('locales/locales-zh-CN.xml', manifest),
    'en-US': readAsset('locales/locales-en-US.xml', manifest),
  };
  const sys = {
    retrieveLocale: tag => {
      if (tag === 'zh' || tag === 'zh-CN') return locales['zh-CN'];
      if (tag === 'en' || tag === 'en-US') return locales['en-US'];
      warnings.push('Locale not bundled: ' + tag);
      return false;
    },
    retrieveItem: id => {
      if (!records.has(id)) throw new Error('Renderer requested an unknown ID');
      return records.get(id);
    },
  };
  const processor = new CSL.Engine(sys, style);
  processor.updateItems(Array.from(records.keys()));
  processor.setOutputFormat('html');
  const html = processor.makeBibliography();
  processor.setOutputFormat('text');
  const text = processor.makeBibliography();
  if (!html || !text || html[0].bibliography_errors.length || text[0].bibliography_errors.length) {
    throw new Error('Renderer could not produce a complete bibliography');
  }
  const entries = text[0].entry_ids.map((ids, index) => ({
    id: ids[0], text: text[1][index].trim(), html: html[1][index].trim(),
  }));
  if (entries.length !== items.length || new Set(entries.map(row => row.id)).size !== items.length) {
    throw new Error('Renderer did not preserve every input ID');
  }
  return {
    schema_version: 1, status: 'candidate_only',
    style: {key: args['--style'] || 'custom', sha256: sha256(style),
            source: styleFile ? manifest.files[styleFile].source : path.resolve(args['--style-file'])},
    renderer: {name: 'citeproc-js', package_version: '2.4.63', processor_version: CSL.PROCESSOR_VERSION},
    entries, layout: html[0], warnings: Array.from(new Set(warnings)), normalizations,
  };
}

function main() {
  try {
    const args = parseArgs(process.argv.slice(2));
    if (args.help) {
      process.stdout.write('Generate candidate bibliography from verified CSL-JSON; this does not certify its sources.\n' +
        'node format_bibliography.cjs --input items.json (--style gbt2025|apa7|ieee | --style-file independent.csl) [--output rendered.json]\n');
      return;
    }
    const result = render(JSON.parse(fs.readFileSync(args['--input'], 'utf8')), args);
    const output = JSON.stringify(result, null, 2) + '\n';
    if (args['--output']) fs.writeFileSync(args['--output'], output, 'utf8');
    else process.stdout.write(output);
  } catch (error) {
    process.stderr.write('Bibliography rendering failed: ' + error.message + '\n');
    process.exitCode = 1;
  }
}

if (require.main === module) main();
module.exports = {render};
