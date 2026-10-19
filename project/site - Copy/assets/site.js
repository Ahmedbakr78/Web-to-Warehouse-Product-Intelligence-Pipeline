
(function () {
  'use strict';

  // ---------------------------------------------------------------- theme
  var KEY = 'pip-docs-theme';
  function systemTheme() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    var btn = document.getElementById('theme-btn');
    if (btn) { btn.textContent = t === 'dark' ? '☀' : '☾'; btn.title = 'Switch to ' + (t === 'dark' ? 'light' : 'dark') + ' theme'; }
  }
  var stored = null;
  try { stored = localStorage.getItem(KEY); } catch (e) {}
  applyTheme(stored || systemTheme());
  var themeBtn = document.getElementById('theme-btn');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(KEY, next); } catch (e) {}
      applyTheme(next);
    });
  }

  // ---------------------------------------------------------------- drawer
  var menuBtn = document.getElementById('menu-btn');
  if (menuBtn) {
    menuBtn.addEventListener('click', function () {
      var open = document.body.getAttribute('data-drawer') === 'open';
      document.body.setAttribute('data-drawer', open ? 'closed' : 'open');
    });
  }
  var backdrop = document.querySelector('.backdrop');
  if (backdrop) backdrop.addEventListener('click', function () { document.body.setAttribute('data-drawer', 'closed'); });

  // ---------------------------------------------------------------- search
  var input = document.getElementById('q');
  var results = document.getElementById('results');
  var index = null, cursor = -1;

  function loadIndex() {
    if (index) return Promise.resolve(index);
    return fetch('search-index.json').then(function (r) { return r.json(); }).then(function (d) { index = d; return index; });
  }

  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]; }); }

  function highlight(text, q) {
    var i = text.toLowerCase().indexOf(q.toLowerCase());
    if (i < 0) return esc(text);
    return esc(text.slice(0, i)) + '<mark>' + esc(text.slice(i, i + q.length)) + '</mark>' + esc(text.slice(i + q.length));
  }

  function run(q) {
    if (!results) return;
    q = q.trim();
    if (q.length < 2) { results.setAttribute('data-open', 'false'); results.innerHTML = ''; cursor = -1; return; }
    loadIndex().then(function (idx) {
      var terms = q.toLowerCase().split(/\s+/);
      var hits = [];
      for (var i = 0; i < idx.length; i++) {
        var doc = idx[i];
        var hay = (doc.title + ' ' + doc.text).toLowerCase();
        var score = 0, ok = true;
        for (var t = 0; t < terms.length; t++) {
          var n = hay.split(terms[t]).length - 1;
          if (!n) { ok = false; break; }
          score += n * (doc.title.toLowerCase().indexOf(terms[t]) >= 0 ? 3 : 1);
        }
        if (ok) hits.push({ doc: doc, score: score, where: bestWhere(doc, terms[0]) });
      }
      hits.sort(function (a, b) { return b.score - a.score; });
      hits = hits.slice(0, 14);
      if (!hits.length) {
        results.innerHTML = '<a data-nohref="1"><small>No matches for "' + esc(q) + '"</small></a>';
      } else {
        results.innerHTML = hits.map(function (h, i) {
          return '<a href="' + h.doc.url + '" data-i="' + i + '"><b>' + highlight(h.doc.title, terms[0]) +
                 '</b><small>' + esc(h.doc.nav) + ' — ' + esc(h.where) + '</small></a>';
        }).join('');
      }
      cursor = -1;
      results.setAttribute('data-open', 'true');
    });
  }

  function bestWhere(doc, term) {
    var t = term.toLowerCase();
    var idx = doc.text.toLowerCase().indexOf(t);
    if (idx < 0) return doc.summary || '';
    var start = Math.max(0, idx - 55);
    var snippet = doc.text.slice(start, start + 150);
    return (start > 0 ? '…' : '') + snippet.trim() + '…';
  }

  function move(delta) {
    var links = results.querySelectorAll('a[href]');
    if (!links.length) return;
    if (cursor >= 0 && links[cursor]) links[cursor].removeAttribute('data-active');
    cursor = (cursor + delta + links.length) % links.length;
    links[cursor].setAttribute('data-active', 'true');
    links[cursor].scrollIntoView({ block: 'nearest' });
  }

  if (input) {
    input.addEventListener('input', function () { run(input.value); });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
      else if (e.key === 'Enter') {
        var active = results.querySelector('a[data-active="true"]') || results.querySelector('a[href]');
        if (active) { e.preventDefault(); window.location.href = active.getAttribute('href'); }
      } else if (e.key === 'Escape') { input.value = ''; results.setAttribute('data-open', 'false'); input.blur(); }
    });
    document.addEventListener('click', function (e) {
      if (!results.contains(e.target) && e.target !== input) results.setAttribute('data-open', 'false');
    });
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); input.focus(); input.select(); }
      if (e.key === '/' && document.activeElement !== input && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
        e.preventDefault(); input.focus();
      }
    });
  }

  // ---------------------------------------------------------------- diagrams
  var blocks = document.querySelectorAll('pre.mermaid');
  if (blocks.length) {
    var local = false;
    import('./' + MERMAID_LOCAL).then(function (m) {
      local = true; start(m.default, blocks);
    }).catch(function () {
      import(MERMAID_CDN).then(function (m) { start(m.default, blocks); })
        .catch(function () { blocks.forEach(function (b) { b.setAttribute('data-failed', 'true'); }); });
    });
  }
  function start(mermaid, blocks) {
    mermaid.initialize({
      startOnLoad: false, securityLevel: 'strict', theme: 'base', fontFamily: 'Inter, system-ui, sans-serif',
      flowchart: { curve: 'basis', useMaxWidth: true }, sequence: { useMaxWidth: true }
    });
    var theme = document.documentElement.getAttribute('data-theme');
    mermaid.render('m' + Math.random().toString(36).slice(2), '', '').catch(function () {});
    blocks.forEach(function (block, i) {
      var id = 'mmd-' + i;
      block.removeAttribute('data-failed');
      mermaid.render(id, block.textContent).then(function (r) {
        var holder = document.createElement('div');
        holder.className = 'diagram';
        holder.innerHTML = r.svg;
        block.parentNode.replaceChild(holder, block);
      }).catch(function () { block.setAttribute('data-failed', 'true'); });
    });
    void theme; void local;
  }

  // ---------------------------------------------------------------- toc + scrollspy
  var links = Array.prototype.slice.call(document.querySelectorAll('.toc a'));
  if (links.length) {
    var targets = links.map(function (a) { return document.getElementById(a.getAttribute('href').slice(1)); }).filter(Boolean);
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        links.forEach(function (a) {
          a.style.color = a.getAttribute('href') === '#' + entry.target.id ? 'var(--brand)' : '';
          a.style.fontWeight = a.getAttribute('href') === '#' + entry.target.id ? '600' : '';
        });
      });
    }, { rootMargin: '-70px 0px -75% 0px' });
    targets.forEach(function (t) { observer.observe(t); });
  }

  // ---------------------------------------------------------------- copy buttons
  document.querySelectorAll('.cmd').forEach(function (row) {
    var btn = row.querySelector('.copy');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var text = row.querySelector('code').textContent;
      var done = function () { btn.textContent = 'copied'; setTimeout(function () { btn.textContent = 'copy'; }, 1400); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () {});
      else done();
    });
  });
})();
