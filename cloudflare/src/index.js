/**
 * Masthead feeds. One Worker, one R2 bucket, five RSS paths.
 * Secrets arrive as wrangler secrets (INBOX_TOKEN). Nothing here is an account id.
 */

const FEEDS = [
  { kind: 'article', path: '/feed.xml', aliases: ['/rss'], cover: 'articles', categories: ['News', 'Society & Culture'] },
  { kind: 'x', path: '/x.xml', aliases: ['/x'], cover: 'x', categories: ['News', 'Technology'] },
  { kind: 'video', path: '/videos.xml', aliases: ['/videos'], cover: 'videos', categories: ['TV & Film'] },
  { kind: 'learn', path: '/learn.xml', aliases: ['/learn'], cover: 'learn', categories: ['Education', 'Science'] },
  { kind: 'web', path: '/readings.xml', aliases: ['/readings'], cover: 'readings', categories: ['Society & Culture', 'Arts'] },
];

const COPY = {
  en: {
    article: ['Masthead — Articles', 'Full readings from feeds you chose. Personal use. You are responsible for the rights to anything in this feed.'],
    x: ['Masthead — The Wire', 'Posts and threads read aloud. Personal use. You are responsible for the rights to this feed.'],
    video: ['Masthead — Screen', 'Soundtracks lifted from videos for personal listening. You are responsible for the rights.'],
    learn: ['Masthead — Lessons', 'Short lessons you wrote or generated, read aloud. Personal use.'],
    web: ['Masthead — Readings', 'Web pages you sent to the desk, read aloud. Personal use. You are responsible for the rights.'],
  },
  fr: {
    article: ['Masthead — Articles', 'Lectures intégrales des flux que vous avez choisis. Usage personnel. Vous êtes responsable des droits sur ce flux.'],
    x: ['Masthead — Le fil', 'Posts et fils lus à voix haute. Usage personnel. Vous êtes responsable des droits sur ce flux.'],
    video: ['Masthead — Écran', 'Bandes-son de vidéos, pour une écoute personnelle. Vous êtes responsable des droits.'],
    learn: ['Masthead — Leçons', 'Courtes leçons que vous avez écrites ou fait écrire, lues à voix haute. Usage personnel.'],
    web: ['Masthead — Lectures', 'Pages web envoyées au pupitre, lues à voix haute. Usage personnel. Vous êtes responsable des droits.'],
  },
};

const SENSITIVE_QUERY = new Set([
  'token', 'key', 'apikey', 'api_key', 'auth', 'secret', 'k', 'access_token', 'sig', 'signature', 'password', 'pass',
]);

export function langCode(value) {
  return String(value || 'en').toLowerCase().startsWith('fr') ? 'fr' : 'en';
}

export function escapeXml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

export function publicLink(url) {
  try {
    const parsed = new URL(url);
    const kept = [];
    for (const [key, value] of parsed.searchParams) {
      if (!SENSITIVE_QUERY.has(key.toLowerCase())) kept.push([key, value]);
    }
    parsed.search = '';
    for (const [key, value] of kept) parsed.searchParams.append(key, value);
    parsed.hash = '';
    return parsed.toString();
  } catch {
    return String(url || '').split('?')[0];
  }
}

export async function tokensMatch(presented, expected) {
  if (!presented || !expected) return false;
  const enc = new TextEncoder();
  const digest = async (value) => new Uint8Array(await crypto.subtle.digest('SHA-256', enc.encode(String(value))));
  const a = await digest(presented);
  const b = await digest(expected);
  if (typeof crypto.subtle.timingSafeEqual === 'function') {
    return crypto.subtle.timingSafeEqual(a, b);
  }
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i];
  return diff === 0;
}

function kindOf(episode) {
  const kind = String(episode.kind || 'article').toLowerCase();
  return kind === 'thread' ? 'x' : kind;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function buildRss({ title, description, language, author, link, imageUrl, selfUrl, items, categories }) {
  const channelImage = imageUrl
    ? `<image><url>${escapeXml(imageUrl)}</url><title>${escapeXml(title)}</title><link>${escapeXml(link)}</link></image>
    <itunes:image href="${escapeXml(imageUrl)}" />`
    : '';
  const itemXml = [...items]
    .sort((a, b) => new Date(b.pubDate) - new Date(a.pubDate))
    .map((ep) => {
      const chapters = ep.chaptersUrl
        ? `\n      <podcast:chapters url="${escapeXml(ep.chaptersUrl)}" type="application/json+chapters" />`
        : '';
      const seconds = Math.max(0, Math.floor(Number(ep.durationSeconds) || 0));
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      const s = seconds % 60;
      const duration = h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
      return `<item>
      <title>${escapeXml(ep.title)}</title>
      <description>${escapeXml(ep.description)}</description>
      <pubDate>${new Date(ep.pubDate).toUTCString()}</pubDate>
      <guid isPermaLink="false">${escapeXml(ep.guid || ep.id)}</guid>
      <link>${escapeXml(publicLink(ep.link || ep.audioUrl))}</link>
      <enclosure url="${escapeXml(ep.audioUrl)}" length="${Number(ep.bytes) || 0}" type="audio/mpeg" />
      <itunes:duration>${duration}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>${chapters}
    </item>`;
    }).join('');
  const cats = (categories || []).map((c) => `<itunes:category text="${escapeXml(c)}" />`).join('');
  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:podcast="https://podcastindex.org/namespace/1.0">
  <channel>
    <title>${escapeXml(title)}</title>
    <description>${escapeXml(description)}</description>
    <language>${escapeXml(language || 'en')}</language>
    <link>${escapeXml(link)}</link>
    <atom:link href="${escapeXml(selfUrl)}" rel="self" type="application/rss+xml" />
    <itunes:author>${escapeXml(author || 'Masthead')}</itunes:author>
    <itunes:explicit>false</itunes:explicit>
    ${cats}
    ${channelImage}
    ${itemXml}
  </channel>
</rss>`;
}

function json(body, status = 200, extra) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...(extra || {}) },
  });
}

function cookieToken(request) {
  const raw = request.headers.get('cookie') || '';
  const match = /(?:^|;\s*)mh_k=([^;]+)/.exec(raw);
  return match ? decodeURIComponent(match[1]) : '';
}

async function authorized(request, env, url) {
  const header = request.headers.get('x-inbox-token') || '';
  const presented = header || cookieToken(request) || '';
  return tokensMatch(presented, env.INBOX_TOKEN || '');
}

export function classify(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    if (/(^|\.)(x|twitter|fxtwitter|vxtwitter|fixupx)\.com$/.test(host)) {
      return /\/status(?:es)?\/\d+/.test(parsed.pathname) ? 'x-post' : 'x-profile';
    }
    if (/(youtube\.com|youtu\.be|vimeo\.com|dailymotion\.com|tiktok\.com|twitch\.tv)$/.test(host)) return 'video';
    return 'web';
  } catch {
    return 'invalid';
  }
}

async function readJson(bucket, key, fallback) {
  const obj = await bucket.get(key);
  if (!obj) return fallback;
  return obj.json();
}

function page(title, body, lang) {
  return `<!DOCTYPE html>
<html lang="${lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(title)}</title>
  <link rel="manifest" href="/manifest.webmanifest">
  <style>
    :root { color-scheme: light; }
    body { margin: 0; background: #f3ecdf; color: #1c140f; font: 18px/1.45 Georgia, "Iowan Old Style", serif; }
    main { max-width: 640px; margin: 0 auto; padding: 28px 18px 48px; }
    h1 { font-size: 48px; line-height: 0.9; letter-spacing: -0.04em; margin: 0 0 8px; }
    .rule { border-top: 1px solid #1c140f; border-bottom: 4px solid #1c140f; height: 6px; margin: 12px 0 18px; }
    label { display: block; font: 600 13px/1.3 "Segoe UI", sans-serif; letter-spacing: 0.08em; text-transform: uppercase; }
    input { width: 100%; box-sizing: border-box; border: 1px solid #1c140f; background: #f7f1e6; padding: 10px; font: 16px Georgia, serif; }
    button { margin-top: 14px; background: #1c140f; color: #f7f1e6; border: 0; padding: 10px 16px; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700; }
    .lamp { color: #9d2418; font: 12px/1.4 ui-monospace, monospace; letter-spacing: 0.16em; text-transform: uppercase; }
    a { color: #1e3a5f; }
    .warn { border: 1px solid #d63c2e; padding: 10px 12px; background: #fff6f3; }
  </style>
</head>
<body><main>
  <p class="lamp">● Masthead</p>
  <h1>${escapeHtml(title)}</h1>
  <div class="rule"></div>
  ${body}
</main></body></html>`;
}

function shareForm(lang, prefill) {
  const fr = lang === 'fr';
  const title = fr ? 'Envoyer au pupitre' : 'Send to the desk';
  const body = `
    <p>${fr
      ? 'Collez une adresse que vous avez le droit de lire. Elle attendra dans la boîte du pupitre.'
      : 'Paste an address you have the right to read. It will wait in the desk inbox.'}</p>
    <p class="warn">${fr
      ? 'Usage personnel. Vous êtes responsable des droits.'
      : 'Personal use. You are responsible for the rights.'}</p>
    <form method="post" action="/inbox">
      <label for="url">${fr ? 'Adresse' : 'Address'}</label>
      <input id="url" name="url" type="url" required value="${escapeHtml(prefill || '')}">
      <button type="submit">${fr ? 'Envoyer' : 'Send'}</button>
    </form>
    <p><a href="/feed.xml">Articles</a> · <a href="/x.xml">${fr ? 'Le fil' : 'Wire'}</a> · <a href="/videos.xml">${fr ? 'Écran' : 'Screen'}</a> · <a href="/learn.xml">${fr ? 'Leçons' : 'Lessons'}</a> · <a href="/readings.xml">${fr ? 'Lectures' : 'Readings'}</a></p>`;
  return page(title, body, lang);
}

async function handleInboxPost(request, env, url) {
  if (!env.INBOX_TOKEN) return json({ error: 'INBOX_TOKEN is not set. Run ./setup.sh.' }, 503);
  if (!(await authorized(request, env, url))) return json({ error: 'The inbox refused the token.' }, 401);
  let target = '';
  let title = '';
  const type = request.headers.get('content-type') || '';
  if (type.includes('application/x-www-form-urlencoded') || type.includes('multipart/form-data')) {
    const form = await request.formData();
    target = String(form.get('url') || form.get('text') || '');
    title = String(form.get('title') || '');
  } else {
    const body = await request.json().catch(() => ({}));
    target = String(body.url || body.text || '');
    title = String(body.title || '');
  }
  const found = target.match(/https?:\/\/[^\s]+/);
  if (!found) return json({ error: 'No URL in that share.' }, 400);
  const clean = publicLink(found[0]);
  const label = classify(found[0]);
  const data = await readJson(env.BUCKET, 'inbox.json', { items: [] });
  const items = Array.isArray(data.items) ? data.items : [];
  const prior = items.find((item) => item.url === clean || item.url === found[0]);
  const item = prior || {
    id: 'in-' + crypto.randomUUID().slice(0, 8),
    url: clean,
    title: title.slice(0, 180),
    receivedAt: new Date().toISOString(),
    status: 'queued',
    label,
  };
  if (prior) item.status = prior.status === 'queued' ? 'duplicate' : prior.status;
  else items.unshift(item);
  await env.BUCKET.put('inbox.json', JSON.stringify({ items: items.slice(0, 200) }), {
    httpMetadata: { contentType: 'application/json; charset=utf-8' },
  });
  console.log(JSON.stringify({ message: 'inbox accepted', label, status: item.status }));
  if (type.includes('application/json')) return json({ ok: true, id: item.id, label, status: item.status }, 201);
  const lang = langCode(env.PODCAST_LANGUAGE);
  const html = page(lang === 'fr' ? 'Envoyé' : 'Sent', `<p>${lang === 'fr' ? 'La pièce est dans la boîte du pupitre.' : 'The piece is in the desk inbox.'}</p>`, lang);
  return new Response(html, { status: 201, headers: { 'content-type': 'text/html; charset=utf-8' } });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    try {
      console.log(JSON.stringify({ message: 'request', method: request.method, path: url.pathname }));
      if (!env.BUCKET) return json({ error: 'This worker has no R2 binding. Run ./setup.sh.' }, 503);

      if (request.method === 'GET' && url.pathname === '/manifest.webmanifest') {
        const lang = langCode(env.PODCAST_LANGUAGE);
        return json({
          name: 'Masthead',
          short_name: 'Masthead',
          start_url: '/share',
          display: 'standalone',
          background_color: '#f3ecdf',
          theme_color: '#1c140f',
          share_target: { action: '/share', method: 'GET', params: { title: 'title', text: 'text', url: 'url' } },
          icons: [
            { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
            { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          ],
          description: lang === 'fr' ? 'La une, à voix haute.' : 'The desk that reads aloud.',
        });
      }

      if (request.method === 'GET' && url.pathname === '/logo.svg') {
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" role="img" aria-label="Masthead"><rect width="80" height="80" fill="#1c140f"/><rect x="5" y="5" width="70" height="70" fill="none" stroke="#f4efe4" stroke-width="1.5"/><path fill="#f4efe4" d="M18 58V22h6.2l15.8 22.5L55.8 22H62v36h-5.6V33.2L40.2 54.6 24 33.2V58H18z"/><circle cx="62" cy="16" r="4" fill="#d63c2e"/></svg>`;
        return new Response(svg, { headers: { 'content-type': 'image/svg+xml', 'cache-control': 'public, max-age=86400' } });
      }

      if (request.method === 'GET' && (url.pathname === '/icon-192.png' || url.pathname === '/icon-512.png')) {
        const obj = await env.BUCKET.get(url.pathname === '/icon-192.png' ? 'covers/icon-192.png' : 'covers/icon-512.png');
        if (!obj) return new Response('Missing icon. Run ./setup.sh.', { status: 404 });
        return new Response(obj.body, { headers: { 'content-type': 'image/png', 'cache-control': 'public, max-age=86400' } });
      }

      if (request.method === 'GET' && (url.pathname === '/' || url.pathname === '/share')) {
        const key = url.searchParams.get('k');
        if (key) {
          const next = new URL(url);
          next.searchParams.delete('k');
          return new Response(null, {
            status: 302,
            headers: {
              location: next.pathname + next.search,
              'set-cookie': `mh_k=${encodeURIComponent(key)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=31536000`,
            },
          });
        }
        const lang = langCode(env.PODCAST_LANGUAGE);
        if (url.pathname === '/') {
          const fr = lang === 'fr';
          const home = page('Masthead', `
            <p>${fr ? 'Cinq flux. Une voix. Votre bucket.' : 'Five feeds. One voice. Your bucket.'}</p>
            <ul>
              <li><a href="/feed.xml">Articles</a></li>
              <li><a href="/x.xml">${fr ? 'Le fil' : 'The wire'}</a></li>
              <li><a href="/videos.xml">${fr ? 'Écran' : 'Screen'}</a></li>
              <li><a href="/learn.xml">${fr ? 'Leçons' : 'Lessons'}</a></li>
              <li><a href="/readings.xml">${fr ? 'Lectures' : 'Readings'}</a></li>
            </ul>
            <p><a href="/share">${fr ? 'Envoyer une page depuis le téléphone' : 'Send a page from your phone'}</a></p>`, lang);
          return new Response(home, { headers: { 'content-type': 'text/html; charset=utf-8' } });
        }
        const prefill = url.searchParams.get('url') || url.searchParams.get('text') || '';
        return new Response(shareForm(lang, prefill), { headers: { 'content-type': 'text/html; charset=utf-8' } });
      }

      const feed = FEEDS.find((item) => item.path === url.pathname || item.aliases.includes(url.pathname));
      if (request.method === 'GET' && feed) {
        const lang = langCode(env.PODCAST_LANGUAGE);
        const copy = COPY[lang][feed.kind];
        const library = await readJson(env.BUCKET, 'feed.json', []);
        const episodes = Array.isArray(library) ? library : [];
        const origin = url.origin;
        const items = episodes.filter((ep) => kindOf(ep) === feed.kind).map((ep) => ({
          ...ep,
          link: publicLink(ep.link || ''),
          audioUrl: ep.audioUrl || `${origin}/audio/${encodeURIComponent(ep.id)}.mp3`,
          chaptersUrl: ep.chapters ? `${origin}/chapters/${encodeURIComponent(ep.id)}.json` : '',
        }));
        const xml = buildRss({
          title: copy[0],
          description: copy[1],
          language: lang,
          author: env.PODCAST_AUTHOR || 'Masthead',
          link: origin,
          selfUrl: origin + feed.path,
          imageUrl: `${origin}/covers/${feed.cover}.png`,
          categories: feed.categories,
          items,
        });
        return new Response(xml, { headers: { 'content-type': 'application/rss+xml; charset=utf-8' } });
      }

      const cover = url.pathname.match(/^\/covers\/(articles|x|videos|learn|readings)\.png$/);
      if (request.method === 'GET' && cover) {
        const obj = await env.BUCKET.get(`covers/${cover[1]}.png`);
        if (!obj) return new Response('Cover not uploaded. Run ./setup.sh.', { status: 404 });
        return new Response(obj.body, { headers: { 'content-type': 'image/png', 'cache-control': 'public, max-age=86400' } });
      }

      const audio = url.pathname.match(/^\/audio\/([^/]+)\.mp3$/);
      if (request.method === 'GET' && audio) {
        const id = decodeURIComponent(audio[1]);
        if (!/^[A-Za-z0-9._-]{1,160}$/.test(id)) return json({ error: 'Bad episode id.' }, 400);
        const key = `episodes/${id}.mp3`;
        const range = request.headers.get('range');
        let options;
        if (range) {
          const match = /^bytes=(\d+)-(\d*)$/.exec(range);
          if (match) {
            const offset = Number(match[1]);
            const end = match[2] ? Number(match[2]) : undefined;
            options = { range: end === undefined ? { offset } : { offset, length: end - offset + 1 } };
          }
        }
        const obj = await env.BUCKET.get(key, options);
        if (!obj) return new Response('No audio for that episode.', { status: 404 });
        const headers = { 'content-type': 'audio/mpeg', 'accept-ranges': 'bytes', 'cache-control': 'public, max-age=3600' };
        if (obj.range && obj.size) {
          const start = obj.range.offset || 0;
          const end = start + (obj.range.length || 0) - 1;
          headers['content-range'] = `bytes ${start}-${end}/${obj.size}`;
          return new Response(obj.body, { status: 206, headers });
        }
        return new Response(obj.body, { headers });
      }

      const chapters = url.pathname.match(/^\/chapters\/([^/]+)\.json$/);
      if (request.method === 'GET' && chapters) {
        const id = decodeURIComponent(chapters[1]);
        if (!/^[A-Za-z0-9._-]{1,160}$/.test(id)) return json({ error: 'Bad episode id.' }, 400);
        const obj = await env.BUCKET.get(`chapters/${id}.json`);
        if (!obj) return json({ error: 'No chapters for that episode.' }, 404);
        return new Response(obj.body, { headers: { 'content-type': 'application/json; charset=utf-8' } });
      }

      if (request.method === 'POST' && url.pathname === '/inbox') return handleInboxPost(request, env, url);

      if ((request.method === 'GET' && url.pathname === '/inbox/list') || (request.method === 'POST' && url.pathname === '/inbox/ack')) {
        if (!env.INBOX_TOKEN) return json({ error: 'INBOX_TOKEN is not set. Run ./setup.sh.' }, 503);
        if (!(await authorized(request, env, url))) return json({ error: 'The inbox refused the token.' }, 401);
        const data = await readJson(env.BUCKET, 'inbox.json', { items: [] });
        if (request.method === 'GET') {
          const items = (data.items || []).map((item) => ({
            id: item.id,
            url: publicLink(item.url),
            title: item.title || '',
            receivedAt: item.receivedAt,
            status: item.status,
            label: item.label || classify(item.url || ''),
          }));
          return json({ items });
        }
        const body = await request.json().catch(() => ({}));
        const updates = new Map((body.items || []).map((item) => [item.id, item.status || 'ignored']));
        for (const item of data.items || []) {
          if (updates.has(item.id)) item.status = updates.get(item.id);
        }
        await env.BUCKET.put('inbox.json', JSON.stringify(data), {
          httpMetadata: { contentType: 'application/json; charset=utf-8' },
        });
        return json({ ok: true });
      }

      return json({ error: 'Not found' }, 404);
    } catch (err) {
      console.error(JSON.stringify({ message: 'request failed', error: err instanceof Error ? err.message : String(err) }));
      return json({ error: 'The desk could not complete that.' }, 500);
    }
  },
};
