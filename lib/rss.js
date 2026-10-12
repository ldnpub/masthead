'use strict';

const FEEDS = [
  {
    kind: 'article',
    path: '/feed.xml',
    aliases: ['/', '/rss'],
    cover: 'articles',
    categories: ['News', 'Society & Culture'],
  },
  {
    kind: 'x',
    path: '/x.xml',
    aliases: ['/x'],
    cover: 'x',
    categories: ['News', 'Technology'],
  },
  {
    kind: 'video',
    path: '/videos.xml',
    aliases: ['/videos'],
    cover: 'videos',
    categories: ['TV & Film'],
  },
  {
    kind: 'learn',
    path: '/learn.xml',
    aliases: ['/learn'],
    cover: 'learn',
    categories: ['Education', 'Science'],
  },
  {
    kind: 'web',
    path: '/readings.xml',
    aliases: ['/readings'],
    cover: 'readings',
    categories: ['Society & Culture', 'Arts'],
  },
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

function escapeXml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function rfc2822(dateStr) {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return new Date().toUTCString();
  return d.toUTCString();
}

function itunesDuration(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

function kindOf(episode) {
  const k = String(episode.kind || 'article').toLowerCase();
  return k === 'thread' ? 'x' : k;
}

function matches(episode, kind) {
  return kindOf(episode) === kind;
}

function langCode(lang) {
  return String(lang || 'en').toLowerCase().startsWith('fr') ? 'fr' : 'en';
}

function feedCopy(kind, lang) {
  const code = langCode(lang);
  return COPY[code][kind] || COPY.en[kind];
}

function buildRss({ title, description, language, author, link, imageUrl, selfUrl, items, categories }) {
  const channelImage = imageUrl
    ? `
    <image>
      <url>${escapeXml(imageUrl)}</url>
      <title>${escapeXml(title)}</title>
      <link>${escapeXml(link)}</link>
    </image>
    <itunes:image href="${escapeXml(imageUrl)}" />`
    : '';
  const itemXml = [...items]
    .sort((a, b) => new Date(b.pubDate) - new Date(a.pubDate))
    .map((ep) => {
      const chapters = ep.chaptersUrl
        ? `\n      <podcast:chapters url="${escapeXml(ep.chaptersUrl)}" type="application/json+chapters" />`
        : '';
      return `
    <item>
      <title>${escapeXml(ep.title)}</title>
      <description>${escapeXml(ep.description)}</description>
      <pubDate>${rfc2822(ep.pubDate)}</pubDate>
      <guid isPermaLink="false">${escapeXml(ep.guid || ep.id)}</guid>
      <link>${escapeXml(ep.link || ep.audioUrl)}</link>
      <enclosure url="${escapeXml(ep.audioUrl)}" length="${Number(ep.bytes) || 0}" type="audio/mpeg" />
      <itunes:title>${escapeXml(ep.title)}</itunes:title>
      <itunes:summary>${escapeXml(ep.description)}</itunes:summary>
      <itunes:duration>${itunesDuration(ep.durationSeconds)}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>${chapters}
    </item>`;
    })
    .join('');
  const cats = (categories || []).map((c) => `<itunes:category text="${escapeXml(c)}" />`).join('\n    ');
  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:atom="http://www.w3.org/2005/Atom"
  xmlns:podcast="https://podcastindex.org/namespace/1.0">
  <channel>
    <title>${escapeXml(title)}</title>
    <description>${escapeXml(description)}</description>
    <language>${escapeXml(language || 'en')}</language>
    <link>${escapeXml(link)}</link>
    <atom:link href="${escapeXml(selfUrl)}" rel="self" type="application/rss+xml" />
    <itunes:author>${escapeXml(author || 'Masthead')}</itunes:author>
    <itunes:summary>${escapeXml(description)}</itunes:summary>
    <itunes:explicit>false</itunes:explicit>
    ${cats}
    ${channelImage}
    ${itemXml}
  </channel>
</rss>`;
}

module.exports = {
  FEEDS, COPY, escapeXml, buildRss, matches, kindOf, feedCopy, langCode,
};
