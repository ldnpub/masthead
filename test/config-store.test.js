'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const store = require('../lib/config-store');

test('redact hides source cookies, feed query tokens, and API keys', () => {
  const cfg = {
    cloudflare: { accountId: 'abc', bucket: 'library', token: 'cf-secret' },
    llm: { provider: 'openai', apiKey: 'sk-test-value' },
    inbox: { token: 'inbox-secret' },
    sources: [{
      id: 'members',
      label: 'Members',
      feedUrl: 'https://members.example-press.test/feed.xml?token=replace-me&page=1',
      extractor: 'example-member-press',
      auth: { scheme: 'cookie', cookie: 'session=replace-me' },
    }],
  };
  const redacted = store.redactConfig(cfg);
  const raw = JSON.stringify(redacted);
  assert.equal(raw.includes('replace-me'), false);
  assert.equal(raw.includes('cf-secret'), false);
  assert.equal(raw.includes('sk-test-value'), false);
  assert.equal(raw.includes('inbox-secret'), false);
  assert.equal(raw.includes('session='), false);
  assert.equal(redacted.cloudflare.accountId, 'abc');
  assert.equal(redacted.cloudflare.bucket, 'library');
  assert.equal(redacted.cloudflare.tokenSet, true);
  assert.equal(redacted.inbox.tokenSet, true);
  assert.equal(redacted.sources[0].feedQuerySet, true);
  assert.equal(redacted.sources[0].feedUrl, 'https://members.example-press.test/feed.xml');
  assert.equal(redacted.sources[0].auth.cookieSet, true);
});

test('saving the stripped feed URL keeps the stored query and cookie', () => {
  const existing = [{
    id: 'members',
    label: 'Members',
    feedUrl: 'https://members.example-press.test/feed.xml?token=keep-me',
    extractor: 'auto',
    auth: { scheme: 'cookie', cookie: 'session=keep' },
  }];
  const merged = store.mergeSources(existing, [{
    id: 'members',
    label: 'Members',
    feedUrl: 'https://members.example-press.test/feed.xml',
    extractor: 'example-member-press',
    auth: { scheme: 'cookie', cookieSet: true },
  }]);
  assert.equal(merged[0].feedUrl, 'https://members.example-press.test/feed.xml?token=keep-me');
  assert.equal(merged[0].auth.cookie, 'session=keep');
  assert.equal(merged[0].extractor, 'example-member-press');
});

test('empty secret fields do not wipe stored tokens', () => {
  const cfg = {
    cloudflare: { accountId: 'abc', bucket: 'library', token: 'cf-secret' },
    llm: { apiKey: 'kept' },
    inbox: { token: 'kept-inbox' },
    sources: [],
  };
  const next = store.mergeConfig(cfg, {
    cloudflare: { accountId: 'abc', bucket: 'renamed', token: '' },
    llm: { provider: 'ollama', apiKey: '' },
    inbox: { token: '' },
  });
  assert.equal(next.cloudflare.token, 'cf-secret');
  assert.equal(next.cloudflare.bucket, 'renamed');
  assert.equal(next.llm.apiKey, 'kept');
  assert.equal(next.inbox.token, 'kept-inbox');
  assert.equal(next.llm.provider, 'ollama');
});

test('__clear__ deletes a source secret', () => {
  const merged = store.mergeAuth({ scheme: 'bearer', token: 'abc' }, { scheme: 'bearer', token: '__clear__' });
  assert.equal(merged.token, undefined);
  assert.equal(merged.scheme, 'bearer');
});
