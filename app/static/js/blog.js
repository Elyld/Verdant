/* Blog & Stories page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function postCard(post) {
    const images = post.images || [];
    return `<article class="card space-y-4" data-post="${post.id}">
      <header class="flex justify-between gap-3 border-b border-beige-200 pb-3">
        <div><h3 class="font-display text-xl font-semibold">${esc(post.title)}</h3><p class="text-xs text-navy-400">${fmtDateTime(post.created_at)}</p></div>
        <div class="flex gap-2"><button type="button" class="btn-ghost text-sm" data-edit-post="${post.id}">Edit</button><button type="button" class="btn-ghost text-sm" data-delete-post="${post.id}" aria-label="Delete entry">🗑</button></div>
      </header>
      ${post.content?.trim() ? `<div class="md">${markdown(post.content)}</div>` : ''}
      ${images.length ? `<div class="grid grid-cols-2 gap-2 sm:grid-cols-3">${images.map((image) => `<button type="button" data-lightbox="${esc(image.file_path)}"><img src="${esc(image.file_path)}" alt="Photo from ${esc(post.title)}" class="h-40 w-full rounded-lg object-cover"></button>`).join('')}</div>` : ''}
    </article>`;
  }

  function initBlog() {
    const form = $('#post-form');
    if (!form) return {};
    let posts = [];
    let editingId = null;
    let offset = 0;
    const pageSize = 20;
    const feed = $('#feed');
    const loadMore = $('#posts-load-more');

    async function loadPosts(reset = true) {
      if (reset) offset = 0;
      const query = $('#post-search')?.value.trim() || '';
      const batch = await api.get(`/api/posts?limit=${pageSize}&offset=${offset}${query ? `&q=${encodeURIComponent(query)}` : ''}`);
      posts = reset ? batch : posts.concat(batch);
      feed.innerHTML = posts.length ? posts.map(postCard).join('') : '<div class="card text-center text-navy-500">No entries yet. Write your first garden story.</div>';
      $('#feed-count').textContent = `${posts.length} ${posts.length === 1 ? 'entry' : 'entries'}`;
      if (loadMore) loadMore.classList.toggle('hidden', batch.length < pageSize);
    }

    wireDraft(form, 'verdant.draft.blog', ['#post-title', '#post-content']);
    $('#post-images')?.addEventListener('change', (event) => {
      $('#post-images-preview').innerHTML = Array.from(event.target.files || []).map((file) => `<li class="text-xs text-navy-500">${esc(file.name)}</li>`).join('');
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = $('button[type="submit"]', form);
      button.disabled = true;
      try {
        const payload = { title: $('#post-title').value.trim(), content: $('#post-content').value };
        const post = editingId
          ? await api.patch(`/api/posts/${editingId}`, payload)
          : await api.post('/api/posts', payload);
        if (!editingId) await uploadFiles(`/api/posts/${post.id}/images`, $('#post-images').files);
        editingId = null;
        form.reset();
        localStorage.removeItem('verdant.draft.blog');
        button.textContent = 'Publish entry';
        toast('Entry saved 🌿', 'ok');
        await Promise.all([loadPosts(), renderStats()]);
      } catch (error) { toast(`Could not save: ${error.message}`, 'err'); }
      finally { button.disabled = false; }
    });
    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-edit-post]');
      if (!button) return;
      const post = posts.find((item) => item.id === Number(button.dataset.editPost));
      if (!post) return;
      editingId = post.id;
      $('#post-title').value = post.title;
      $('#post-content').value = post.content || '';
      $('button[type="submit"]', form).textContent = 'Save changes';
      form.scrollIntoView({ behavior: 'smooth' });
    });
    let searchTimer;
    $('#post-search')?.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadPosts(), 250);
    });
    loadMore?.addEventListener('click', async () => { offset += pageSize; await loadPosts(false); });
    loadPosts().catch((error) => toast(`Could not load entries: ${error.message}`, 'err'));
    renderStats();
    return { posts: loadPosts };
  }

  globalThis.Verdant.onBoot(initBlog);
})();
