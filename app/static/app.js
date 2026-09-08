/* Verdant — vanilla JS SPA for the Gardening Blog & Observation Log. */
(() => {
  'use strict';

  // ─────────────────────────── helpers ───────────────────────────
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const esc = (s) =>
    String(s ?? '').replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const fmtDate = (iso) => {
    if (!iso) return '—';
    const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso);
    return Number.isNaN(d.getTime())
      ? iso
      : d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
  };

  const fmtDateTime = (iso) => {
    if (!iso) return '—';
    const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
    return Number.isNaN(d.getTime())
      ? iso
      : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  };

  const toast = (message, kind = 'info') => {
    const tones = {
      info: 'bg-navy-800 text-beige-50 ring-navy-600',
      ok: 'bg-sage-700 text-beige-50 ring-sage-500',
      err: 'bg-red-800 text-beige-50 ring-red-600',
    };
    const el = document.createElement('div');
    el.className = `pointer-events-auto rounded-xl px-4 py-3 text-sm shadow-botanical ring-1 transition duration-300 ${tones[kind] || tones.info}`;
    el.textContent = message;
    $('#toasts').append(el);
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(6px)';
      setTimeout(() => el.remove(), 320);
    }, 3600);
  };

  // ─────────────────────────── API client ───────────────────────────
  const api = {
    async request(method, path, { json, form } = {}) {
      const opts = { method, headers: {} };
      if (json !== undefined) {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(json);
      } else if (form) {
        opts.body = form;
      }
      const res = await fetch(path, opts);
      if (!res.ok) {
        let detail = `${res.status} ${res.statusText}`;
        try {
          const body = await res.json();
          if (body?.detail) {
            detail = Array.isArray(body.detail)
              ? body.detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
              : body.detail;
          }
        } catch { /* non-JSON error body */ }
        throw new Error(detail);
      }
      return res.status === 204 ? null : res.json();
    },
    get: (p) => api.request('GET', p),
    post: (p, json) => api.request('POST', p, { json }),
    patch: (p, json) => api.request('PATCH', p, { json }),
    del: (p) => api.request('DELETE', p),
    upload: (p, form) => api.request('POST', p, { form }),
  };

  // ─────────────────────── tiny markdown renderer ───────────────────────
  // Escapes first, then applies a safe subset: headings, lists, quotes,
  // fenced/inline code, bold/italic, links, hr, paragraphs.
  function markdown(src) {
    const text = esc(src ?? '').replace(/\r\n/g, '\n');
    const codeBlocks = [];
    let out = text.replace(/```([\s\S]*?)```/g, (_, code) => {
      codeBlocks.push(code.replace(/^\n/, ''));
      return `\u0000CODE${codeBlocks.length - 1}\u0000`;
    });

    const inline = (s) =>
      s
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>')
        .replace(/(^|[\s(])_([^_\n]+)_/g, '$1<em>$2</em>')
        .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
          '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    const lines = out.split('\n');
    const html = [];
    let list = null; // 'ul' | 'ol'
    let para = [];

    const flushPara = () => {
      if (para.length) {
        html.push(`<p>${inline(para.join(' '))}</p>`);
        para = [];
      }
    };
    const closeList = () => {
      if (list) { html.push(`</${list}>`); list = null; }
    };

    for (const raw of lines) {
      const line = raw.trimEnd();

      if (!line.trim()) { flushPara(); closeList(); continue; }

      let m;
      if ((m = line.match(/^(#{1,3})\s+(.*)$/))) {
        flushPara(); closeList();
        html.push(`<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`);
      } else if (/^(---|\*\*\*|___)$/.test(line.trim())) {
        flushPara(); closeList();
        html.push('<hr />');
      } else if ((m = line.match(/^\s*[-*+]\s+(.*)$/))) {
        flushPara();
        if (list !== 'ul') { closeList(); html.push('<ul>'); list = 'ul'; }
        html.push(`<li>${inline(m[1])}</li>`);
      } else if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
        flushPara();
        if (list !== 'ol') { closeList(); html.push('<ol>'); list = 'ol'; }
        html.push(`<li>${inline(m[1])}</li>`);
      } else if ((m = line.match(/^&gt;\s?(.*)$/))) {
        flushPara(); closeList();
        html.push(`<blockquote>${inline(m[1])}</blockquote>`);
      } else if (/^\u0000CODE\d+\u0000$/.test(line.trim())) {
        flushPara(); closeList();
        html.push(line.trim());
      } else {
        para.push(line.trim());
      }
    }
    flushPara(); closeList();

    return html
      .join('\n')
      .replace(/\u0000CODE(\d+)\u0000/g, (_, i) => `<pre><code>${codeBlocks[Number(i)]}</code></pre>`);
  }

  // ─────────────────────────── state ───────────────────────────
  const state = { posts: [], ferts: [], obs: [], search: '', plantFilter: '', albums: [] };

  // ─────────────────────────── stats ───────────────────────────
  const STAT_CARDS = [
    { key: 'posts', label: 'Entries', icon: '📖' },
    { key: 'observations', label: 'Observations', icon: '🔍' },
    { key: 'fertilizations', label: 'Feedings', icon: '🧪' },
    { key: 'images', label: 'Photos', icon: '🖼️' },
    { key: 'avg_health', label: 'Avg health', icon: '💚', suffix: ' / 10' },
  ];

  async function renderStats() {
    let s;
    try {
      s = await api.get('/api/stats');
    } catch {
      return;
    }
    $('#stats').innerHTML = STAT_CARDS.map(({ key, label, icon, suffix }) => {
      const raw = s[key];
      const value = raw === null || raw === undefined ? '—' : `${raw}${suffix || ''}`;
      return `
        <div class="rounded-xl border border-beige-300 bg-beige-50 px-4 py-3 shadow-sm">
          <dt class="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-navy-500">
            <span aria-hidden="true">${icon}</span>${esc(label)}
          </dt>
          <dd class="mt-1 font-display text-2xl font-semibold text-sage-700">${esc(value)}</dd>
        </div>`;
    }).join('');
  }

  // ─────────────────────────── blog feed ───────────────────────────
  function postCard(post) {
    const images = post.images || [];
    const gallery = images.length
      ? `<div class="grid gap-2 ${images.length === 1 ? 'grid-cols-1' : 'grid-cols-2 sm:grid-cols-3'}">
           ${images.map((img) => `
             <button type="button" class="group relative overflow-hidden rounded-lg ring-1 ring-beige-300"
                     data-lightbox="${esc(img.file_path)}">
               <img src="${esc(img.file_path)}" alt="Photo from ${esc(post.title)}" loading="lazy"
                    class="h-40 w-full object-cover transition duration-300 group-hover:scale-105" />
             </button>`).join('')}
         </div>`
      : '';

    return `
      <article class="card space-y-4" data-post="${post.id}">
        <header class="flex flex-wrap items-start justify-between gap-3 border-b border-beige-200 pb-3">
          <div>
            <h3 class="font-display text-xl font-semibold text-navy-800">${esc(post.title)}</h3>
            <p class="mt-1 text-xs text-navy-400">
              ${fmtDateTime(post.created_at)}
              ${post.updated_at && post.updated_at !== post.created_at ? ` · edited ${fmtDateTime(post.updated_at)}` : ''}
              ${images.length ? ` · <span class="pill">${images.length} photo${images.length === 1 ? '' : 's'}</span>` : ''}
            </p>
          </div>
          <div class="flex gap-2">
            <label class="btn-ghost cursor-pointer text-sm" title="Add photos">
              ＋📷<input type="file" accept="image/*" multiple class="hidden" data-add-images="${post.id}" />
            </label>
            <button type="button" class="btn-ghost text-sm" data-delete-post="${post.id}" title="Delete entry">🗑</button>
          </div>
        </header>
        ${post.content?.trim() ? `<div class="md">${markdown(post.content)}</div>` : ''}
        ${gallery}
      </article>`;
  }

  function renderFeed() {
    const feed = $('#feed');
    const items = state.posts;
    $('#feed-count').textContent = items.length
      ? `${items.length} entr${items.length === 1 ? 'y' : 'ies'}`
      : '';

    if (!items.length) {
      feed.innerHTML = `
        <div class="card border-dashed text-center text-navy-500">
          <p class="text-4xl">🌱</p>
          <p class="mt-2 font-display text-lg text-navy-700">No entries yet</p>
          <p class="text-sm">${state.search ? 'No entries match your search.' : 'Write your first garden story on the left.'}</p>
        </div>`;
      return;
    }
    feed.innerHTML = items.map(postCard).join('');
  }

  async function loadPosts() {
    const qs = state.search ? `?q=${encodeURIComponent(state.search)}` : '';
    try {
      state.posts = await api.get(`/api/posts${qs}`);
      renderFeed();
    } catch (e) {
      toast(`Could not load entries: ${e.message}`, 'err');
    }
  }

  // ─────────────────────────── logs tables ───────────────────────────
  function renderFerts() {
    $('#fert-count').textContent = state.ferts.length;
    const body = $('#fert-rows');
    if (!state.ferts.length) {
      body.innerHTML = `<tr><td class="td py-8 text-center text-navy-400" colspan="6">No fertilization entries yet.</td></tr>`;
      return;
    }
    body.innerHTML = state.ferts.map((f, i) => `
      <tr class="${i % 2 ? 'bg-beige-50/60' : 'bg-white'} hover:bg-sage-50">
        <td class="td whitespace-nowrap font-semibold text-navy-700">${fmtDate(f.date)}</td>
        <td class="td">${esc(f.fertilizer_name)}</td>
        <td class="td whitespace-nowrap">${f.npk_ratio ? `<span class="pill">${esc(f.npk_ratio)}</span>` : '—'}</td>
        <td class="td whitespace-nowrap">${esc(f.amount_used) || '—'}</td>
        <td class="td max-w-xs text-navy-600">${esc(f.notes) || '—'}</td>
        <td class="td text-right">
          <button type="button" class="text-navy-400 hover:text-red-700" data-delete-fert="${f.id}" title="Delete">🗑</button>
        </td>
      </tr>`).join('');
  }

  function healthBar(score) {
    const pct = (score / 10) * 100;
    const color = score >= 8 ? 'bg-sage-600' : score >= 5 ? 'bg-beige-500' : 'bg-red-600';
    return `
      <div class="flex items-center gap-2">
        <div class="h-2 w-16 overflow-hidden rounded-full bg-beige-200">
          <div class="h-full ${color}" style="width:${pct}%"></div>
        </div>
        <span class="text-xs font-bold text-navy-600">${score}</span>
      </div>`;
  }

  function renderObs() {
    $('#obs-count').textContent = state.obs.length;
    const body = $('#obs-rows');
    if (!state.obs.length) {
      body.innerHTML = `<tr><td class="td py-8 text-center text-navy-400" colspan="8">No observations yet.</td></tr>`;
      return;
    }
    body.innerHTML = state.obs.map((o, i) => {
      const imgs = (o.images || []).map((img) => `
        <button type="button" data-lightbox="${esc(img.file_path)}" class="inline-block">
          <img src="${esc(img.file_path)}" alt="${esc(o.plant_name)}" loading="lazy"
               class="h-10 w-10 rounded object-cover ring-1 ring-beige-300 hover:ring-sage-500" />
        </button>`).join(' ');
      return `
        <tr class="${i % 2 ? 'bg-beige-50/60' : 'bg-white'} hover:bg-sage-50">
          <td class="td whitespace-nowrap font-semibold text-navy-700">${fmtDate(o.date)}</td>
          <td class="td font-medium">${esc(o.plant_name)}</td>
          <td class="td">${healthBar(o.health_scale)}</td>
          <td class="td whitespace-nowrap">${o.watering_status
            ? '<span class="pill">💧 Watered</span>'
            : '<span class="text-navy-400">—</span>'}</td>
          <td class="td max-w-[10rem]">${o.pest_sightings
            ? `<span class="text-red-800">🐛 ${esc(o.pest_sightings)}</span>`
            : '<span class="text-navy-400">None</span>'}</td>
          <td class="td max-w-xs text-navy-600">${esc(o.notes) || '—'}</td>
          <td class="td">
            <div class="flex flex-wrap gap-1">${imgs || '<span class="text-navy-400">—</span>'}</div>
            <label class="mt-1 inline-block cursor-pointer text-xs text-sage-700 underline">
              add<input type="file" accept="image/*" multiple class="hidden" data-add-obs-images="${o.id}" />
            </label>
          </td>
          <td class="td text-right">
            <button type="button" class="text-navy-400 hover:text-red-700" data-delete-obs="${o.id}" title="Delete">🗑</button>
          </td>
        </tr>`;
    }).join('');
  }

  async function loadFerts() {
    try {
      state.ferts = await api.get('/api/fertilizations');
      renderFerts();
    } catch (e) {
      toast(`Could not load fertilizations: ${e.message}`, 'err');
    }
  }

  async function loadObs() {
    const qs = state.plantFilter ? `?plant=${encodeURIComponent(state.plantFilter)}` : '';
    try {
      state.obs = await api.get(`/api/observations${qs}`);
      renderObs();
    } catch (e) {
      toast(`Could not load observations: ${e.message}`, 'err');
    }
  }

  // ─────────────────────────── tabs ───────────────────────────
  function activateTab(name) {
    $$('.tab-btn').forEach((btn) => {
      btn.setAttribute('aria-selected', String(btn.dataset.tab === name));
    });
    $$('[data-panel]').forEach((panel) => {
      panel.classList.toggle('hidden', panel.dataset.panel !== name);
    });
    localStorage.setItem('verdant.tab', name);
  }

  // ─────────────────────────── uploads ───────────────────────────
  async function uploadImages(endpoint, files) {
    if (!files || !files.length) return null;
    const form = new FormData();
    Array.from(files).forEach((f) => form.append('files', f, f.name));
    return api.upload(endpoint, form);
  }

  // ─────────────────────────── albums & URL import ───────────────────────────
  async function loadAlbums() {
    try {
      state.albums = await api.get('/api/albums');
      renderAlbumSelects();
    } catch { /* albums are optional until used */ }
  }

  function renderAlbumSelects() {
    const sel = $('#post-album-select');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = '<option value="">Choose an album…</option>' +
      state.albums.map((a) => `<option value="${a.id}">${esc(a.name)} (${a.images.length})</option>`).join('');
    if (current && state.albums.some((a) => a.id === Number(current))) sel.value = current;
  }

  function wireAlbumPicker() {
    const loadBtn = $('#post-album-load');
    const grid = $('#post-album-grid');
    if (!loadBtn || !grid) return;
    loadBtn.addEventListener('click', async () => {
      const id = $('#post-album-select').value;
      if (!id) { toast('Pick an album first', 'info'); return; }
      loadBtn.disabled = true;
      try {
        const album = await api.get(`/api/albums/${id}`);
        grid.classList.remove('hidden');
        grid.innerHTML = (album.images || []).length
          ? album.images.map((img) => `
            <label class="relative cursor-pointer overflow-hidden rounded-lg ring-1 ring-beige-300 has-[:checked]:ring-sage-600 has-[:checked]:ring-2">
              <input type="checkbox" class="absolute z-10 m-1 accent-sage-600" data-album-image="${img.id}" value="${esc(img.title)}" />
              <img src="${esc(img.file_path)}" alt="${esc(img.title || 'album photo')}" loading="lazy" class="h-20 w-full object-cover" />
            </label>`).join('')
          : '<p class="col-span-3 text-sm text-navy-400">This album is empty — import from URL below.</p>';
      } catch (e) {
        toast(`Could not load album: ${e.message}`, 'err');
      } finally {
        loadBtn.disabled = false;
      }
    });
  }

  function wireUrlImport() {
    const btn = $('#post-import-urls');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      const raw = $('#post-import-url-input').value.trim();
      const urls = raw.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
      if (!urls.length) { toast('Paste at least one image URL', 'info'); return; }
      btn.disabled = true;
      try {
        const res = await api.post('/api/import/urls', { urls });
        const albumId = res.album.id;
        await loadAlbums();
        const sel = $('#post-album-select');
        sel.value = String(albumId);
        toast(`Imported ${res.created} photo${res.created === 1 ? '' : 's'} into "${res.album.name}"${res.failed ? ` (${res.failed} failed)` : ''}`, res.failed ? 'info' : 'ok');
        $('#post-album-load').click();
      } catch (e) {
        toast(`Import failed: ${e.message}`, 'err');
      } finally {
        btn.disabled = false;
      }
    });
  }

  // ─────────────────────────── wiring ───────────────────────────
  function wirePostForm() {
    const form = $('#post-form');
    const picker = $('#post-images');
    const preview = $('#post-images-preview');

    const renderPreview = () => {
      preview.innerHTML = Array.from(picker.files || []).map((f) => `
        <li class="overflow-hidden rounded-lg ring-1 ring-beige-300">
          <img src="${URL.createObjectURL(f)}" alt="${esc(f.name)}" class="h-20 w-full object-cover" />
        </li>`).join('');
    };
    picker.addEventListener('change', renderPreview);
    form.addEventListener('reset', () => setTimeout(() => {
      preview.innerHTML = '';
      const grid = $('#post-album-grid');
      if (grid) { grid.innerHTML = ''; grid.classList.add('hidden'); }
    }, 0));

    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const btn = $('button[type="submit"]', form);
      btn.disabled = true;
      try {
        const post = await api.post('/api/posts', {
          title: $('#post-title').value.trim(),
          content: $('#post-content').value,
        });
        const files = picker.files;
        if (files?.length) {
          try {
            await uploadImages(`/api/posts/${post.id}/images`, files);
          } catch (e) {
            toast(`Entry saved, but photos failed: ${e.message}`, 'err');
          }
        }

        // copy any checked album photos into the new post
        const albumGrid = $('#post-album-grid');
        const checked = albumGrid ? $$('[data-album-image]:checked', albumGrid) : [];
        if (checked.length) {
          const albumId = $('#post-album-select').value;
          const image_ids = checked.map((el) => Number(el.dataset.albumImage));
          try {
            await api.post(`/api/posts/${post.id}/from-album`, { album_id: Number(albumId), image_ids });
          } catch (e) {
            toast(`Entry saved, but album photos failed: ${e.message}`, 'err');
          }
        }

        form.reset();
        preview.innerHTML = '';
        toast('Entry published 🌿', 'ok');
        await Promise.all([loadPosts(), renderStats()]);
      } catch (e) {
        toast(`Could not publish: ${e.message}`, 'err');
      } finally {
        btn.disabled = false;
      }
    });
  }

  function wireFertForm() {
    const form = $('#fert-form');
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const btn = $('button[type="submit"]', form);
      btn.disabled = true;
      try {
        await api.post('/api/fertilizations', {
          date: $('#fert-date').value,
          fertilizer_name: $('#fert-name').value.trim(),
          npk_ratio: $('#fert-npk').value.trim(),
          amount_used: $('#fert-amount').value.trim(),
          notes: $('#fert-notes').value,
        });
        form.reset();
        $('#fert-date').value = new Date().toISOString().slice(0, 10);
        toast('Fertilization logged 🧪', 'ok');
        await Promise.all([loadFerts(), renderStats()]);
      } catch (e) {
        toast(`Could not save: ${e.message}`, 'err');
      } finally {
        btn.disabled = false;
      }
    });
  }

  function wireObsForm() {
    const form = $('#obs-form');
    const range = $('#obs-health');
    range.addEventListener('input', () => { $('#obs-health-out').textContent = range.value; });

    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const btn = $('button[type="submit"]', form);
      btn.disabled = true;
      try {
        const obs = await api.post('/api/observations', {
          date: $('#obs-date').value,
          plant_name: $('#obs-plant').value.trim(),
          health_scale: Number(range.value),
          watering_status: $('#obs-water').value === 'true',
          pest_sightings: $('#obs-pests').value.trim(),
          notes: $('#obs-notes').value,
        });
        const files = $('#obs-images').files;
        if (files?.length) {
          try {
            await uploadImages(`/api/observations/${obs.id}/images`, files);
          } catch (e) {
            toast(`Observation saved, but photos failed: ${e.message}`, 'err');
          }
        }
        form.reset();
        $('#obs-date').value = new Date().toISOString().slice(0, 10);
        $('#obs-health-out').textContent = $('#obs-health').value;
        toast('Observation logged 🔍', 'ok');
        await Promise.all([loadObs(), renderStats()]);
      } catch (e) {
        toast(`Could not save: ${e.message}`, 'err');
      } finally {
        btn.disabled = false;
      }
    });
  }

  function wireDelegatedEvents() {
    document.addEventListener('click', async (ev) => {
      const lightbox = ev.target.closest('[data-lightbox]');
      if (lightbox) {
        $('#lightbox-img').src = lightbox.dataset.lightbox;
        $('#lightbox').classList.replace('hidden', 'flex');
        return;
      }

      const delPost = ev.target.closest('[data-delete-post]');
      if (delPost && confirm('Delete this entry and its photos?')) {
        try {
          await api.del(`/api/posts/${delPost.dataset.deletePost}`);
          toast('Entry deleted', 'ok');
          await Promise.all([loadPosts(), renderStats()]);
        } catch (e) { toast(e.message, 'err'); }
        return;
      }

      const delFert = ev.target.closest('[data-delete-fert]');
      if (delFert && confirm('Delete this fertilization entry?')) {
        try {
          await api.del(`/api/fertilizations/${delFert.dataset.deleteFert}`);
          toast('Entry deleted', 'ok');
          await Promise.all([loadFerts(), renderStats()]);
        } catch (e) { toast(e.message, 'err'); }
        return;
      }

      const delObs = ev.target.closest('[data-delete-obs]');
      if (delObs && confirm('Delete this observation and its photos?')) {
        try {
          await api.del(`/api/observations/${delObs.dataset.deleteObs}`);
          toast('Observation deleted', 'ok');
          await Promise.all([loadObs(), renderStats()]);
        } catch (e) { toast(e.message, 'err'); }
      }
    });

    // Add-photos-to-existing-record pickers (rendered dynamically).
    document.addEventListener('change', async (ev) => {
      const postPicker = ev.target.closest('[data-add-images]');
      if (postPicker) {
        try {
          await uploadImages(`/api/posts/${postPicker.dataset.addImages}/images`, postPicker.files);
          toast('Photos added 📷', 'ok');
          await Promise.all([loadPosts(), renderStats()]);
        } catch (e) { toast(e.message, 'err'); }
        return;
      }
      const obsPicker = ev.target.closest('[data-add-obs-images]');
      if (obsPicker) {
        try {
          await uploadImages(`/api/observations/${obsPicker.dataset.addObsImages}/images`, obsPicker.files);
          toast('Photos added 📷', 'ok');
          await Promise.all([loadObs(), renderStats()]);
        } catch (e) { toast(e.message, 'err'); }
      }
    });

    $('#lightbox').addEventListener('click', () => {
      $('#lightbox').classList.replace('flex', 'hidden');
      $('#lightbox-img').src = '';
    });
    document.addEventListener('keydown', (ev) => {
      if (ev.key === 'Escape') {
        $('#lightbox').classList.replace('flex', 'hidden');
      }
    });
  }

  function debounce(fn, ms = 280) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  function wireFilters() {
    $('#post-search').addEventListener('input', debounce((ev) => {
      state.search = ev.target.value.trim();
      loadPosts();
    }));
    $('#obs-filter').addEventListener('input', debounce((ev) => {
      state.plantFilter = ev.target.value.trim();
      loadObs();
    }));
    $$('.tab-btn').forEach((btn) =>
      btn.addEventListener('click', () => activateTab(btn.dataset.tab)));
  }

  // ─────────────────────────── boot ───────────────────────────
  function boot() {
    const today = new Date().toISOString().slice(0, 10);
    $('#fert-date').value = today;
    $('#obs-date').value = today;

    wirePostForm();
    wireFertForm();
    wireObsForm();
    wireFilters();
    wireDelegatedEvents();
    wireAlbumPicker();
    wireUrlImport();
    activateTab(localStorage.getItem('verdant.tab') || 'blog');

    Promise.all([loadPosts(), loadFerts(), loadObs(), renderStats(), loadAlbums()]);

    const v = document.documentElement.dataset.version;
    const ve = $('#app-version');
    if (v && ve) ve.textContent = `v${v}`;
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
