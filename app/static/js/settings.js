/* Settings page: garden zone / frost dates + morning digest. */
(() => {
  'use strict';

  const { $, esc, api, toast } = globalThis.Verdant;

  function renderPreview(preview) {
    const box = $('#frost-preview');
    if (!box || !preview) return;
    const fmt = (p, icon, name) => {
      if (!p || !p.date) return `${icon} ${name}: <span class="text-navy-400">not set</span>`;
      const when = p.days_until === 0 ? 'today'
        : p.days_until === 1 ? 'tomorrow'
        : `in ${p.days_until}d`;
      const d = new Date(p.date + 'T12:00:00');
      const nice = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      return `${icon} ${name} ≈ <strong>${nice}</strong> <span class="text-navy-400">(${esc(p.label)} · ${when})</span>`;
    };
    box.innerHTML = `${fmt(preview.last, '🌸', 'Last spring frost')}<br>${fmt(preview.first, '❄️', 'First fall frost')}`;
  }

  function initSettings() {
    const form = $('#settings-form');
    if (!form) return;

    const status = $('#settings-status');

    async function load() {
      const s = await api.get('/api/settings');
      $('#set-zone').value = s.zone || '';
      $('#set-first-frost').value = (s.frost_date || '').slice(0, 10);
      $('#set-last-frost').value = (s.last_frost_date || '').slice(0, 10);
      $('#set-digest-enabled').checked = !!s.digest_enabled;
      $('#set-webhook').value = s.discord_webhook_url || '';
      $('#set-digest-time').value = s.digest_time || '08:00';
      renderPreview(s.frost_preview);
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      status.textContent = 'Saving…';
      try {
        const saved = await api.put('/api/settings', {
          zone: $('#set-zone').value,
          frost_date: $('#set-first-frost').value,
          last_frost_date: $('#set-last-frost').value,
          digest_enabled: $('#set-digest-enabled').checked,
          discord_webhook_url: $('#set-webhook').value.trim(),
          digest_time: $('#set-digest-time').value || '08:00',
        });
        renderPreview(saved.frost_preview);
        status.textContent = '';
        toast('Settings saved 🌿', 'ok');
      } catch (error) {
        status.textContent = '';
        toast(`Could not save: ${error.message}`, 'err');
      }
    });

    $('#digest-test').addEventListener('click', async () => {
      try {
        await api.post('/api/digest/send');
        toast('Test digest sent — check Discord 💬', 'ok');
      } catch (error) {
        toast(`Could not send: ${error.message}`, 'err');
      }
    });

    load().catch((error) => toast(`Could not load settings: ${error.message}`, 'err'));
  }

  globalThis.Verdant.onBoot(initSettings);
})();
