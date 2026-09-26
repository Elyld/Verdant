/* Backup page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initBackup() {
    const form = $('#restore-form');
    if (!form) return {};
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
