'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const rss = require('../lib/rss');

test('RSS includes podcast chapters and escapes titles', () => {
  const xml = rss.buildRss({
    title: 'Masthead — Articles',
    description: 'Personal use.',
    language: 'en',
    author: 'Masthead',
    link: 'http://127.0.0.1:8741',
    selfUrl: 'http://127.0.0.1:8741/feed.xml',
    imageUrl: 'http://127.0.0.1:8741/covers/articles.png',
    categories: ['News'],
    items: [{
      title: 'A & B <city>',
      description: 'Sample',
      pubDate: '2026-10-09T06:30:00.000Z',
      guid: 'article-night-press',
      audioUrl: 'http://127.0.0.1:8741/audio/article-night-press.mp3',
      bytes: 1200,
      durationSeconds: 75,
      chaptersUrl: 'http://127.0.0.1:8741/chapters/article-night-press.json',
    }],
  });
  assert.match(xml, /xmlns:podcast=/);
  assert.match(xml, /podcast:chapters/);
  assert.match(xml, /itunes:duration>1:15/);
  assert.match(xml, /A &amp; B &lt;city&gt;/);
  assert.doesNotMatch(xml, /<city>/);
});

test('thread episodes belong on the wire feed', () => {
  assert.equal(rss.matches({ kind: 'thread' }, 'x'), true);
  assert.equal(rss.matches({ kind: 'book' }, 'article'), false);
  assert.equal(rss.feedCopy('web', 'fr')[0], 'Masthead — Lectures');
});
