(function () {
  const VIEWS = ['desk', 'sources', 'wire', 'screen', 'lessons', 'editions', 'compose'];
  const state = {
    lang: 'en',
    view: 'desk',
    boot: null,
    timeline: null,
    notice: '',
    error: '',
    editionFilter: 'all',
    tokenVisible: false,
    share: null,
  };

  const stage = document.getElementById('stage');
  const rail = document.getElementById('rail');

  function t(path) {
    const pack = window.MH[state.lang] || window.MH.en;
    const value = path.split('.').reduce((node, key) => (node ? node[key] : undefined), pack);
    return value === undefined ? path : value;
  }

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[ch]));
  }

  function applyStatic() {
    document.documentElement.lang = state.lang;
    document.querySelectorAll('[data-i18n]').forEach((node) => {
      const key = node.getAttribute('data-i18n');
      const value = t(key);
      if (typeof value === 'string') node.textContent = value;
    });
    document.title = 'Masthead';
    rail.innerHTML = VIEWS.map((view) => {
      const current = view === state.view ? ' aria-current="page"' : '';
      return `<a href="#${view}"${current}>${esc(t('nav.' + view))}</a>`;
    }).join('');
    document.querySelectorAll('.lang-btn').forEach((btn) => {
      btn.setAttribute('aria-pressed', btn.dataset.lang === state.lang ? 'true' : 'false');
    });
    const dateline = document.getElementById('dateline');
    const when = new Date();
    const formatted = new Intl.DateTimeFormat(state.lang === 'fr' ? 'fr-FR' : 'en-GB', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
    }).format(when);
    dateline.textContent = (state.lang === 'fr' ? 'Vol. I · Exemplaire de pupitre · ' : 'Vol. I · Desk copy · ') + formatted;
  }

  async function boot() {
    const res = await fetch('/api/bootstrap');
    if (!res.ok) throw new Error('bootstrap');
    state.boot = await res.json();
    state.boot.health = null;
    state.lang = (state.boot.config.ui && state.boot.config.ui.lang) || 'en';
    const hash = location.hash.replace('#', '');
    state.view = VIEWS.includes(hash) ? hash : 'desk';
    applyStatic();
    render();
    loadHealth();
    if (state.view === 'wire') loadWire();
    if (state.view === 'compose') loadShare();
  }

  function loadHealth() {
    fetch('/api/health').then((res) => res.json()).then((health) => {
      if (!health || health.error) return;
      state.boot.health = health;
      if (state.view === 'desk') render();
    }).catch(() => {});
  }

  function episodes() {
    return (state.boot && state.boot.feed && state.boot.feed.episodes) || [];
  }

  function cfg() {
    return (state.boot && state.boot.config) || { ui: {}, tts: {}, publish: {}, sources: [] };
  }

  function when(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '';
    return new Intl.DateTimeFormat(state.lang === 'fr' ? 'fr-FR' : 'en-GB', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(date);
  }

  function duration(seconds) {
    const s = Math.max(0, Math.floor(Number(seconds) || 0));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${String(r).padStart(2, '0')}`;
  }

  function noticeHtml() {
    if (state.error) return `<p class="notice error">${esc(state.error)}</p>`;
    if (state.notice) return `<p class="notice">${esc(state.notice)}</p>`;
    return '';
  }

  function render() {
    applyStatic();
    const view = state.view;
    const html = {
      desk: renderDesk,
      sources: renderSources,
      wire: renderWire,
      screen: renderScreen,
      lessons: renderLessons,
      editions: renderEditions,
      compose: renderCompose,
    }[view]();
    stage.innerHTML = noticeHtml() + html;
    stage.focus({ preventScroll: true });
  }

  function renderDesk() {
    const d = t('desk');
    const list = episodes();
    const demo = state.boot.demo;
    const sources = cfg().sources || [];
    const wizard = !cfg().ui.wizardDismissed && sources.length === 0;
    const title = list.length === 0 ? d.emptyTitle : demo ? d.demoTitle : d.liveTitle;
    const body = list.length === 0 ? d.emptyBody : demo ? d.demoBody : d.liveBody;
    const storage = state.boot.feed.storage === 'r2' ? d.storageR2 : d.storageLocal;
    const health = state.boot.health
      ? Object.entries(state.boot.health).map(([key, item]) => `
      <li>
        <i class="mark ${item.ok ? '' : 'bad'}"></i>
        <div><strong>${esc(t('health.' + key))}</strong><span>${esc(item.detail || '')}</span></div>
      </li>`).join('')
      : `<li><i class="mark"></i><div><strong>${esc(d.health)}</strong><span>${esc(t('loading'))}</span></div></li>`;
    const recent = list.slice().sort((a, b) => new Date(b.pubDate) - new Date(a.pubDate)).slice(0, 5);
    const jobs = (state.boot.jobs || []).slice(0, 5);
    const inbox = (state.boot.inbox && state.boot.inbox.items) || [];
    return `
      ${wizard ? renderWizard() : ''}
      <div class="desk-grid">
        <article class="card">
          ${demo ? `<span class="flag">${esc(d.demoFlag)}</span>` : ''}
          <p class="kicker">${esc(d.kicker)}</p>
          <h2>${esc(title)}</h2>
          <p class="lede">${esc(body)}</p>
          <p class="meta">${esc(typeof d.count === 'function' ? d.count(list.length) : '')} · ${esc(storage)}</p>
        </article>
        <aside class="card health">
          <h2>${esc(d.health)}</h2>
          <ul class="bench">${health}</ul>
        </aside>
      </div>
      <div class="section-head"><h2>${esc(d.recent)}</h2></div>
      ${recent.length ? recent.map(editionRow).join('') : `<p>${esc(d.none)}</p>`}
      <div class="section-head"><h2>${esc(d.jobs)}</h2></div>
      ${jobs.length ? `<ul class="jobs">${jobs.map(jobRow).join('')}</ul>` : `<p>${esc(d.noJobs)}</p>`}
      <div class="section-head"><h2>${esc(d.inbox)}</h2></div>
      ${inbox.length ? `<ul class="inbox-list">${inbox.map(inboxRow).join('')}</ul>` : `<p>${esc(d.noInbox)}</p>`}
    `;
  }

  function renderWizard() {
    const w = t('wizard');
    return `<section class="card wizard">
      <p class="kicker">${esc(w.kicker)}</p>
      <h2>${esc(w.title)}</h2>
      <p>${esc(w.body)}</p>
      <ol><li>${esc(w.step1)}</li><li>${esc(w.step2)}</li><li>${esc(w.step3)}</li></ol>
      <p class="warn">${esc(w.rights)}</p>
      <div class="row-actions">
        <a class="btn" href="#sources">${esc(w.sources)}</a>
        <button class="btn secondary" type="button" data-action="dismiss-wizard">${esc(w.dismiss)}</button>
      </div>
    </section>`;
  }

  function editionRow(ep) {
    const kind = t('kinds.' + (ep.kind || 'article'));
    return `<article class="edition">
      <time datetime="${esc(ep.pubDate)}">${esc(when(ep.pubDate))}</time>
      <div>
        <h3>${esc(ep.title)}</h3>
        <p>${esc(ep.description || '')}</p>
      </div>
      <div>
        <div class="kind">${esc(kind)} · ${esc(duration(ep.durationSeconds))}${ep.chapters ? ' · ' + esc(t('editions.chapters')) : ''}</div>
      </div>
    </article>`;
  }

  function jobRow(job) {
    const label = t('status.' + job.status) || job.status;
    return `<li><span class="pill ${esc(job.status)}">${esc(label)}</span><span>${esc(job.summary || job.command)}</span><span class="when">${esc(when(job.finishedAt || job.createdAt))}</span></li>`;
  }

  function inboxRow(item) {
    const label = t('labels.' + (item.label || 'web')) || item.label;
    return `<li>
      <span class="pill ${esc(item.status)}">${esc(t('status.' + item.status) || item.status)}</span>
      <span><strong>${esc(label)}</strong> — ${esc(item.title || item.url)}</span>
      <span class="row-actions">
        ${item.status === 'queued' ? `<button class="btn" type="button" data-action="read-inbox" data-url="${esc(item.url)}" data-id="${esc(item.id)}">${esc(t('desk.read'))}</button>` : ''}
        <button class="btn secondary" type="button" data-action="ignore-inbox" data-id="${esc(item.id)}">${esc(t('desk.ignore'))}</button>
      </span>
    </li>`;
  }

  function authFields(prefix) {
    const s = t('sources');
    return `
      <label for="${prefix}-auth">${esc(s.auth)}</label>
      <select id="${prefix}-auth" name="scheme">
        <option value="none">${esc(s.none)}</option>
        <option value="bearer">${esc(s.bearer)}</option>
        <option value="basic">${esc(s.basic)}</option>
        <option value="cookie">${esc(s.cookie)}</option>
        <option value="header">${esc(s.header)}</option>
      </select>
      <div data-auth="bearer" hidden>
        <label>${esc(s.token)}</label>
        <input name="token" type="password" autocomplete="off">
      </div>
      <div data-auth="basic" hidden>
        <label>${esc(s.username)}</label>
        <input name="username" autocomplete="off">
        <label>${esc(s.password)}</label>
        <input name="password" type="password" autocomplete="off">
      </div>
      <div data-auth="cookie" hidden>
        <label>${esc(s.cookieValue)}</label>
        <input name="cookie" type="password" autocomplete="off" placeholder="session=…">
      </div>
      <div data-auth="header" hidden>
        <label>${esc(s.headerName)}</label>
        <input name="name" autocomplete="off">
        <label>${esc(s.headerValue)}</label>
        <input name="value" type="password" autocomplete="off">
      </div>
      <p class="hint">${esc(s.secretKept)}</p>`;
  }

  function renderSources() {
    const s = t('sources');
    const extractors = ((state.boot.extractors && state.boot.extractors.extractors) || [])
      .map((ext) => `<option value="${esc(ext.id)}">${esc(ext.id)}</option>`).join('');
    const blocks = (state.boot.sources && state.boot.sources.sources) || [];
    const cards = blocks.map((source) => {
      const items = (source.items || []).map((item) => `
        <div class="item">
          <div>
            <h4>${esc(item.title)}</h4>
            <p class="hint">${esc(item.author || '')} · ${item.published ? esc(s.published) : esc(s.fresh)} · ${item.hasFullText ? esc(s.full) : esc(s.tease)}</p>
          </div>
          <button class="btn" type="button" data-action="read-url" data-url="${esc(item.url)}" data-source="${esc(source.id)}" ${item.published ? 'disabled' : ''}>${esc(t('desk.read'))}</button>
        </div>`).join('');
      return `<section class="source">
        <h3>${esc(source.label || source.id)}</h3>
        <p class="meta">${esc(source.id)}${source.error ? ' · ' + esc(source.error) : ''}</p>
        ${items || `<p>${esc(s.empty)}</p>`}
        <button class="btn secondary" type="button" data-action="remove-source" data-id="${esc(source.id)}">${esc(s.remove)}</button>
      </section>`;
    }).join('');
    const known = (cfg().sources || []).map((source) => `
      <p class="hint"><strong>${esc(source.label)}</strong> — ${esc(source.feedUrl)}
        ${source.feedQuerySet ? ' · ' + esc(s.hiddenQuery) : ''}
        ${source.auth && (source.auth.tokenSet || source.auth.cookieSet || source.auth.passwordSet || source.auth.valueSet) ? ' · ' + esc(s.secretKept) : ''}
      </p>`).join('');
    return `
      <p class="kicker">${esc(s.kicker)}</p>
      <h2>${esc(t('nav.sources'))}</h2>
      <p class="lede">${esc(s.intro)} <a href="/guide">${esc(s.guide)}</a></p>
      ${known}
      <div class="split">
        <form class="card" id="source-form">
          <h3>${esc(s.add)}</h3>
          <label>${esc(s.label)}</label>
          <input name="label" required maxlength="120" placeholder="City Desk">
          <label>${esc(s.url)}</label>
          <input name="feedUrl" required type="url" placeholder="https://example.test/feed.xml">
          <label>${esc(s.extractor)}</label>
          <select name="extractor">
            <option value="auto">${esc(s.auto)}</option>
            ${extractors}
          </select>
          ${authFields('new')}
          <p><button class="btn" type="submit">${esc(s.save)}</button></p>
        </form>
        <div>${cards || `<p>${esc(s.empty)}</p>`}</div>
      </div>`;
  }

  function renderWire() {
    const w = t('wire');
    const handles = (cfg().xFollow && cfg().xFollow.handles) || [];
    const posts = (state.timeline && state.timeline.posts) || [];
    const list = posts.map((post) => `
      <article class="item">
        <div>
          <h4>${esc(post.text)}</h4>
          <p class="hint">${esc(String(post.chars || post.text.length))} ${esc(w.chars)}</p>
        </div>
        <button class="btn" type="button" data-action="read-x" data-url="${esc(post.url)}" ${post.published ? 'disabled' : ''}>${esc(w.publish)}</button>
      </article>`).join('');
    return `
      <p class="kicker">${esc(w.kicker)}</p>
      <h2>${esc(t('nav.wire'))}</h2>
      <p class="lede">${esc(w.intro)}</p>
      <form class="card" id="wire-form">
        <label>${esc(w.handle)}</label>
        <input name="handle" required maxlength="15" value="${esc(handles[0] || '')}" placeholder="citydesk">
        <p class="row-actions">
          <button class="btn" type="submit">${esc(w.follow)}</button>
          <button class="btn secondary" type="button" data-action="refresh-wire">${esc(w.refresh)}</button>
        </p>
      </form>
      <div class="section-head"><h2>${esc(handles[0] ? '@' + handles[0] : w.kicker)}</h2></div>
      ${list || `<p>${esc(w.empty)}</p>`}
    `;
  }

  function renderScreen() {
    const s = t('screen');
    const videos = episodes().filter((ep) => ep.kind === 'video');
    return `
      <p class="kicker">${esc(s.kicker)}</p>
      <h2>${esc(t('nav.screen'))}</h2>
      <p class="lede">${esc(s.intro)}</p>
      <form class="card" id="screen-form">
        <label>${esc(s.url)}</label>
        <input name="url" type="url" required placeholder="https://example.test/watch/booth">
        <p><button class="btn" type="submit">${esc(s.go)}</button></p>
      </form>
      <div class="section-head"><h2>${esc(t('nav.editions'))}</h2></div>
      ${videos.length ? videos.map(editionRow).join('') : `<p>${esc(s.empty)}</p>`}
    `;
  }

  function renderLessons() {
    const l = t('lessons');
    const lessons = episodes().filter((ep) => ep.kind === 'learn');
    return `
      <p class="kicker">${esc(l.kicker)}</p>
      <h2>${esc(t('nav.lessons'))}</h2>
      <p class="lede">${esc(l.intro)}</p>
      <form class="card" id="lesson-draft">
        <div class="compose-grid">
          <div><label>${esc(l.subject)}</label><input name="sujet" required placeholder="Cylinder press"></div>
          <div><label>${esc(l.angle)}</label><input name="angle" placeholder="${state.lang === 'fr' ? 'le mécanisme' : 'the mechanism'}"></div>
          <div><label>${esc(l.number)}</label><input name="numero" type="number" min="1" value="1"></div>
        </div>
        <p><button class="btn secondary" type="submit">${esc(l.draft)}</button></p>
      </form>
      <form id="lesson-speak">
        <label>${esc(l.title)}</label>
        <input name="title" required value="${state.lang === 'fr' ? 'Comment une presse à cylindre marche' : 'How a cylinder press actually works'}">
        <label>${esc(l.script)}</label>
        <textarea name="text" required placeholder="${esc(l.hint)}"></textarea>
        <p class="hint">${esc(l.hint)}</p>
        <p><button class="btn" type="submit">${esc(l.speak)}</button></p>
      </form>
      ${lessons.map(editionRow).join('')}
    `;
  }

  function renderEditions() {
    const e = t('editions');
    const filters = ['all', 'article', 'x', 'video', 'learn', 'web'];
    const buttons = filters.map((kind) => {
      const label = kind === 'all' ? e.all : t('kinds.' + kind);
      return `<button class="btn secondary" type="button" data-action="filter" data-kind="${kind}" aria-pressed="${state.editionFilter === kind}">${esc(label)}</button>`;
    }).join('');
    const list = episodes().filter((ep) => state.editionFilter === 'all' || (ep.kind === 'thread' ? 'x' : (ep.kind || 'article')) === state.editionFilter);
    const base = (state.boot.feed && state.boot.feed.baseUrl) || '';
    const paths = { article: '/feed.xml', x: '/x.xml', video: '/videos.xml', learn: '/learn.xml', web: '/readings.xml' };
    const feedUrl = state.editionFilter === 'all' ? base + '/feed.xml' : base + (paths[state.editionFilter] || '/feed.xml');
    return `
      <p class="kicker">${esc(e.kicker)}</p>
      <h2>${esc(t('nav.editions'))}</h2>
      <p class="lede">${esc(e.intro)}</p>
      <p class="feed-url" id="feed-url">${esc(feedUrl)}</p>
      <p><button class="btn secondary" type="button" data-action="copy-feed" data-url="${esc(feedUrl)}">${esc(e.copy)}</button></p>
      <div class="filters">${buttons}</div>
      ${list.length ? list.map((ep) => editionRow(ep) + `<p><button class="btn secondary" type="button" data-action="delete-ep" data-id="${esc(ep.id)}">${esc(e.remove)}</button></p>`).join('') : `<p>${esc(e.empty)}</p>`}
    `;
  }

  function renderCompose() {
    const c = t('compose');
    const ui = cfg().ui || {};
    const tts = cfg().tts || {};
    const pub = cfg().publish || {};
    const cloud = cfg().cloudflare || {};
    const llm = cfg().llm || {};
    const server = cfg().server || {};
    const sched = cfg().scheduler || {};
    const voices = (state.boot.voices || []).map((voice) => `<option value="${esc(voice)}">`).join('');
    const token = state.share && state.tokenVisible ? state.share.token : (cfg().inbox && cfg().inbox.tokenSet ? '••••••••••••••••' : '');
    return `
      <p class="kicker">${esc(c.kicker)}</p>
      <h2>${esc(t('nav.compose'))}</h2>
      <p class="lede">${esc(c.intro)}</p>
      <p class="warn">${esc(c.rights)}</p>
      <p class="warn">${esc(c.unofficial)}</p>
      <form id="compose-form" class="compose-grid">
        <div>
          <label>${esc(c.lang)}</label>
          <select name="lang">
            <option value="en" ${ui.lang !== 'fr' ? 'selected' : ''}>English</option>
            <option value="fr" ${ui.lang === 'fr' ? 'selected' : ''}>Français</option>
          </select>
        </div>
        <div>
          <label>${esc(c.voice)}</label>
          <input name="voice" list="voices" value="${esc(tts.voice || 'en-US-AriaNeural')}">
          <datalist id="voices">${voices}</datalist>
          <p class="hint">${esc(c.voiceHint)}</p>
        </div>
        <div>
          <label>${esc(c.engine)}</label>
          <select name="engine">
            <option value="edge" ${tts.engine !== 'piper' ? 'selected' : ''}>${esc(c.edge)}</option>
            <option value="piper" ${tts.engine === 'piper' ? 'selected' : ''}>${esc(c.piper)}</option>
          </select>
        </div>
        <div>
          <label>${esc(c.rate)}</label>
          <input name="rate" type="number" min="-50" max="50" value="${esc(tts.rate || 0)}">
        </div>
        <div class="span-2">
          <label>${esc(c.piperModel)}</label>
          <input name="piperModel" value="${esc(tts.piperModel || '')}" placeholder="voices/en_US-lessac-medium.onnx">
        </div>
        <div>
          <label>${esc(c.author)}</label>
          <input name="author" value="${esc(pub.author || 'Masthead')}">
        </div>
        <div>
          <label>${esc(c.title)}</label>
          <input name="title" value="${esc(pub.title || 'Masthead')}">
        </div>
        <div class="span-2">
          <label>${esc(c.base)}</label>
          <input name="publicBaseUrl" value="${esc(pub.publicBaseUrl || '')}" placeholder="https://your-name.workers.dev">
          <p class="hint">${esc(c.baseHint)}</p>
        </div>
        <div>
          <label>${esc(c.zone)}</label>
          <input name="timezone" value="${esc(ui.timezone || '')}" placeholder="UTC">
          <p class="hint">${esc(c.zoneHint)}</p>
        </div>
        <div>
          <label>${esc(c.account)}</label>
          <input name="accountId" value="${esc(cloud.accountId || '')}" autocomplete="off" spellcheck="false">
        </div>
        <div>
          <label>${esc(c.bucket)}</label>
          <input name="bucket" value="${esc(cloud.bucket || '')}" autocomplete="off">
        </div>
        <div>
          <label>${esc(c.cfToken)}</label>
          <input name="cfToken" type="password" autocomplete="off" placeholder="${cloud.tokenSet ? '•••• saved' : ''}">
        </div>
        <div>
          <label>${esc(c.llm)}</label>
          <select name="provider">
            <option value="none" ${llm.provider === 'none' || !llm.provider ? 'selected' : ''}>${esc(c.llmNone)}</option>
            <option value="ollama" ${llm.provider === 'ollama' ? 'selected' : ''}>${esc(c.llmOllama)}</option>
            <option value="openai" ${llm.provider === 'openai' ? 'selected' : ''}>${esc(c.llmOpenAI)}</option>
          </select>
        </div>
        <div>
          <label>${esc(c.model)}</label>
          <input name="model" value="${esc(llm.model || '')}">
        </div>
        <div class="span-2">
          <label>${esc(c.baseUrl)}</label>
          <input name="baseUrl" value="${esc(llm.baseUrl || '')}" placeholder="http://127.0.0.1:11434">
        </div>
        <div class="span-2">
          <label>${esc(c.apiKey)}</label>
          <input name="apiKey" type="password" autocomplete="off" placeholder="${llm.apiKeySet ? '•••• saved' : ''}">
        </div>
        <div class="span-2">
          <label>${esc(c.inbox)}</label>
          <div class="token" id="inbox-token">${esc(token)}</div>
          <p class="hint">${esc(c.inboxHint)}</p>
          <button class="btn secondary" type="button" data-action="toggle-token">${esc(state.tokenVisible ? c.hide : c.show)}</button>
        </div>
        <div class="span-2">
          <label class="check"><input type="checkbox" name="listenAll" ${server.listenAll ? 'checked' : ''}> ${esc(c.listenAll)}</label>
          <p class="hint">${esc(c.listenWarn)}</p>
        </div>
        <div class="span-2"><h3>${esc(c.scheduler)}</h3></div>
        <div><label class="check"><input type="checkbox" name="schedEnabled" ${sched.enabled ? 'checked' : ''}> ${esc(c.enabled)}</label></div>
        <div><label>${esc(c.hour)}</label><input name="hour" type="number" min="0" max="23" value="${esc(sched.hour ?? 7)}"></div>
        <div><label>${esc(c.minute)}</label><input name="minute" type="number" min="0" max="59" value="${esc(sched.minute ?? 0)}"></div>
        <div><label>${esc(c.count)}</label><input name="count" type="number" min="1" max="10" value="${esc(sched.count ?? 2)}"></div>
        <div class="span-2"><button class="btn" type="submit">${esc(c.save)}</button></div>
      </form>`;
  }

  function slug(value) {
    return String(value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40);
  }

  async function saveConfig(patch) {
    const res = await fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'save');
    state.boot.config = data;
    state.lang = (data.ui && data.ui.lang) || state.lang;
    state.notice = t('compose.saved');
    state.error = '';
  }

  async function queue(command, args) {
    const res = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, args }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'job');
    state.boot.jobs = [data].concat(state.boot.jobs || []);
    state.notice = data.summary || data.status;
    state.error = '';
  }

  function formAuth(form) {
    const scheme = form.scheme.value;
    const auth = { scheme };
    if (scheme === 'bearer' && form.token.value) auth.token = form.token.value;
    if (scheme === 'basic') {
      if (form.username.value) auth.username = form.username.value;
      if (form.password.value) auth.password = form.password.value;
    }
    if (scheme === 'cookie' && form.cookie.value) auth.cookie = form.cookie.value;
    if (scheme === 'header') {
      if (form.name.value) auth.name = form.name.value;
      if (form.value.value) auth.value = form.value.value;
    }
    return auth;
  }

  function showAuth(select) {
    const form = select.form;
    form.querySelectorAll('[data-auth]').forEach((node) => {
      node.hidden = node.getAttribute('data-auth') !== select.value;
    });
  }

  async function loadWire() {
    const handle = ((cfg().xFollow || {}).handles || [])[0] || 'citydesk';
    try {
      const res = await fetch('/api/x/timeline?handle=' + encodeURIComponent(handle));
      state.timeline = await res.json();
      if (state.view === 'wire') render();
    } catch {
      state.error = t('errors.load');
      if (state.view === 'wire') render();
    }
  }

  async function loadShare() {
    try {
      const res = await fetch('/api/share');
      if (res.ok) state.share = await res.json();
    } catch { /* loopback only */ }
    if (state.view === 'compose') render();
  }

  document.addEventListener('click', async (event) => {
    const langBtn = event.target.closest('.lang-btn');
    if (langBtn) {
      state.lang = langBtn.dataset.lang;
      try {
        await saveConfig({ ui: { lang: state.lang } });
      } catch { /* keep the local switch */ }
      state.notice = '';
      render();
      return;
    }
    const action = event.target.closest('[data-action]');
    if (!action) return;
    const name = action.dataset.action;
    try {
      if (name === 'dismiss-wizard') {
        await saveConfig({ ui: { wizardDismissed: true } });
        render();
      } else if (name === 'read-url') {
        await queue('article', { url: action.dataset.url, sourceId: action.dataset.source });
        render();
      } else if (name === 'read-x') {
        await queue('x', { urls: [action.dataset.url] });
        render();
      } else if (name === 'read-inbox') {
        const label = (state.boot.inbox.items.find((item) => item.id === action.dataset.id) || {}).label;
        const command = label === 'video' ? 'video' : label === 'x-post' ? 'x' : 'web';
        const args = command === 'x' ? { urls: [action.dataset.url] } : { url: action.dataset.url };
        await queue(command, args);
        await fetch('/api/inbox/ack', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: [{ id: action.dataset.id, status: 'queued' }] }),
        });
        render();
      } else if (name === 'ignore-inbox') {
        await fetch('/api/inbox/ack', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: [{ id: action.dataset.id, status: 'ignored' }] }),
        });
        const item = (state.boot.inbox.items || []).find((row) => row.id === action.dataset.id);
        if (item) item.status = 'ignored';
        render();
      } else if (name === 'remove-source') {
        const sources = (cfg().sources || []).filter((source) => source.id !== action.dataset.id);
        await saveConfig({ sources });
        state.boot = await (await fetch('/api/bootstrap')).json();
        render();
      } else if (name === 'refresh-wire') {
        await loadWire();
      } else if (name === 'filter') {
        state.editionFilter = action.dataset.kind;
        render();
      } else if (name === 'copy-feed') {
        await navigator.clipboard.writeText(action.dataset.url);
        state.notice = t('editions.copied');
        render();
      } else if (name === 'delete-ep') {
        await queue('delete', { id: action.dataset.id });
        render();
      } else if (name === 'toggle-token') {
        state.tokenVisible = !state.tokenVisible;
        if (state.tokenVisible && !state.share) await loadShare();
        render();
      }
    } catch (err) {
      state.error = err.message || t('errors.job');
      render();
    }
  });

  document.addEventListener('change', (event) => {
    if (event.target.name === 'scheme') showAuth(event.target);
  });

  document.addEventListener('submit', async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    event.preventDefault();
    try {
      if (form.id === 'source-form') {
        const id = slug(form.label.value) || 'source';
        const source = {
          id,
          label: form.label.value,
          feedUrl: form.feedUrl.value,
          extractor: form.extractor.value,
          auth: formAuth(form),
        };
        const sources = (cfg().sources || []).filter((item) => item.id !== id).concat([source]);
        await saveConfig({ sources, ui: { wizardDismissed: true } });
        state.boot = await (await fetch('/api/bootstrap')).json();
        state.lang = state.boot.config.ui.lang || state.lang;
        render();
      } else if (form.id === 'wire-form') {
        const handle = form.handle.value.replace(/^@/, '').trim();
        const prev = cfg().xFollow || {};
        await saveConfig({ xFollow: Object.assign({}, prev, { handles: [handle] }) });
        await loadWire();
      } else if (form.id === 'screen-form') {
        await queue('video', { url: form.url.value });
        render();
      } else if (form.id === 'lesson-draft') {
        await queue('learn-generate', {
          sujet: form.sujet.value,
          angle: form.angle.value,
          numero: Number(form.numero.value || 1),
        });
        render();
      } else if (form.id === 'lesson-speak') {
        await queue('learn', { title: form.title.value, text: form.text.value });
        render();
      } else if (form.id === 'compose-form') {
        const data = new FormData(form);
        await saveConfig({
          ui: { lang: data.get('lang'), timezone: data.get('timezone') },
          tts: {
            engine: data.get('engine'),
            voice: data.get('voice'),
            rate: Number(data.get('rate') || 0),
            piperModel: data.get('piperModel'),
          },
          publish: {
            author: data.get('author'),
            title: data.get('title'),
            publicBaseUrl: data.get('publicBaseUrl'),
          },
          cloudflare: {
            accountId: data.get('accountId'),
            bucket: data.get('bucket'),
            token: data.get('cfToken') || '',
          },
          llm: {
            provider: data.get('provider'),
            model: data.get('model'),
            baseUrl: data.get('baseUrl'),
            apiKey: data.get('apiKey') || '',
          },
          server: { listenAll: form.listenAll.checked },
          scheduler: {
            enabled: form.schedEnabled.checked,
            hour: Number(data.get('hour') || 0),
            minute: Number(data.get('minute') || 0),
            count: Number(data.get('count') || 1),
          },
        });
        state.lang = data.get('lang');
        render();
      }
    } catch (err) {
      state.error = err.message || t('errors.save');
      render();
    }
  });

  window.addEventListener('hashchange', () => {
    const hash = location.hash.replace('#', '');
    state.view = VIEWS.includes(hash) ? hash : 'desk';
    state.error = '';
    state.notice = '';
    render();
    if (state.view === 'wire') loadWire();
    if (state.view === 'compose') loadShare();
  });

  boot().catch(() => {
    stage.innerHTML = `<p class="notice error">${esc(t('errors.load'))}</p>`;
  });
})();
