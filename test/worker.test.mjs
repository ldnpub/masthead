import test from 'node:test';
import assert from 'node:assert/strict';
import worker, { tokensMatch, publicLink, buildRss } from '../cloudflare/src/index.js';

class MemoryBucket {
  constructor(files = {}) {
    this.files = new Map(Object.entries(files));
  }
  async get(key) {
    if (!this.files.has(key)) return null;
    const text = this.files.get(key);
    return { json: async () => JSON.parse(text), text: async () => text, body: text };
  }
  async put(key, body) {
    this.files.set(key, typeof body === 'string' ? body : new TextDecoder().decode(body));
  }
}

test('token compare is equal only for the same secret', async () => {
  assert.equal(await tokensMatch('desk-token', 'desk-token'), true);
  assert.equal(await tokensMatch('desk-token', 'other'), false);
  assert.equal(await tokensMatch('', 'desk-token'), false);
});

test('public links drop query secrets', () => {
  assert.equal(
    publicLink('https://members.example-press.test/a?token=super-secret&page=2'),
    'https://members.example-press.test/a?page=2',
  );
});

test('feed XML does not republish a query token', async () => {
  const bucket = new MemoryBucket({
    'feed.json': JSON.stringify([{
      id: 'article-night-press',
      title: 'The night the presses learned to speak',
      description: 'Sample',
      pubDate: '2026-10-09T06:30:00.000Z',
      kind: 'article',
      bytes: 10,
      durationSeconds: 12,
      link: 'https://members.example-press.test/story?token=super-secret',
    }]),
  });
  const res = await worker.fetch(new Request('https://feed.test/feed.xml'), {
    BUCKET: bucket,
    PODCAST_LANGUAGE: 'en',
    PODCAST_AUTHOR: 'Masthead',
    INBOX_TOKEN: 'desk-token',
  });
  const xml = await res.text();
  assert.equal(res.status, 200);
  assert.match(xml, /The night the presses learned to speak/);
  assert.equal(xml.includes('super-secret'), false);
  assert.match(xml, /\/audio\/article-night-press\.mp3/);
});

test('inbox rejects a wrong token and accepts the right one', async () => {
  const bucket = new MemoryBucket();
  const env = { BUCKET: bucket, INBOX_TOKEN: 'desk-token', PODCAST_LANGUAGE: 'en' };
  const denied = await worker.fetch(new Request('https://feed.test/inbox', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-inbox-token': 'nope' },
    body: JSON.stringify({ url: 'https://example-press.test/notes' }),
  }), env);
  assert.equal(denied.status, 401);
  const ok = await worker.fetch(new Request('https://feed.test/inbox', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-inbox-token': 'desk-token' },
    body: JSON.stringify({ url: 'https://example-press.test/notes?token=hide-me' }),
  }), env);
  assert.equal(ok.status, 201);
  const stored = JSON.parse(bucket.files.get('inbox.json'));
  assert.equal(stored.items[0].url.includes('hide-me'), false);
  assert.equal(stored.items[0].label, 'web');
});

test('a worker without a bucket does not pretend to have one', async () => {
  const res = await worker.fetch(new Request('https://feed.test/feed.xml'), {});
  assert.equal(res.status, 503);
  const body = await res.json();
  assert.match(body.error, /setup\.sh/);
});

test('buildRss escapes titles', () => {
  const xml = buildRss({
    title: 'Masthead',
    description: 'd',
    language: 'en',
    author: 'Masthead',
    link: 'https://feed.test',
    selfUrl: 'https://feed.test/feed.xml',
    imageUrl: '',
    categories: [],
    items: [{ id: 'a', title: 'A & B', description: '', pubDate: '2026-10-01T00:00:00.000Z', audioUrl: 'https://feed.test/audio/a.mp3', bytes: 1, durationSeconds: 1 }],
  });
  assert.match(xml, /A &amp; B/);
});
