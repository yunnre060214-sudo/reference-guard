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
  if (result['--style'] && !Object.hasOwn(styles, result['--style'])) throw new Error('Unsupported built-in style');
  return result;
}

function validateItem(item) {
  if (!item || Array.isArray(item) || typeof item !== 'object' ||
      !['id', 'type', 'title'].every(key => typeof item[key] === 'string' && item[key].trim()) || item.id.trim() !== item.id) {
    throw new Error('Every item needs a nonempty string id, type, and title; ID whitespace is not allowed');
  }
  for (const field of ['DOI', 'URL', 'language', 'version', 'publication-form']) {
    if (field in item && (typeof item[field] !== 'string' || !item[field].trim())) throw new Error(item.id + ': invalid ' + field);
  }
  if (item.URL) {
    const url = new URL(item.URL);
    if (!['http:', 'https:', 'ftp:'].includes(url.protocol) || url.username || url.password) throw new Error(item.id + ': unsafe URL protocol or credentials');
  }
  for (const field of ['author', 'editor', 'translator']) {
    if (field in item && (!Array.isArray(item[field]) || item[field].some(name =>
      !name || Array.isArray(name) || typeof name !== 'object' ||
      !['family', 'given', 'literal'].some(key => typeof name[key] === 'string' && name[key].trim()) ||
      ['family', 'given', 'literal'].some(key => key in name && typeof name[key] !== 'string')))) {
      throw new Error(item.id + ': invalid names in ' + field);
    }
  }
  for (const field of ['issued', 'accessed', 'available-date', 'original-date']) {
    if (!(field in item)) continue;
    const date = item[field];
    if (!date || Array.isArray(date) || typeof date !== 'object') throw new Error(item.id + ': invalid ' + field);
    if ('date-parts' in date && (!Array.isArray(date['date-parts']) || !date['date-parts'].length || date['date-parts'].length > 2 ||
      date['date-parts'].some(parts => {
        if (!Array.isArray(parts) || !parts.length || parts.length > 3 || !parts.every(Number.isInteger)) return true;
        if (parts.length > 1 && (parts[1] < 1 || parts[1] > 12)) return true;
        if (parts.length > 2) {
          const d = new Date(0);
          d.setUTCFullYear(parts[0], parts[1] - 1, parts[2]);
          return d.getUTCFullYear() !== parts[0] || d.getUTCMonth() !== parts[1] - 1 || d.getUTCDate() !== parts[2];
        }
        return false;
      }))) throw new Error(item.id + ': invalid calendar date in ' + field);
    if (!('date-parts' in date) && !(typeof date.literal === 'string' && date.literal.trim()) && !(typeof date.raw === 'string' && date.raw.trim())) {
      throw new Error(item.id + ': ' + field + ' needs date-parts, literal or raw');
    }
  }
}

function render(items, args) {
  if (!Array.isArray(items) || !items.length) throw new Error('Input must be a nonempty CSL-JSON array');
  const records = new Map();
  const warnings = [];
  const normalizations = [];
  for (const item of items) {
    validateItem(item);
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
  if (JSON.stringify(text[0].entry_ids) !== JSON.stringify(html[0].entry_ids) ||
      text[0].entry_ids.some(ids => ids.length !== 1)) throw new Error('Text and HTML bibliography mappings differ');
  const inputPositions = new Map(items.map((item, index) => [item.id, index + 1]));
  const entries = text[0].entry_ids.map((ids, index) => ({
    id: ids[0], input_index: inputPositions.get(ids[0]), bibliography_index: index + 1,
    text: text[1][index].trim(), html: html[1][index].trim(),
  }));
  if (entries.length !== items.length || new Set(entries.map(row => row.id)).size !== items.length) {
    throw new Error('Renderer did not preserve every input ID');
  }
  return {
    schema_version: 2, status: 'candidate_only',
    input_sha256: sha256(JSON.stringify(items)),
    bibliography_order: entries.map(row => row.id),
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
    const result = render(JSON.parse(fs.readFileSync(args['--input'], 'utf8').replace(/^\uFEFF/, '')), args);
    const output = JSON.stringify(result, null, 2) + '\n';
    if (args['--output']) fs.writeFileSync(args['--output'], output, {encoding: 'utf8', flag: 'wx'});
    else process.stdout.write(output);
  } catch (error) {
    process.stderr.write('Bibliography rendering failed: ' + error.message + '\n');
    process.exitCode = 1;
  }
}

if (require.main === module) main();
module.exports = {render};
