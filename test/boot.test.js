'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function start(env) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['server.js'], {
      cwd: path.join(__dirname, '..'),
      env: { ...process.env, ...env },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let buf = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error('server did not listen: ' + buf));
    }, 15000);
    child.stdout.on('data', (chunk) => {
      buf += chunk.toString();
      if (buf.includes('masthead listening')) {
        clearTimeout(timer);
        resolve(child);
      }
    });
    child.on('exit', (code) => {
      clearTimeout(timer);
      reject(new Error('server exited ' + code + ' ' + buf));
    });
  });
}

test('demo desk serves the sample shelf without secrets', async () => {
  const data = fs.mkdtempSync(path.join(os.tmpdir(), 'masthead-'));
  const port = 18741;
  const child = await start({
    STUDIO_DEMO: '1',
    PORT: String(port),
    MASTHEAD_DATA: data,
    STUDIO_NO_AUTOMATION: '1',
  });
  try {
    const boot = await fetch(`http://127.0.0.1:${port}/api/bootstrap`).then((res) => res.json());
    const raw = JSON.stringify(boot);
    assert.equal(raw.includes('replace-me'), false);
    assert.equal(raw.includes('session='), false);
    assert.equal(raw.includes('demo-share-token'), false);
    assert.equal(boot.demo, true);
    assert.equal(boot.feed.episodes.length, 6);
    assert.equal(boot.config.tts.voice, 'en-US-AriaNeural');
    assert.equal(boot.config.sources[1].feedQuerySet, true);
    const html = await fetch(`http://127.0.0.1:${port}/`).then((res) => res.text());
    assert.match(html, /Masthead/);
    assert.match(html, /The desk that reads aloud/);
    const xml = await fetch(`http://127.0.0.1:${port}/feed.xml`).then((res) => res.text());
    assert.match(xml, /The night the presses learned to speak/);
    assert.match(xml, /application\/rss\+xml|xmlns:itunes/);
    const chapters = await fetch(`http://127.0.0.1:${port}/chapters/article-night-press.json`).then((res) => res.json());
    assert.ok(chapters.chapters.length >= 2);
    const denied = await fetch(`http://127.0.0.1:${port}/api/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: 'article', args: { url: 'https://example-press.test/city/margin-notes' } }),
    });
    assert.equal(denied.status, 403);
  } finally {
    child.kill();
  }
});
