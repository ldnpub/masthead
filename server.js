'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const crypto = require('crypto');

const store = require('./lib/config-store');
const rss = require('./lib/rss');

const ROOT = __dirname;
const PUBLIC = path.join(ROOT, 'public');
const PORT = Number(process.env.PORT || 8741);
const DEMO = process.env.STUDIO_DEMO === '1';
const NO_AUTO = DEMO || process.env.STUDIO_NO_AUTOMATION === '1';

const READ_ONLY = new Set([
  'feed', 'source-items', 'extractors', 'health', 'voices',
  'prompt-template', 'digest-prompt', 'chapters-candidates', 'x-timeline',
]);

const VOICE_SUGGESTIONS = [
  'en-US-AriaNeural',
  'en-US-GuyNeural',
  'en-GB-SoniaNeural',
  'en-GB-RyanNeural',
  'fr-FR-VivienneMultilingualNeural',
  'fr-FR-DeniseNeural',
  'fr-FR-HenriNeural',
  'es-ES-ElviraNeural',
  'de-DE-KatjaNeural',
  'pt-BR-FranciscaNeural',
];

const jobs = [];
let draining = false;
let bootedAt = new Date().toISOString();

const demoInbox = [
  {
    id: 'desk-late-wire',
    url: 'https://example-press.test/notes/late-wire',
    title: 'Late wire from a paper that does not exist',
    receivedAt: '2026-10-12T08:05:00.000Z',
    status: 'queued',
    label: 'web',
  },
  {
    id: 'desk-city-post',
    url: 'https://example-press.test/wire/2041',
    title: 'The late edition is a voice now',
    receivedAt: '2026-10-11T21:16:00.000Z',
    status: 'published',
    label: 'x-post',
  },
];

if (DEMO) {
  jobs.push({
    id: 'job-night-press',
    command: 'article',
    status: 'done',
    summary: 'The night the presses learned to speak',
    createdAt: '2026-10-09T06:31:00.000Z',
    finishedAt: '2026-10-09T06:36:00.000Z',
    log: [
      'Sample shelf. The voice service was not contacted.',
      'Chapters written for the night-press essay.',
    ],
  });
}

function dataDir() {
  return process.env.MASTHEAD_DATA || path.join(ROOT, 'data');
}

function configFile() {
  if (process.env.STUDIO_CONFIG) return process.env.STUDIO_CONFIG;
  if (DEMO) {
    const session = path.join(dataDir(), 'demo-session.json');
    if (fs.existsSync(session)) return session;
    return path.join(ROOT, 'examples', 'demo-config.json');
  }
  const local = path.join(ROOT, 'studio-config.json');
  if (fs.existsSync(local)) return local;
  return local;
}

function readConfig() {
  try {
    return JSON.parse(fs.readFileSync(configFile(), 'utf8'));
  } catch {
    try {
      return JSON.parse(fs.readFileSync(path.join(ROOT, 'studio-config.example.json'), 'utf8'));
    } catch {
      return {};
    }
  }
}

function writeConfig(cfg) {
  let file = configFile();
  if (DEMO && path.basename(file) === 'demo-config.json') {
    file = path.join(dataDir(), 'demo-session.json');
  }
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(cfg, null, 2) + '\n');
  fs.chmodSync(tmp, 0o600);
  fs.renameSync(tmp, file);
}

function listenHost(cfg) {
  if (process.env.HOST) return process.env.HOST;
  const full = store.withDefaults(cfg);
  return full.server && full.server.listenAll ? '0.0.0.0' : '127.0.0.1';
}

function loopback(req) {
  const addr = req.socket.remoteAddress || '';
  return addr === '127.0.0.1' || addr === '::1' || addr === '::ffff:127.0.0.1';
}

function scrub(text) {
  return String(text || '').replace(/https?:\/\/[^\s'")]+/g, (url) => {
    try {
      const u = new URL(url);
      u.search = '';
      u.hash = '';
      return u.toString();
    } catch {
      return url.split('?')[0];
    }
  });
}

function send(res, status, body, headers) {
  const payload = typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body);
  const type = typeof body === 'string'
    ? 'text/html; charset=utf-8'
    : Buffer.isBuffer(body)
      ? 'application/octet-stream'
      : 'application/json; charset=utf-8';
  res.writeHead(status, Object.assign({ 'Content-Type': type, 'Cache-Control': 'no-store' }, headers));
  res.end(payload);
}

function readBody(req, limit = 1_000_000) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(Object.assign(new Error('Body too large'), { status: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      if (!raw) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch {
        reject(Object.assign(new Error('Expected JSON'), { status: 400 }));
      }
    });
    req.on('error', reject);
  });
}

function runPython(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn('python3', [path.join(ROOT, 'engine', 'studio.py'), command, '-'], {
      cwd: ROOT,
      env: process.env,
    });
    let out = '';
    let err = '';
    const lines = [];
    child.stdout.on('data', (buf) => {
      out += buf.toString('utf8');
    });
    child.stderr.on('data', (buf) => {
      err += buf.toString('utf8');
    });
    child.stdin.end(JSON.stringify(args || {}));
    child.on('close', (code) => {
      const resultLine = out.trim().split('\n').filter((line) => line.startsWith('RESULT ')).pop();
      for (const line of out.split('\n')) {
        if (!line.startsWith('RESULT ') && line.trim()) lines.push(scrub(line).slice(0, 400));
      }
      if (!resultLine) {
        const error = new Error(scrub(err || out).slice(-500) || 'The engine returned nothing.');
        error.log = lines;
        error.status = 500;
        return reject(error);
      }
      let payload;
      try {
        payload = JSON.parse(resultLine.slice('RESULT '.length));
      } catch {
        return reject(Object.assign(new Error('The engine returned malformed JSON.'), { log: lines, status: 500 }));
      }
      if (!payload.ok) {
        const error = new Error(payload.error || 'The engine failed.');
        error.log = lines;
        error.status = code === 2 ? 400 : 500;
        return reject(error);
      }
      resolve({ result: payload.result, log: lines });
    });
  });
}

function publicJob(job) {
  return {
    id: job.id,
    command: job.command,
    status: job.status,
    summary: job.summary,
    createdAt: job.createdAt,
    finishedAt: job.finishedAt || null,
    error: job.error || null,
    log: job.log || [],
  };
}

function summarize(command, args) {
  args = args || {};
  if (args.url) return scrub(args.url);
  if (Array.isArray(args.urls) && args.urls.length) return args.urls.map(scrub).join(' · ');
  if (args.handle) return '@' + String(args.handle).replace(/^@/, '');
  if (args.title) return String(args.title).slice(0, 140);
  if (args.sujet) return String(args.sujet).slice(0, 140);
  if (args.id) return String(args.id);
  return command;
}

async function drain() {
  if (draining) return;
  draining = true;
  try {
    while (true) {
      const job = jobs.find((item) => item.status === 'queued');
      if (!job) break;
      job.status = 'running';
      job.startedAt = new Date().toISOString();
      try {
        const { result, log } = await runPython(job.command, job._args || {});
        job.status = 'done';
        job.result = result;
        job.log = (job.log || []).concat(log).slice(-40);
      } catch (err) {
        job.status = 'failed';
        job.error = err.message;
        job.log = (job.log || []).concat(err.log || []).slice(-40);
      }
      job.finishedAt = new Date().toISOString();
    }
  } finally {
    draining = false;
  }
}

function uiLang() {
  return store.withDefaults(readConfig()).ui.lang === 'fr' ? 'fr' : 'en';
}

function enqueue(command, args) {
  if (DEMO && !READ_ONLY.has(command)) {
    const error = new Error(uiLang() === 'fr'
      ? 'L’étagère d’exemple est en lecture seule. Arrêtez la démo et lancez npm start pour enregistrer.'
      : 'The sample shelf is read-only. Stop the demo and run npm start to record.');
    error.status = 403;
    throw error;
  }
  if (!/^[a-z0-9-]{1,40}$/.test(command)) {
    const error = new Error('Unknown command.');
    error.status = 400;
    throw error;
  }
  const job = {
    id: 'job-' + crypto.randomBytes(6).toString('hex'),
    command,
    status: 'queued',
    summary: summarize(command, args),
    createdAt: new Date().toISOString(),
    log: [],
    _args: args || {},
  };
  jobs.unshift(job);
  if (jobs.length > 80) jobs.pop();
  setImmediate(drain);
  return publicJob(job);
}

function inboxPath() {
  return path.join(dataDir(), 'inbox.json');
}

function readInbox() {
  if (DEMO) return { items: demoInbox.map((item) => ({ ...item })) };
  try {
    const data = JSON.parse(fs.readFileSync(inboxPath(), 'utf8'));
    if (Array.isArray(data.items)) return data;
  } catch { /* empty desk */ }
  return { items: [] };
}

function writeInbox(data) {
  if (DEMO) {
    const error = new Error('The sample shelf does not accept shares.');
    error.status = 403;
    throw error;
  }
  fs.mkdirSync(dataDir(), { recursive: true });
  fs.writeFileSync(inboxPath(), JSON.stringify(data, null, 2) + '\n');
}

function inboxToken() {
  return ((readConfig().inbox || {}).token) || '';
}

function tokenOk(presented) {
  const expected = inboxToken();
  if (!expected || !presented) return false;
  const a = crypto.createHash('sha256').update(String(presented)).digest();
  const b = crypto.createHash('sha256').update(String(expected)).digest();
  return crypto.timingSafeEqual(a, b);
}

function classifyLabel(url) {
  try {
    const host = new URL(url).hostname.toLowerCase();
    if (/(^|\.)(x|twitter|fxtwitter)\.com$/.test(host)) {
      return /\/status(?:es)?\/\d+/.test(url) ? 'x-post' : 'x-profile';
    }
    if (/(youtube\.com|youtu\.be|vimeo\.com|dailymotion\.com|tiktok\.com)$/.test(host)) return 'video';
    return 'web';
  } catch {
    return 'invalid';
  }
}

function demoTimeline(handle) {
  return {
    handle,
    posts: [
      {
        id: '2041',
        url: 'https://example-press.test/wire/2041',
        text: 'The late edition is a voice now. The stone stays, the lamp stays, and the column walks out of the building.',
        chars: 112,
        date: 1760217240,
        isReply: false,
        hasVideo: false,
        published: true,
      },
      {
        id: '2044',
        url: 'https://example-press.test/wire/2044',
        text: 'Margin note, not for the front: a half-inch rule is a promise to the reader that the column will stop.',
        chars: 104,
        date: 1760300000,
        isReply: false,
        hasVideo: false,
        published: false,
      },
    ],
  };
}

let libraryCache = { at: 0, data: null };

async function library() {
  if (libraryCache.data && Date.now() - libraryCache.at < 3000) return libraryCache.data;
  const { result } = await runPython('feed', {});
  libraryCache = { at: Date.now(), data: result };
  return result;
}

function baseUrl(req, cfg) {
  const explicit = ((cfg.publish || {}).publicBaseUrl || '').trim().replace(/\/$/, '');
  if (explicit) return explicit;
  const hostHeader = req.headers.host || `127.0.0.1:${PORT}`;
  return `http://${hostHeader}`;
}

function decorateEpisode(episode, base) {
  const id = episode.id;
  const audioUrl = episode.audioUrl || `${base}/audio/${encodeURIComponent(id)}.mp3`;
  const chaptersUrl = episode.chapters ? `${base}/chapters/${encodeURIComponent(id)}.json` : '';
  return Object.assign({}, episode, {
    audioUrl,
    chaptersUrl,
    link: episode.link || audioUrl,
  });
}

async function buildFeed(req, kind) {
  const cfg = store.withDefaults(readConfig());
  const spec = rss.FEEDS.find((item) => item.kind === kind);
  const lib = await library();
  const base = lib.baseUrl || baseUrl(req, cfg);
  const lang = rss.langCode(cfg.ui.lang);
  const copy = rss.feedCopy(kind, lang);
  const items = (lib.episodes || [])
    .filter((episode) => rss.matches(episode, kind))
    .map((episode) => decorateEpisode(episode, base));
  const self = base + spec.path;
  return rss.buildRss({
    title: copy[0],
    description: copy[1],
    language: lang,
    author: cfg.publish.author || 'Masthead',
    link: base,
    selfUrl: self,
    imageUrl: `${base}/covers/${spec.cover}.png`,
    categories: spec.categories,
    items,
  });
}

function safeId(value) {
  return /^[A-Za-z0-9._-]{1,160}$/.test(value || '');
}

function serveRange(req, res, file, type) {
  const stat = fs.statSync(file);
  const header = req.headers.range;
  if (header) {
    const match = /^bytes=(\d*)-(\d*)$/.exec(header);
    if (!match) {
      res.writeHead(416, { 'Content-Range': `bytes */${stat.size}` });
      res.end();
      return;
    }
    let start = match[1] === '' ? NaN : Number(match[1]);
    let end = match[2] === '' ? NaN : Number(match[2]);
    if (Number.isNaN(start)) {
      const tail = Number.isNaN(end) ? stat.size : end;
      start = Math.max(0, stat.size - tail);
      end = stat.size - 1;
    } else if (Number.isNaN(end)) {
      end = stat.size - 1;
    }
    if (start < 0 || end >= stat.size || start > end) {
      res.writeHead(416, { 'Content-Range': `bytes */${stat.size}` });
      res.end();
      return;
    }
    res.writeHead(206, {
      'Content-Type': type,
      'Content-Length': end - start + 1,
      'Content-Range': `bytes ${start}-${end}/${stat.size}`,
      'Accept-Ranges': 'bytes',
      'Cache-Control': 'no-store',
    });
    fs.createReadStream(file, { start, end }).pipe(res);
    return;
  }
  res.writeHead(200, {
    'Content-Type': type,
    'Content-Length': stat.size,
    'Accept-Ranges': 'bytes',
    'Cache-Control': 'no-store',
  });
  fs.createReadStream(file).pipe(res);
}

function chaptersFor(id) {
  const local = path.join(dataDir(), 'chapters', `${id}.json`);
  if (fs.existsSync(local)) return fs.readFileSync(local, 'utf8');
  if (DEMO) {
    const sample = JSON.parse(fs.readFileSync(path.join(ROOT, 'examples', 'demo-chapters.json'), 'utf8'));
    if (sample[id]) return JSON.stringify(sample[id]);
  }
  return null;
}

function contentType(file) {
  const ext = path.extname(file).toLowerCase();
  return {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.json': 'application/json; charset=utf-8',
    '.webmanifest': 'application/manifest+json',
    '.ttf': 'font/ttf',
    '.txt': 'text/plain; charset=utf-8',
    '.mp3': 'audio/mpeg',
  }[ext] || 'application/octet-stream';
}

function serveStatic(req, res, urlPath) {
  const decoded = decodeURIComponent(urlPath.split('?')[0]);
  const file = path.normalize(path.join(PUBLIC, decoded));
  if (!file.startsWith(PUBLIC)) {
    send(res, 403, { error: 'Forbidden' });
    return;
  }
  if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
    if (!path.extname(decoded)) {
      const index = path.join(PUBLIC, 'index.html');
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      fs.createReadStream(index).pipe(res);
      return;
    }
    send(res, 404, { error: 'Not found' });
    return;
  }
  res.writeHead(200, { 'Content-Type': contentType(file), 'Cache-Control': file.includes('/fonts/') ? 'public, max-age=86400' : 'no-store' });
  fs.createReadStream(file).pipe(res);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function inlineMd(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
}

function renderGuide() {
  const lines = fs.readFileSync(path.join(ROOT, 'docs', 'private-feeds.md'), 'utf8').split('\n');
  let body = '';
  let para = [];
  let inCode = false;
  let inList = false;
  const flush = () => {
    if (para.length) {
      body += `<p>${para.map(inlineMd).join(' ')}</p>`;
      para = [];
    }
    if (inList) {
      body += '</ul>';
      inList = false;
    }
  };
  for (const line of lines) {
    if (line.startsWith('```')) {
      if (inCode) {
        body += '</code></pre>';
        inCode = false;
      } else {
        flush();
        body += '<pre><code>';
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      body += escapeHtml(line) + '\n';
      continue;
    }
    if (!line.trim()) {
      flush();
      continue;
    }
    const heading = /^(#{1,3}) (.+)$/.exec(line);
    if (heading) {
      flush();
      const level = heading[1].length;
      body += `<h${level}>${inlineMd(heading[2])}</h${level}>`;
      continue;
    }
    if (line.startsWith('- ')) {
      if (para.length) flush();
      if (!inList) {
        body += '<ul>';
        inList = true;
      }
      body += `<li>${inlineMd(line.slice(2))}</li>`;
      continue;
    }
    if (inList) flush();
    para.push(line);
  }
  flush();
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Private feeds — Masthead</title>
  <link rel="stylesheet" href="/fonts/fonts.css">
  <link rel="stylesheet" href="/styles.css">
</head>
<body class="guide">
  <header class="top">
    <a class="brand" href="/">
      <img src="/logo.svg" alt="" width="48" height="48">
      <span class="wordmark-row"><span class="wordmark">Masthead</span> <abbr class="beta" title="Beta. Expect breaking changes before 1.0.">BETA</abbr></span>
    </a>
    <p class="tagline">Private sources, for your own ears.</p>
  </header>
  <main class="guide-body">${body}</main>
</body>
</html>`;
}

async function handle(req, res) {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const pathname = url.pathname;
  try {
    if (req.method === 'GET' && pathname === '/api/bootstrap') {
      const cfg = readConfig();
      const [lib, sources, extractors] = await Promise.all([
        runPython('feed', {}).then((r) => r.result),
        runPython('source-items', {}).then((r) => r.result),
        runPython('extractors', {}).then((r) => r.result),
      ]);
      libraryCache = { at: Date.now(), data: lib };
      return send(res, 200, {
        demo: DEMO,
        bootedAt,
        config: store.redactConfig(cfg),
        feed: lib,
        sources,
        extractors,
        jobs: jobs.map(publicJob),
        inbox: readInbox(),
        voices: VOICE_SUGGESTIONS,
        listenAll: !!store.withDefaults(cfg).server.listenAll,
      });
    }

    if (req.method === 'GET' && pathname === '/api/config') {
      return send(res, 200, store.redactConfig(readConfig()));
    }

    if (req.method === 'PUT' && pathname === '/api/config') {
      const patch = await readBody(req);
      const next = store.mergeConfig(readConfig(), patch);
      writeConfig(next);
      return send(res, 200, store.redactConfig(next));
    }

    if (req.method === 'GET' && pathname === '/api/share') {
      if (!loopback(req)) {
        return send(res, 403, { error: 'Open Masthead on the computer that runs it to see the inbox token.' });
      }
      const cfg = readConfig();
      let token = (cfg.inbox || {}).token || '';
      if (!token && !DEMO) {
        token = crypto.randomBytes(24).toString('hex');
        cfg.inbox = Object.assign({}, cfg.inbox, { token });
        writeConfig(cfg);
      }
      const base = baseUrl(req, store.withDefaults(cfg));
      return send(res, 200, {
        token: token || '',
        inboxUrl: base + '/inbox',
        feeds: rss.FEEDS.map((feed) => ({ kind: feed.kind, url: base + feed.path })),
      });
    }

    if (req.method === 'POST' && pathname === '/api/jobs') {
      const body = await readBody(req);
      const command = String(body.command || '');
      return send(res, 202, enqueue(command, body.args || {}));
    }

    if (req.method === 'GET' && pathname === '/api/jobs') {
      return send(res, 200, { jobs: jobs.map(publicJob) });
    }

    if (req.method === 'GET' && pathname === '/api/inbox') {
      return send(res, 200, readInbox());
    }

    if (req.method === 'POST' && pathname === '/api/inbox/ack') {
      const body = await readBody(req);
      const updates = new Map((body.items || []).map((item) => [item.id, item.status || 'ignored']));
      if (DEMO) {
        for (const item of demoInbox) {
          if (updates.has(item.id)) item.status = updates.get(item.id);
        }
        return send(res, 200, readInbox());
      }
      const data = readInbox();
      for (const item of data.items) {
        if (updates.has(item.id)) item.status = updates.get(item.id);
      }
      writeInbox(data);
      return send(res, 200, data);
    }

    if (req.method === 'GET' && pathname === '/inbox/list') {
      if (!tokenOk(req.headers['x-inbox-token'])) {
        return send(res, 401, { error: 'The inbox refused the token.' });
      }
      const data = readInbox();
      data.items = data.items.map((item) => Object.assign({}, item, { url: scrub(item.url) }));
      return send(res, 200, data);
    }

    if (req.method === 'POST' && pathname === '/inbox/ack') {
      if (!tokenOk(req.headers['x-inbox-token'])) {
        return send(res, 401, { error: 'The inbox refused the token.' });
      }
      const body = await readBody(req);
      const updates = new Map((body.items || []).map((item) => [item.id, item.status || 'ignored']));
      if (DEMO) {
        for (const item of demoInbox) {
          if (updates.has(item.id)) item.status = updates.get(item.id);
        }
        return send(res, 200, { ok: true });
      }
      const data = readInbox();
      for (const item of data.items) {
        if (updates.has(item.id)) item.status = updates.get(item.id);
      }
      writeInbox(data);
      return send(res, 200, { ok: true });
    }

    if (req.method === 'POST' && (pathname === '/inbox' || pathname === '/inbox/submit')) {
      const header = req.headers['x-inbox-token'];
      const cookie = /(?:^|;\s*)mh_k=([^;]+)/.exec(req.headers.cookie || '');
      if (!tokenOk(header || (cookie && decodeURIComponent(cookie[1])))) {
        return send(res, 401, { error: 'The inbox refused the token.' });
      }
      const body = await readBody(req);
      const target = String(body.url || body.text || '').trim();
      const found = target.match(/https?:\/\/[^\s]+/);
      if (!found) return send(res, 400, { error: 'No URL in that share.' });
      const item = {
        id: 'in-' + crypto.randomBytes(6).toString('hex'),
        url: found[0],
        title: String(body.title || '').slice(0, 180),
        receivedAt: new Date().toISOString(),
        status: 'queued',
        label: classifyLabel(found[0]),
      };
      const data = readInbox();
      data.items.unshift(item);
      writeInbox(data);
      return send(res, 201, { ok: true, id: item.id, label: item.label });
    }

    if (req.method === 'GET' && pathname === '/api/x/timeline') {
      const handle = (url.searchParams.get('handle') || 'citydesk').replace(/^@/, '');
      if (DEMO) return send(res, 200, demoTimeline(handle));
      const { result } = await runPython('x-timeline', { handle, count: 20 });
      return send(res, 200, result);
    }

    if (req.method === 'GET' && pathname === '/api/health') {
      const { result } = await runPython('health', {});
      return send(res, 200, result);
    }

    const feed = rss.FEEDS.find((item) => item.path === pathname || item.aliases.includes(pathname));
    if (req.method === 'GET' && feed && pathname !== '/') {
      const xml = await buildFeed(req, feed.kind);
      return send(res, 200, xml, { 'Content-Type': 'application/rss+xml; charset=utf-8' });
    }
    if (req.method === 'GET' && (pathname === '/rss' || pathname === '/feed.xml')) {
      const xml = await buildFeed(req, 'article');
      return send(res, 200, xml, { 'Content-Type': 'application/rss+xml; charset=utf-8' });
    }

    const audio = pathname.match(/^\/audio\/([^/]+)\.mp3$/);
    if (req.method === 'GET' && audio) {
      const id = decodeURIComponent(audio[1]);
      if (!safeId(id)) return send(res, 400, { error: 'Bad episode id.' });
      const file = path.join(dataDir(), 'episodes', `${id}.mp3`);
      if (!fs.existsSync(file)) {
        return send(res, 404, { error: DEMO ? 'Sample episodes have no audio file. Record one with npm start.' : 'No audio for that episode yet.' });
      }
      return serveRange(req, res, file, 'audio/mpeg');
    }

    const chapter = pathname.match(/^\/chapters\/([^/]+)\.json$/);
    if (req.method === 'GET' && chapter) {
      const id = decodeURIComponent(chapter[1]);
      if (!safeId(id)) return send(res, 400, { error: 'Bad episode id.' });
      const raw = chaptersFor(id);
      if (!raw) return send(res, 404, { error: 'No chapters for that episode.' });
      return send(res, 200, raw, { 'Content-Type': 'application/json; charset=utf-8' });
    }

    if (req.method === 'GET' && pathname === '/guide') {
      return send(res, 200, renderGuide());
    }

    if (req.method === 'GET' || req.method === 'HEAD') {
      if (pathname === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        fs.createReadStream(path.join(PUBLIC, 'index.html')).pipe(res);
        return;
      }
      return serveStatic(req, res, pathname);
    }

    send(res, 405, { error: 'Method not allowed' });
  } catch (err) {
    const status = err.status || 500;
    send(res, status, { error: err.message || 'The desk failed.' });
  }
}

function tickAutomation() {
  if (NO_AUTO) return;
  const cfg = store.withDefaults(readConfig());
  const now = new Date();
  const key = now.toISOString().slice(0, 13);
  if (cfg.scheduler.enabled && now.getHours() === Number(cfg.scheduler.hour) && now.getMinutes() === Number(cfg.scheduler.minute)) {
    if (!jobs.some((job) => job.command === 'auto-import' && job.createdAt.slice(0, 13) === key)) {
      try { enqueue('auto-import', { count: cfg.scheduler.count }); } catch { /* read-only */ }
    }
  }
}

if (require.main === module) {
  const cfg = readConfig();
  const host = listenHost(cfg);
  const server = http.createServer((req, res) => {
    handle(req, res).catch((err) => {
      if (!res.headersSent) send(res, 500, { error: err.message || 'The desk failed.' });
    });
  });
  server.listen(PORT, host, () => {
    const shown = host === '0.0.0.0' ? '127.0.0.1' : host;
    console.log(JSON.stringify({
      message: 'masthead listening',
      url: `http://${shown}:${PORT}`,
      demo: DEMO,
      host,
    }));
    if (host === '0.0.0.0') {
      console.log(JSON.stringify({
        message: 'listenAll is on. The dashboard, feed URLs, and anyone on this network who can reach the port can open the desk.',
      }));
    }
  });
  setInterval(tickAutomation, 30_000).unref();
  bootedAt = new Date().toISOString();
}

module.exports = { readConfig, redactPath: store.redactConfig, enqueue, DEMO };
