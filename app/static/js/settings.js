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
      $('#set-lat').value = s.garden_lat || '';
      $('#set-lon').value = s.garden_lon || '';
      $('#set-temp-unit').value = s.temperature_unit || 'F';
      $('#set-week-start').value = s.week_start || '0';
      $('#set-weight-unit').value = s.default_weight_unit || 'oz';
      $('#set-slideshow-interval').value = String(s.slideshow_interval || 5);
      $('#set-confirm-water-all').checked = s.confirm_water_all !== false;
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
          garden_lat: $('#set-lat').value.trim(),
          garden_lon: $('#set-lon').value.trim(),
          digest_enabled: $('#set-digest-enabled').checked,
          discord_webhook_url: $('#set-webhook').value.trim(),
          digest_time: $('#set-digest-time').value || '08:00',
          temperature_unit: $('#set-temp-unit').value,
          week_start: $('#set-week-start').value,
          default_weight_unit: $('#set-weight-unit').value,
          slideshow_interval: Number($('#set-slideshow-interval').value) || 5,
          confirm_water_all: $('#set-confirm-water-all').checked,
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
        toast(`Could not send: ${error.message}`, 'error');
      }
    });

    // "Use my location": browser geolocation first (accurate, needs a secure
    // context + permission); one-shot city-level IP lookup as fallback.
    // Click-only — never in the background. Fills the fields; saving is
    // still the user's explicit Save settings click.
    $('#set-locate').addEventListener('click', async () => {
      const btn = $('#set-locate');
      const fill = (lat, lon, where) => {
        $('#set-lat').value = lat;
        $('#set-lon').value = lon;
        toast(`Location filled in${where ? ` — ${where}` : ''}. Hit Save settings to apply.`, 'ok');
      };
      btn.disabled = true;
      try {
        if (globalThis.navigator && globalThis.navigator.geolocation) {
          const pos = await new Promise((resolve, reject) => {
            globalThis.navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 8000 });
          });
          fill(pos.coords.latitude.toFixed(5), pos.coords.longitude.toFixed(5), 'from your browser');
          return;
        }
        throw new Error('geolocation unavailable');
      } catch (error) {
        try {
          const geo = await api.get('/api/weather/geolocate');
          if (geo && geo.ok) {
            fill(Number(geo.lat).toFixed(4), Number(geo.lon).toFixed(4),
              geo.city ? `city-level, near ${geo.city}` : 'city-level');
          } else {
            toast('Could not determine your location — enter it by hand.', 'err');
          }
        } catch (fallbackError) {
          toast('Could not determine your location — enter it by hand.', 'err');
        }
      } finally {
        btn.disabled = false;
      }
    });

    load().catch((error) => toast(`Could not load settings: ${error.message}`, 'err'));
  }

  globalThis.Verdant.onBoot(initSettings);
})();
