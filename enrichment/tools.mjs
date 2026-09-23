#!/usr/bin/env node
// Status-tracking helpers for the resource-card enrichment effort (see ENRICHMENT.md).
//
//   node enrichment/tools.mjs manifest   rescan study-guide/curated/resources -> enrichment/manifest.json (+ TSV to stdout)
//   node enrichment/tools.mjs table      regenerate the status table inside ENRICHMENT.md
//   node enrichment/tools.mjs merge      validate enrichment/<slug>.json cards, fold into site/curated.json
//   node enrichment/tools.mjs validate   merge, dry-run (no writes)
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const EN = path.join(ROOT, 'enrichment');
const CURATED = path.join(ROOT, 'site', 'curated.json');
const RES = path.join(ROOT, 'resources');
const PLAN = path.join(ROOT, 'ENRICHMENT.md');

// slug rules mirror site/generate.mjs
const NON_ARXIV_SLUG = {
  'https://www.nature.com/articles/s41586-023-06924-6': 'nature-funsearch-2024',
  'https://doi.org/10.1038/s41586-026-10265-5': 'nature-ai-scientist-v2-2026',
  'https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2016.00040/full': 'frontiers-quality-diversity-2016',
  'https://openreview.net/forum?id=3tk6AES1Aj': 'openreview-higher-order-evolution-2024',
};
const slugify = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
const slugFor = (e) =>
  e.u.startsWith('https://arxiv.org/abs/') ? e.u.split('/abs/')[1] :
  e.u.startsWith('https://github.com/') ? slugify(e.u.replace(/\/$/, '').split('/').pop()) :
  NON_ARXIV_SLUG[e.u] || slugify(e.t);

function loadE() {
  const html = fs.readFileSync(path.join(ROOT, 'study-guide.html'), 'utf8');
  const at = html.indexOf('const E = [');
  return eval(html.slice(at, html.indexOf('];', at) + 2).replace('const E = ', ''));
}

const readJson = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const writeJson = (p, o) => fs.writeFileSync(p, JSON.stringify(o, null, 2) + '\n');
const maybe = (p) => (fs.existsSync(p) ? readJson(p) : {});

function manifest() {
  const curated = maybe(CURATED);
  const rows = loadE().map((e, idx) => {
    const slug = slugFor(e);
    const repo = e.u.startsWith('https://github.com/');
    const card = curated[slug];
    const words = card ? JSON.stringify(card).split(/\s+/).length : 0;
    return {
      idx, slug, title: e.t, url: e.u, repo, ph: e.ph, d: e.d, section: e.s, sub: e.ss,
      hadCard: !!card, cardWords: words, hasMethod: !!(card && card.method),
      pdf: repo ? '-' : (fs.existsSync(path.join(RES, slug + '.pdf')) ? 'yes' : 'no'),
    };
  });
  writeJson(path.join(EN, 'manifest.json'), rows);
  for (const r of rows) console.log([r.idx + 1, r.slug, r.repo ? 'repo' : 'paper', r.ph, r.hadCard ? 'had' : 'new', r.cardWords, r.hasMethod ? 'm' : '-', r.pdf, r.title].join('\t'));
  const papers = rows.filter((r) => !r.repo);
  console.error(`\n${rows.length} resources — ${papers.length} papers, ${rows.length - papers.length} repos`);
  console.error(`cards: ${rows.filter((r) => r.hadCard).length} present, ${papers.filter((r) => !r.hasMethod).length} papers missing in-card method, ${rows.filter((r) => !r.hadCard).length} missing entirely`);
  console.error(`papers without local PDF: ${papers.filter((r) => r.pdf === 'no').length}`);
}

function statusOf(rows) {
  const merged = maybe(path.join(EN, 'merged.json'));
  const failed = maybe(path.join(EN, 'failures.json'));
  return Object.fromEntries(rows.map((r) => {
    const s = merged[r.slug] ? '✓' : failed[r.slug] ? '✗' : (fs.existsSync(path.join(EN, r.slug + '.json')) ? '◐' : '☐');
    return [r.slug, s];
  }));
}

function table() {
  const rows = readJson(path.join(EN, 'manifest.json'));
  const st = statusOf(rows);
  const notes = maybe(path.join(EN, 'notes.json'));
  const body = [
    '| # | Stage | Type | Slug | Title | Card | PDF | Status | Notes |',
    '|---|-------|------|------|-------|------|-----|--------|-------|',
    ...rows.map((r) => `| ${r.idx + 1} | ${r.ph} | ${r.repo ? 'repo' : 'paper'} | ${r.slug} | ${r.title} | ${r.hadCard ? 'had' : '**new**'} | ${r.pdf} | ${st[r.slug]} | ${notes[r.slug] || ''} |`),
  ].join('\n');
  const md = fs.readFileSync(PLAN, 'utf8');
  const a = md.indexOf('<!-- BEGIN STATUS TABLE -->');
  const b = md.indexOf('<!-- END STATUS TABLE -->');
  if (a < 0 || b < 0) throw new Error('status-table markers missing from ENRICHMENT.md');
  fs.writeFileSync(PLAN, md.slice(0, a) + '<!-- BEGIN STATUS TABLE -->\n' + body + '\n<!-- END STATUS TABLE -->' + md.slice(b + '<!-- END STATUS TABLE -->'.length));
  const done = Object.values(st).filter((s) => s === '✓').length;
  console.log(`table regenerated — ${done}/${rows.length} merged`);
}

const PAPER = { strings: ['tldr', 'method', 'fits', 'reading'], arrays: ['results', 'advantages', 'limitations'], optionalArrays: [] };
const REPO = { strings: ['what', 'run', 'note'], arrays: ['architecture'], optionalArrays: ['advantages'] };

function merge(dry) {
  const rows = readJson(path.join(EN, 'manifest.json'));
  const bySlug = new Map(rows.map((r) => [r.slug, r]));
  const curated = maybe(CURATED);
  const merged = maybe(path.join(EN, 'merged.json'));
  const failed = maybe(path.join(EN, 'failures.json'));
  const ok = [], errs = [];
  for (const f of fs.readdirSync(EN).sort()) {
    if (!f.endsWith('.json') || ['manifest.json', 'merged.json', 'failures.json', 'notes.json'].includes(f)) continue;
    const slug = f.slice(0, -5);
    const meta = bySlug.get(slug);
    if (!meta) { errs.push(`${slug}: not in manifest — wrong filename?`); continue; }
    let card;
    try { card = readJson(path.join(EN, f)); } catch (e) { errs.push(`${slug}: invalid JSON — ${e.message}`); continue; }
    const spec = meta.repo ? REPO : PAPER;
    const bad = [];
    for (const k of spec.strings) if (typeof card[k] !== 'string' || !card[k].trim()) bad.push(`missing string "${k}"`);
    for (const k of [...spec.arrays, ...spec.optionalArrays]) {
      if (spec.optionalArrays.includes(k) && card[k] === undefined) continue;
      if (!Array.isArray(card[k]) || card[k].length === 0 || card[k].some((x) => typeof x !== 'string' || !x.trim())) bad.push(`bad array "${k}"`);
    }
    if (bad.length) { errs.push(`${slug}: ${bad.join('; ')}`); continue; }
    curated[slug] = Object.fromEntries(Object.entries(card).filter(([k]) => !k.startsWith('_')));
    merged[slug] = new Date().toISOString();
    delete failed[slug];
    ok.push(slug);
  }
  if (dry) console.log(`validate: ${ok.length} ok, ${errs.length} errors`);
  else if (ok.length) {
    writeJson(CURATED, curated);
    writeJson(path.join(EN, 'merged.json'), merged);
    writeJson(path.join(EN, 'failures.json'), failed);
    console.log(`merged ${ok.length}: ${ok.join(', ')}`);
  } else console.log('nothing new to merge');
  for (const e of errs) console.log(`  ERROR ${e}`);
  if (errs.length) process.exitCode = 1;
}

const cmd = process.argv[2];
if (cmd === 'manifest') manifest();
else if (cmd === 'table') table();
else if (cmd === 'merge') merge(false);
else if (cmd === 'validate') merge(true);
else { console.error('usage: node enrichment/tools.mjs manifest|table|merge|validate'); process.exit(2); }
