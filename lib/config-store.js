'use strict';

const SECRET_KEYS = ['token', 'password', 'cookie', 'value'];

function stripQuery(url) {
  try {
    const u = new URL(url);
    u.search = '';
    u.hash = '';
    return u.toString();
  } catch {
    return String(url || '').split('#')[0].split('?')[0];
  }
}

function withDefaults(cfg) {
  cfg = cfg || {};
  return {
    ui: { lang: 'en', timezone: '', wizardDismissed: false, ...(cfg.ui || {}) },
    tts: { engine: 'edge', voice: 'en-US-AriaNeural', rate: 0, piperModel: '', ...(cfg.tts || {}) },
    publish: { publicBaseUrl: '', author: 'Masthead', title: 'Masthead', ...(cfg.publish || {}) },
    cloudflare: { accountId: '', bucket: '', ...(cfg.cloudflare || {}) },
    llm: { provider: 'none', baseUrl: '', model: '', ...(cfg.llm || {}) },
    scheduler: { count: 2, hour: 7, minute: 0, enabled: false, ...(cfg.scheduler || {}) },
    server: { listenAll: false, autostart: false, ...(cfg.server || {}) },
    inbox: { ...(cfg.inbox || {}) },
    xFollow: {
      handles: [],
      intervalHours: 3,
      digestHour: 8,
      digestWeekday: 0,
      schedulerEnabled: false,
      accounts: {},
      ...(cfg.xFollow || {}),
    },
    sources: Array.isArray(cfg.sources) ? cfg.sources : [],
  };
}

function redactAuth(auth) {
  const out = { ...(auth || {}) };
  for (const key of SECRET_KEYS) {
    out[key + 'Set'] = !!out[key];
    delete out[key];
  }
  if (out.headers && typeof out.headers === 'object' && Object.keys(out.headers).length) out.headersSet = true;
  delete out.headers;
  return out;
}

function publicSource(source) {
  const auth = redactAuth(source.auth);
  let feedUrl = source.feedUrl || '';
  let feedQuerySet = false;
  try {
    const u = new URL(feedUrl);
    if (u.search) {
      feedQuerySet = true;
      u.search = '';
      feedUrl = u.toString();
    }
  } catch { /* keep the raw value if it is not a URL yet */ }
  return {
    id: source.id,
    label: source.label || source.id,
    feedUrl,
    feedQuerySet,
    extractor: source.extractor || 'auto',
    auth,
  };
}

function redactConfig(cfg) {
  const full = withDefaults(cfg);
  full.cloudflare = redactAuth({ ...full.cloudflare, token: full.cloudflare.token });
  // redactAuth only knows SECRET_KEYS. accountId and bucket must stay.
  full.cloudflare.accountId = (cfg.cloudflare || {}).accountId || '';
  full.cloudflare.bucket = (cfg.cloudflare || {}).bucket || '';
  full.cloudflare.tokenSet = !!((cfg.cloudflare || {}).token);
  delete full.cloudflare.token;
  delete full.cloudflare.passwordSet;
  delete full.cloudflare.cookieSet;
  delete full.cloudflare.valueSet;
  delete full.cloudflare.headersSet;

  full.llm = { ...full.llm };
  full.llm.apiKeySet = !!((cfg.llm || {}).apiKey);
  delete full.llm.apiKey;

  full.inbox = { tokenSet: !!((cfg.inbox || {}).token) };
  full.sources = (full.sources || []).map(publicSource);
  return full;
}

function mergeAuth(prev, next) {
  const out = { ...(prev || {}) };
  next = next || {};
  for (const [key, value] of Object.entries(next)) {
    if (key.endsWith('Set')) continue;
    if (SECRET_KEYS.includes(key)) {
      if (value === '' || value == null) continue;
      if (value === '__clear__') {
        delete out[key];
        continue;
      }
    }
    if (key === 'headers') {
      if (!value || typeof value !== 'object' || !Object.keys(value).length) continue;
      out.headers = value;
      continue;
    }
    out[key] = value;
  }
  return out;
}

function mergeSources(existing, incoming) {
  const byId = new Map((existing || []).map((s) => [s.id, s]));
  const seen = new Set();
  const out = [];
  for (const source of incoming || []) {
    const prev = byId.get(source.id) || {};
    const id = String(source.id || prev.id || '').trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    let feedUrl = prev.feedUrl || '';
    if (source.feedUrl) {
      const typed = String(source.feedUrl).trim();
      const prevStripped = prev.feedUrl ? stripQuery(prev.feedUrl) : '';
      if (prev.feedUrl && (typed === prev.feedUrl || typed === prevStripped)) feedUrl = prev.feedUrl;
      else feedUrl = typed;
    }
    out.push({
      id,
      label: String(source.label || prev.label || id).slice(0, 120),
      feedUrl,
      extractor: String(source.extractor || prev.extractor || 'auto').slice(0, 80),
      auth: mergeAuth(prev.auth, source.auth),
    });
  }
  return out.filter((s) => s.id && s.feedUrl);
}

function mergeConfig(cfg, patch) {
  // Clone the raw config so secrets that withDefaults would not name still survive.
  const base = JSON.parse(JSON.stringify(cfg || {}));
  for (const sec of ['cloudflare', 'tts', 'llm', 'scheduler', 'ui', 'server', 'inbox', 'publish', 'xFollow']) {
    if (!patch[sec] || typeof patch[sec] !== 'object') continue;
    base[sec] = { ...(base[sec] || {}) };
    for (const [key, value] of Object.entries(patch[sec])) {
      if (key.endsWith('Set')) continue;
      const secret = (sec === 'cloudflare' && key === 'token')
        || (sec === 'llm' && key === 'apiKey')
        || (sec === 'inbox' && key === 'token');
      if (secret && (value === '' || value == null)) continue;
      if (secret && value === '__clear__') {
        delete base[sec][key];
        continue;
      }
      base[sec][key] = value;
    }
  }
  if (Array.isArray(patch.sources)) base.sources = mergeSources(cfg.sources || [], patch.sources);
  return base;
}

module.exports = {
  stripQuery,
  withDefaults,
  publicSource,
  redactConfig,
  mergeAuth,
  mergeSources,
  mergeConfig,
};
