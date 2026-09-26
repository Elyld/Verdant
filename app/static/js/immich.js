/* Immich import wiring on the Photos page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initImmich() {
    const sections = $$('#immich-section');
    if (!sections.length) return;
    api.get('/api/immich/status')
      .then((status) => {
        if (!status.configured) return null;
        sections.forEach((section) => section.classList.remove('hidden'));
        return api.get('/api/immich/albums');
      })
      .then((albums) => {
        if (!albums) return;
        $$('#immich-album-select').forEach((sel) => {
          sel.innerHTML = '<option value="">Choose an Immich album…</option>'
            + albums.map((a) => `<option value="${esc(a.id)}">${esc(a.albumName)} (${a.assetCount})</option>`).join('');
        });
      })
      .catch(() => { /* Immich unreachable: leave the section hidden */ });
    $$('#immich-import').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const section = btn.closest('#immich-section');
        const sel = (section && section.querySelector('#immich-album-select')) || $('#immich-album-select');
        const immichAlbumId = sel && sel.value;
        if (!immichAlbumId) { toast('Choose an Immich album first.', 'err'); return; }
        btn.disabled = true;
        const label = btn.textContent;
        try {
          // Big albums import in batches (50/request) so no single request
          // times out. Batches are idempotent server-side: a retried batch
          // never duplicates photos.
          const batchSize = 50;
          let localAlbumId = null, offset = 0, done = false;
          let totalCreated = 0, totalFailed = 0, albumName = '';
          let firstErrors = [];
          while (!done) {
            const qs = `?offset=${offset}&limit=${batchSize}` + (localAlbumId ? `&album_id=${localAlbumId}` : '');
            const result = await api.post(`/api/immich/albums/${encodeURIComponent(immichAlbumId)}/import${qs}`);
            localAlbumId = result.album_id;
            albumName = result.album_name;
            totalCreated += result.created;
            totalFailed += result.failed || 0;
            if (result.errors && result.errors.length && firstErrors.length < 3) {
              firstErrors = firstErrors.concat(result.errors.slice(0, 3 - firstErrors.length));
            }
            offset += batchSize;
            done = result.done;
            // A whole batch that fails with nothing imported will never
            // recover (e.g. a missing API permission): stop instead of
            // hammering the server with more doomed requests.
            if (result.created === 0 && (result.failed || 0) > 0) done = true;
            btn.textContent = `Importing… ${result.imported}/${result.total}`;
          }
          if (totalCreated === 0 && totalFailed > 0) {
            toast(`Import failed: ${firstErrors[0] || 'every photo failed to download.'}`, 'err');
          } else {
            toast(`Imported ${totalCreated} photo${totalCreated === 1 ? '' : 's'} into \u201C${albumName}\u201D.`
              + (totalFailed ? ` (${totalFailed} failed)` : ''));
            document.dispatchEvent(new CustomEvent('verdant:albums-changed', { detail: { selectId: localAlbumId } }));
          }
        } catch (error) {
          toast(`Import failed: ${error.message}`, 'err');
        } finally {
          btn.disabled = false;
          btn.textContent = label;
        }
      });
    });
  }

  function initMergeButton() {
    $$('#immich-merge').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const label = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Merging…';
        try {
          const result = await api.post('/api/albums/merge-duplicates');
          if (!result || !result.groups_merged) {
            toast('No duplicate albums found.');
          } else {
            toast(`Merged ${result.albums_removed} duplicate album${result.albums_removed === 1 ? '' : 's'}`
              + (result.files_removed ? `, freed ${result.files_removed} duplicate file${result.files_removed === 1 ? '' : 's'}` : '')
              + '.');
            document.dispatchEvent(new CustomEvent('verdant:albums-changed', {}));
          }
        } catch (error) {
          toast(`Merge failed: ${error.message}`, 'err');
        } finally {
          btn.disabled = false;
          btn.textContent = label;
        }
      });
    });
  }

  globalThis.Verdant.onBoot(initImmich);
  globalThis.Verdant.onBoot(initMergeButton);
})();
