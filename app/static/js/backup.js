/* Backup page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initBackup() {
    const form = $('#restore-form');
    if (!form) return {};

    // Download button: fetch the zip so we can show progress and real errors
    // instead of a silent link that looks like it did nothing.
    const dlBtn = $('#backup-download');
    if (dlBtn) {
      dlBtn.addEventListener('click', async () => {
        const orig = dlBtn.textContent;
        dlBtn.disabled = true;
        dlBtn.textContent = 'Preparing backup…';
        try {
          const res = await fetch('/api/backup/export');
          if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.detail || `Backup failed (${res.status})`);
          }
          const blob = await res.blob();
          const cd = res.headers.get('Content-Disposition') || '';
          const m = /filename="([^"]+)"/.exec(cd);
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = m ? m[1] : 'verdant-backup.zip';
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(a.href), 5000);
          toast('Backup downloaded — check your Downloads folder.', 'ok');
        } catch (err) {
          toast(err.message || 'Backup failed.', 'err');
        } finally {
          dlBtn.disabled = false;
          dlBtn.textContent = orig;
        }
      });
    }

    const result = $('#restore-result');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const fileInput = $('#restore-file');
      const file = fileInput.files[0];
      if (!file) { toast('Choose a backup file first.', 'err'); return; }
      const submit = $('#restore-submit');
      submit.disabled = true;
      submit.textContent = 'Restoring…';
      try {
        const body = new FormData();
        body.append('file', file);
        const res = await fetch('/api/backup/import', { method: 'POST', body });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Restore failed (${res.status})`);
        const counts = data.restored || {};
        const total = Object.values(counts).reduce((a, b) => a + b, 0);
        result.classList.remove('hidden');
        result.innerHTML = `<div class="rounded-xl border border-sage-300 bg-sage-50 p-4 text-sage-800">✅ Restored <b>${total}</b> records from backup. Reloading…</div>`;
        toast(`Backup restored: ${total} records.`, 'ok');
        setTimeout(() => window.location.reload(), 1500);
      } catch (error) {
        toast(error.message, 'err');
        result.classList.remove('hidden');
        result.innerHTML = `<div class="rounded-xl border border-red-300 bg-red-50 p-4 text-red-800">⚠️ ${error.message}</div>`;
      } finally {
        submit.disabled = false;
        submit.textContent = 'Restore backup';
      }
    });
    return {};
  }

  globalThis.Verdant.onBoot(initBackup);
})();
