import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { marked } from 'marked';

const ROOT = path.resolve(import.meta.dirname, '..');
const SITE = path.join(ROOT, 'site');
const P = path.join(SITE, 'p');
const RES = path.join(ROOT, 'resources');
const CACHE = path.join(SITE, '.meta-cache.json');

// ---- load E + METHODS from study-guide.html ----
const html = fs.readFileSync(path.join(ROOT, 'study-guide.html'), 'utf8');
const estart = html.indexOf('const E = [');
const E = eval(html.slice(estart, html.indexOf('];', estart) + 2).replace('const E = ', ''));
const mstart = html.indexOf('const METHODS = {');
const METHODS = eval('(' + html.slice(mstart + 'const METHODS = '.length, html.indexOf('};', mstart) + 1) + ')');

const curated = JSON.parse(fs.readFileSync(path.join(SITE, 'curated.json'), 'utf8'));

const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// ---- rsif framework docs (framework/docs/*.md -> site/framework/*.html) ----
// `node site/generate.mjs --docs-only` builds just these pages, fully offline
// (no arxiv / repo-README fetching) - convenient while iterating on the docs.
const DOCS_ONLY = process.argv.includes('--docs-only');
const DOCS_ROOT = path.join(ROOT, 'framework', 'docs');
const DOCS_MANIFEST = [
  { group: 'Start', items: ['index.md', 'primer.md', 'walkthrough.md', 'quickstart.md', 'faq.md'] },
  { group: 'Understand', items: ['architecture.md', 'concepts.md', 'lifecycle.md'] },
  { group: 'Component guides', items: ['components/artifacts.md', 'components/engine.md', 'components/runtime.md', 'components/memory.md', 'components/objectives.md', 'components/efficiency.md', 'components/safety.md', 'components/observability.md'] },
  { group: 'Reference & records', items: ['design.md', 'investigation.md', 'plan.md', 'decision-log.md', 'changes.md'] },
];

function docTitle(md, fallback) {
  const m = md.match(/^#\s+(.+)$/m);
  return m ? m[1].trim() : fallback;
}

// relative href from one doc page's directory to another doc's slug
function docHref(fromSlug, toSlug) {
  const fromDir = path.posix.dirname(fromSlug);
  const rel = fromDir === '.' ? toSlug : path.posix.relative(fromDir, toSlug);
  return rel + '.html';
}

function rewriteDocLinks(html, slug) {
  const known = new Set(DOCS_MANIFEST.flatMap((g) => g.items).map((i) => i.replace(/\.md$/, '')));
  const fromDir = path.posix.dirname(slug);
  return html.replace(/(<a\s[^>]*?href=")([^"]+?\.md(?:#[^"]*)?)(")/g, (m, pre, href, post) => {
    const hashSplit = href.split('#');
    const target = path.posix.normalize(path.posix.join(fromDir === '.' ? '' : fromDir, hashSplit[0])).replace(/\.md$/, '');
    if (known.has(target)) {
      const rel = fromDir === '.' ? target : path.posix.relative(fromDir, target);
      return pre + rel + '.html' + (hashSplit[1] !== undefined ? '#' + hashSplit[1] : '') + post;
    }
    return m; // outside the docs tree: leave untouched (still valid on GitHub)
  });
}

function buildFrameworkDocs() {
  const flat = DOCS_MANIFEST.flatMap((g) => g.items);
  const bySlug = new Map(flat.map((item) => [item.replace(/\.md$/, ''), item]));
  const sidebarFor = (cur) => DOCS_MANIFEST.map((g) => {
    const links = g.items.filter((i) => i !== cur).map((i) => {
      const slug = i.replace(/\.md$/, '');
      const md = fs.readFileSync(path.join(DOCS_ROOT, i), 'utf8');
      return `<a href="${esc(docHref(cur.replace(/\.md$/, ''), slug))}">${esc(docTitle(md, slug))}</a>`;
    }).join('');
    return `<div class="dg">${esc(g.group)}</div>${links}`;
  }).join('');

  let n = 0;
  for (const item of flat) {
    const slug = item.replace(/\.md$/, '');
    const md = fs.readFileSync(path.join(DOCS_ROOT, item), 'utf8');
    const idx = flat.indexOf(item);
    const prev = idx > 0 ? flat[idx - 1] : null;
    const next = idx < flat.length - 1 ? flat[idx + 1] : null;
    const prevSlug = prev && prev.replace(/\.md$/, '');
    const nextSlug = next && next.replace(/\.md$/, '');
    const prevHtml = prev ? `<a class="pn prev" href="${esc(docHref(slug, prevSlug))}">← ${esc(docTitle(fs.readFileSync(path.join(DOCS_ROOT, prev), 'utf8'), prevSlug))}</a>` : '';
    const nextHtml = next ? `<a class="pn next" href="${esc(docHref(slug, nextSlug))}">${esc(docTitle(fs.readFileSync(path.join(DOCS_ROOT, next), 'utf8'), nextSlug))} →</a>` : '';

    const body = rewriteDocLinks(sanitizeHtml(marked.parse(md)), slug);
    const up = '../'.repeat(slug.split('/').length); // site/framework/<...>.html -> site/
    const out = `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>${esc(docTitle(md, slug))} — rsif docs</title><link rel="stylesheet" href="${up}assets/style.css"></head><body><nav class="crumbs"><a href="${up}index.html">← All resources</a> · <a href="${esc(docHref(slug, 'index'))}">rsif docs</a></nav><div class="docs-layout"><aside class="docs-side"><div class="docs-brand"><a href="${esc(docHref(slug, 'index'))}">rsif docs</a></div>${sidebarFor(item)}</aside><main class="docs-main"><article class="readme-html">${body}</article><div class="docs-prevnext">${prevHtml}${nextHtml}</div></main></div></body></html>`;
    const outPath = path.join(SITE, 'framework', slug + '.html');
    fs.mkdirSync(path.dirname(outPath), { recursive: true });
    fs.writeFileSync(outPath, out);
    n++;
  }
  return n;
}

const DOCS_BUILT = buildFrameworkDocs();
if (DOCS_ONLY) {
  console.log(`framework docs: ${DOCS_BUILT} pages -> site/framework/`);
  process.exit(0);
}

// ---- slugs ----
const NON_ARXIV_SLUG = {
  'https://www.nature.com/articles/s41586-023-06924-6': 'nature-funsearch-2024',
  'https://doi.org/10.1038/s41586-026-10265-5': 'nature-ai-scientist-v2-2026',
  'https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2016.00040/full': 'frontiers-quality-diversity-2016',
  'https://openreview.net/forum?id=3tk6AES1Aj': 'openreview-higher-order-evolution-2024',
};
function slugify(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, ''); }
function slugFor(e) {
  if (e.u.startsWith('https://arxiv.org/abs/')) return e.u.split('/abs/')[1];
  if (e.u.startsWith('https://github.com/')) return slugify(e.u.replace(/\/$/, '').split('/').pop());
  return NON_ARXIV_SLUG[e.u] || slugify(e.t);
}
const isRepo = (e) => e.u.startsWith('https://github.com/');

const EXTRA_AUTHORS = {
  'nature-funsearch-2024': 'Bernardino Romera-Paredes, Mohammadamin Barekatain, Alexander Novikov, et al. (Google DeepMind)',
  'nature-ai-scientist-v2-2026': 'Chris Lu, Cong Lu, Robert Tjarko Lange, Yutaro Yamada, Shengran Hu, Jakob Foerster, David Ha, Jeff Clune',
  'frontiers-quality-diversity-2016': 'Justin K. Pugh, Lisa B. Soros, Kenneth O. Stanley',
  'openreview-higher-order-evolution-2024': 'Samuel Coward, Christopher Lu, Alistair Letcher, Minqi Jiang, Jack Parker-Holder, Jakob Foerster',
};
const OPENREVIEW_ABSTRACT = 'Investigates higher-order and self-referential mutations in evolutionary algorithms. Evolving the mutation rate — and recursively the meta-mutation rate, up to a self-referential top-level parameter that modifies itself — improves robustness to initial hyperparameters in Population-based Training (PBT) and Unsupervised Environment Design (UED), and enables more complex adaptation in competitive multi-agent settings.';

const REPO_TO_PAPER = {
  'agentfactory': '2603.18000', 'dgm': '2505.22954', 'godel-agent': '2410.04444',
  'hyperagents': '2603.19461', 'sia': '2605.27276', 'ace': '2510.04618',
  'alma': '2602.07755', 'continual-harness': '2605.09998', 'evoagentx': '2507.03616',
  'evolver': '2510.16079', 'voyager': '2305.16291', 'adas': '2408.08435',
  'ai-scientist': '2408.06292', 'funsearch': 'nature-funsearch-2024', 'mlevolve': '2606.06473',
  'poet': '1901.01753', 'rsiagent': '2609.15364',
};

// ---- cache ----
let cache = fs.existsSync(CACHE) ? JSON.parse(fs.readFileSync(CACHE, 'utf8')) : { arxiv: {}, repos: {}, pdf: {} };

function clean(s) { return String(s ?? '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/\s+/g, ' ').trim(); }

// ---- README rendering (Markdown → HTML) ----
marked.use({ gfm: true, async: false });
function sanitizeHtml(h) {
  return h
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<iframe[\s\S]*?<\/iframe>/gi, '')
    .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
    .replace(/href\s*=\s*(["'])javascript:[^"']*\1/gi, 'href="#"');
}
function renderReadme(md) {
  if (!md) return { html: '', truncated: false };
  const CAP = 16000;
  let src = md, truncated = false;
  if (src.length > CAP) { const cut = src.lastIndexOf('\n', CAP); src = src.slice(0, cut > 0 ? cut : CAP); truncated = true; }
  return { html: sanitizeHtml(marked.parse(src)), truncated };
}

async function arxivMeta(ids) {
  const missing = ids.filter((id) => !cache.arxiv[id]);
  for (let i = 0; i < missing.length; i += 40) {
    const chunk = missing.slice(i, i + 40);
    const r = await fetch(`https://export.arxiv.org/api/query?id_list=${chunk.join(',')}&max_results=${chunk.length}`, { signal: AbortSignal.timeout(40000) });
    const xml = await r.text();
    for (const en of xml.split('<entry>').slice(1)) {
      const idm = en.match(/<id>https?:\/\/arxiv\.org\/abs\/([^<]+)/);
      if (!idm) continue;
      const id = idm[1].replace(/v\d+$/, '');
      const title = (en.match(/<title>([\s\S]*?)<\/title>/) || [])[1];
      const authors = [...en.matchAll(/<name>([^<]*)<\/name>/g)].map((x) => x[1]);
      const summary = (en.match(/<summary>([\s\S]*?)<\/summary>/) || [])[1];
      cache.arxiv[id] = { title: clean(title), authors: authors.join(', '), abstract: clean(summary) };
    }
  }
  return cache.arxiv;
}

async function repoReadme(url) {
  const m = url.match(/github\.com\/([^/]+)\/([^/]+)/);
  if (!m) return null;
  const key = `${m[1]}/${m[2]}`;
  if (cache.repos[key]) return cache.repos[key];
  for (const br of ['main', 'master']) {
    try {
      const r = await fetch(`https://raw.githubusercontent.com/${m[1]}/${m[2]}/${br}/README.md`, { signal: AbortSignal.timeout(15000) });
      if (r.ok) { cache.repos[key] = await r.text(); return cache.repos[key]; }
    } catch {}
  }
  cache.repos[key] = null;
  return null;
}

function pdfAbstract(pdfPath, key) {
  if (cache.pdf[key]) return cache.pdf[key];
  let txt = '';
  try { txt = execSync(`pdftotext -f 1 -l 2 "${pdfPath}" -`, { encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 }); } catch { txt = ''; }
  const norm = txt.replace(/\s+/g, ' ').trim();
  const idx = norm.search(/\babstract\b/i);
  let out = idx >= 0 ? norm.slice(idx) : norm;
  out = out.replace(/^abstract\b[:\s]*/i, '').slice(0, 2000);
  const cut = out.search(/\b(Introduction|Keywords|Received|Accepted|Published|1\.? ?Introduction)\b/i);
  if (cut > 40) out = out.slice(0, cut);
  cache.pdf[key] = out.trim();
  return cache.pdf[key];
}

// ---- build entries ----
const arxivIds = E.filter((e) => e.u.startsWith('https://arxiv.org/abs/')).map((e) => e.u.split('/abs/')[1]);
const arxiv = await arxivMeta(arxivIds);

const pages = [];
for (const e of E) {
  const slug = slugFor(e);
  const repo = isRepo(e);
  const title = repo ? e.t.replace(/\s*\(code\)\s*$/i, '') : e.t;
  const year = (e.v.match(/\b(19|20)\d{2}\b/) || [])[0] || '';
  const depth = e.d;
  let authors = '', abstract = '';
  if (repo) {
    abstract = await repoReadme(e.u);
  } else if (e.u.startsWith('https://arxiv.org/abs/')) {
    const meta = arxiv[e.u.split('/abs/')[1]] || {};
    authors = meta.authors || '';
    abstract = meta.abstract || '';
  } else {
    authors = EXTRA_AUTHORS[slug] || '';
    const pdfKey = { 'nature-funsearch-2024': 'nature-funsearch-2024.pdf', 'nature-ai-scientist-v2-2026': 'nature-ai-scientist-v2-2026.pdf', 'frontiers-quality-diversity-2016': 'frontiers-quality-diversity-2016.pdf' }[slug];
    abstract = pdfKey ? pdfAbstract(path.join(RES, pdfKey), slug) : OPENREVIEW_ABSTRACT;
  }
  pages.push({ slug, title, repo, url: e.u, venue: e.v, year, section: e.s, subsection: e.ss, stage: e.ph, depth, desc: e.desc, note: e.note, authors, abstract, method: METHODS[e.u] || null, curated: curated[slug] || null });
}
fs.writeFileSync(CACHE, JSON.stringify(cache, null, 0));

// ---- helpers ----
const DEPTH_LABEL = { full: 'read fully', skim: 'skim', code: 'hands-on' };
const bySlug = Object.fromEntries(pages.map((p) => [p.slug, p]));
const PHASE_NAMES = ['Foundations & Theory', 'Optimization-as-Language', 'Self-Correction & Verification', 'Memory, Reflection & Skills', 'Harness & Scaffold Evolution', 'Multi-Agent Self-Improvement', 'Self-Modifying Coding', 'Automated AI R&D', 'Evolutionary & Open-Ended', 'Hands-On Repos & Tools'];

const relatedFor = (p) => {
  const idx = pages.indexOf(p);
  const prev = idx > 0 ? pages[idx - 1] : null;
  const next = idx < pages.length - 1 ? pages[idx + 1] : null;
  const siblings = pages.filter((x) => x !== p && x.section === p.section).slice(0, 4);
  return { prev, next, siblings };
};

function linksFor(p) {
  const out = [];
  if (!p.repo) {
    const pdf = p.url.startsWith('https://arxiv.org/abs/')
      ? `../../resources/${p.url.split('/abs/')[1]}.pdf`
      : ({ 'nature-funsearch-2024': '../../resources/nature-funsearch-2024.pdf', 'nature-ai-scientist-v2-2026': '../../resources/nature-ai-scientist-v2-2026.pdf', 'frontiers-quality-diversity-2016': '../../resources/frontiers-quality-diversity-2016.pdf' }[p.slug] || null);
    if (pdf) out.push({ label: 'Local PDF', href: pdf, cls: '' });
    out.push({ label: 'Online', href: p.url, cls: 'alt' });
    for (const [rs, ps] of Object.entries(REPO_TO_PAPER)) if (ps === p.slug) out.push({ label: 'Code', href: `${rs}.html`, cls: 'alt' });
  } else {
    out.push({ label: 'GitHub', href: p.url, cls: '' });
  }
  return out;
}

function badge(depth, venue) {
  const b = { full: 'b-full', skim: 'b-skim', code: 'b-code' }[depth];
  return `<span class="badge b-venue">${esc(venue)}</span><span class="badge ${b}">${DEPTH_LABEL[depth]}</span>`;
}

// ---- detail page ----
function detailPage(p) {
  const { prev, next, siblings } = relatedFor(p);
  const typeLabel = p.repo ? 'REPOSITORY' : 'PAPER';
  const crumbs = `<nav class="crumbs"><a href="../index.html">← All resources</a>${prev ? ` · <a href="${prev.slug}.html">← ${esc(prev.title.slice(0, 40))}</a>` : ''}${next ? ` · <a href="${next.slug}.html">${esc(next.title.slice(0, 40))} →</a>` : ''}</nav>`;
  const head = `<div class="detail-head">
    <div class="kicker">${typeLabel} · stage ${p.stage} · ${esc(p.section)}</div>
    <h1>${esc(p.title)}</h1>
    ${p.authors ? `<p class="authors">${esc(p.authors)}</p>` : ''}
    <p class="meta">${esc(p.venue)}${p.year ? ' · ' + esc(p.year) : ''}</p>
    <div class="links">${linksFor(p).map((l) => `<a class="${l.cls}" href="${l.href}" target="_blank" rel="noopener">${l.label}</a>`).join('')}</div>
  </div>`;

  let body = '';
  if (p.repo) {
    const c = p.curated;
    body += `<section class="block"><h2>What it does</h2><p>${esc(c?.what || p.desc)}</p></section>`;
    if (c?.architecture && c.architecture.length) body += `<section class="block"><h2>How it works</h2><ul>${c.architecture.map((r) => `<li>${esc(r)}</li>`).join('')}</ul></section>`;
    const paper = REPO_TO_PAPER[p.slug] ? bySlug[REPO_TO_PAPER[p.slug]] : null;
    if (paper) body += `<section class="block"><h2>Related paper</h2><p><a href="${paper.slug}.html">${esc(paper.title)}</a></p></section>`;
    if (c?.run) body += `<section class="block"><h2>Install & run</h2><pre class="readme">${esc(c.run)}</pre></section>`;
    body += `<section class="block"><h2>Learning note</h2><p>${esc(c?.note || p.note)}</p></section>`;
    if (p.abstract) {
      const rd = renderReadme(p.abstract);
      body += `<section class="block"><h2>Repo README</h2><div class="readme-html">${rd.html}</div>${rd.truncated ? `<p class="abstract">… (truncated for length) — <a href="${esc(p.url)}" target="_blank" rel="noopener">full README on GitHub</a></p>` : ''}</section>`;
    } else {
      body += `<section class="block"><h2>Repo README</h2><p class="abstract">Could not fetch README (rate-limited or renamed default branch). See the <a href="${esc(p.url)}" target="_blank" rel="noopener">GitHub repo</a>.</p></section>`;
    }
  } else {
    const c = p.curated;
    body += `<section class="block"><h2>TL;DR</h2><div class="tldr"><p style="margin:0">${c ? esc(c.tldr) : esc(p.desc)}</p></div></section>`;
    if (p.abstract) body += `<section class="block"><h2>Abstract</h2><p class="abstract">${esc(p.abstract)}</p></section>`;
    if (c?.method || p.method) body += `<section class="block"><h2>Method</h2><p>${esc((c?.method) || p.method)}</p></section>`;
    if (c) {
      if (c.results && c.results.length) body += `<section class="block"><h2>Key results</h2><ul>${c.results.map((r) => `<li>${esc(r)}</li>`).join('')}</ul></section>`;
      if (c.limitations && c.limitations.length) body += `<section class="block"><h2>Limitations</h2><ul>${c.limitations.map((r) => `<li>${esc(r)}</li>`).join('')}</ul></section>`;
      if (c.fits) body += `<section class="block"><h2>Where it fits the RSI arc</h2><p>${esc(c.fits)}</p></section>`;
      if (c.reading) body += `<section class="block"><h2>How to read it</h2><p>${esc(c.reading)}</p></section>`;
    } else {
      body += `<section class="block"><h2>Learning note</h2><p>${p.note}</p></section>`;
    }
  }

  const relLinks = [prev, next, ...siblings].filter(Boolean);
  const rel = `<section class="block"><h2>Related</h2><div class="related">${relLinks.map((r) => `<a href="${r.slug}.html">${esc(r.title)}<small>${esc(r.venue || r.section)}</small></a>`).join('')}</div></section>`;

  return `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>${esc(p.title)} — RSI Study</title><link rel="stylesheet" href="../assets/style.css"></head><body>${crumbs}<div class="wrap">${head}${body}${rel}<footer>Hand-distilled from the original ${p.repo ? 'repository' : 'paper'} (the abstract/README is included verbatim). Part of the <a href="https://github.com/xzhao/awesome-rsi">awesome-rsi</a> study site.</footer></div></body></html>`;
}

// ---- catalog ----
const SECTIONS = [...new Set(pages.map((p) => p.section))];
const SUBS = { 'Harness-level RSI': ['Prompt & Program Optimization', 'Context & Memory Evolution', 'Harness & Scaffold Evolution', 'Extensible Harness Substrates', 'Self-Verification & Self-Correction', 'Self-Evolving Agent Frameworks'], 'Multi-Agent Self-Improvement': ['Co-Evolution', 'Inference-time Debate'], 'Coding / Software-Engineering Self-Improvement': ['Self-Modifying Coding Agents', 'Iterative Repair & Training'], 'Frameworks & Tools': ['Self-Modifying / Self-Evolving Systems', 'Harness / Memory / Skill Evolution', 'Automated Search / AI R&D'] };

function searchText(p) {
  const parts = [p.title, p.desc, p.note, p.venue, p.year, p.section, p.subsection, p.authors];
  const c = p.curated;
  if (c) {
    for (const k of ['tldr', 'method', 'fits', 'reading', 'what', 'run']) if (typeof c[k] === 'string') parts.push(c[k]);
    for (const k of ['results', 'limitations', 'architecture']) if (Array.isArray(c[k])) parts.push(c[k].join(' '));
  }
  return parts.filter(Boolean).join(' ');
}

function catalog() {
  let items = '';
  for (const s of SECTIONS) {
    const secItems = pages.filter((p) => p.section === s);
    items += `<div class="cat-section"><h2>${esc(s)}</h2></div>`;
    const subs = SUBS[s] || [''];
    for (const sub of subs) {
      const subItems = secItems.filter((p) => p.subsection === sub);
      if (!subItems.length) continue;
      if (sub) items += `<div class="cat-sub">${esc(sub)}</div>`;
      items += subItems.map((p) => `<div class="item" data-search="${esc(searchText(p).toLowerCase())}" data-type="${p.repo ? 'repo' : 'paper'}" data-depth="${p.depth}"><a class="title" href="p/${p.slug}.html">${esc(p.title)}</a><div class="d">${badge(p.depth, p.venue)} ${esc(p.desc)}</div></div>`).join('');
    }
  }
  const js = `<script>
const q=document.getElementById('q'), ft=document.getElementById('ftype'), fd=document.getElementById('fdepth'), none=document.getElementById('none'), cnt=document.getElementById('count');
function refreshSections(){
  document.querySelectorAll('.cat-section').forEach(function(s){var any=false,el=s.nextElementSibling;while(el&&!el.classList.contains('cat-section')){if(el.classList.contains('item')&&el.style.display!=='none')any=true;el=el.nextElementSibling;}s.style.display=any?'':'none';});
  document.querySelectorAll('.cat-sub').forEach(function(s){var any=false,el=s.nextElementSibling;while(el&&!el.classList.contains('cat-sub')&&!el.classList.contains('cat-section')){if(el.classList.contains('item')&&el.style.display!=='none')any=true;el=el.nextElementSibling;}s.style.display=any?'':'none';});
}
function apply(){
  var v=q.value.toLowerCase(), ty=ft.value, dep=fd.value, n=0;
  document.querySelectorAll('.item').forEach(function(i){
    var show=(!v||i.dataset.search.indexOf(v)>-1)&&(ty==='all'||i.dataset.type===ty)&&(dep==='all'||i.dataset.depth===dep);
    i.style.display=show?'':'none'; if(show)n++;
  });
  refreshSections();
  none.style.display=n?'none':'';
  cnt.textContent=n+' shown';
}
q.addEventListener('input',apply); ft.addEventListener('change',apply); fd.addEventListener('change',apply); apply();
</script>`;
  return `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>RSI Study — All Resources</title><link rel="stylesheet" href="assets/style.css"></head><body><div class="catalog-head"><h1>RSI Study</h1><p class="sub">${pages.length} resources, each with a dedicated distilled page. Filter by type and depth, or search keywords, authors, and concepts.</p><div class="fw-cta"><strong>rsif</strong> — the recursive self-improvement framework built from this list. <a href="framework/index.html">Design &amp; implementation docs →</a></div></div><div class="search"><input id="q" type="search" placeholder="Search keywords, authors, concepts…"></div><div class="filters"><label>Type <select id="ftype"><option value="all">All</option><option value="paper">Papers</option><option value="repo">Repositories</option></select></label><label>Depth <select id="fdepth"><option value="all">All</option><option value="full">Read fully</option><option value="skim">Skim</option><option value="code">Hands-on</option></select></label><span id="count" class="count"></span></div><div class="wrap">${items}<div class="empty" id="none" style="display:none">No resources match.</div></div>${js}</body></html>`;
}

// ---- write ----
fs.mkdirSync(P, { recursive: true });
fs.writeFileSync(path.join(SITE, 'index.html'), catalog());
for (const p of pages) fs.writeFileSync(path.join(P, p.slug + '.html'), detailPage(p));

const anchors = pages.filter((p) => p.curated).length;
const reposWithReadme = pages.filter((p) => p.repo && p.abstract).length;
const reposTotal = pages.filter((p) => p.repo).length;
console.log(`generated: ${pages.length} pages (${anchors} anchors hand-distilled, ${reposWithReadme}/${reposTotal} repos with README)`);
console.log(`arxiv metadata: ${Object.keys(cache.arxiv).length} papers`);
