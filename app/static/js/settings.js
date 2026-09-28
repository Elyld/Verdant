/* Settings page: garden zone / frost dates + morning digest + mobile tab bar. */
(() => {
  'use strict';

  const { $, esc, api, toast, NAV_SECTIONS, DEFAULT_MOBILE_TABS, MAX_MOBILE_TABS, parseMobileTabs } = globalThis.Verdant;

  // Mobile tab-bar chip picker: up to MAX_MOBILE_TABS section keys, in tap order.
  let mobileTabPicks = [];

  function renderMobileChips() {
    const host = $('#mobile-tab-chips');
    if (!host) return;
    host.innerHTML = NAV_SECTIONS.map((s) => {
      const idx = mobileTabPicks.indexOf(s.key);
      const on = idx >= 0;
      return `<button type="button" class="tab-chip" data-key="${s.key}" aria-pressed="${on}">` +
        `<span class="tab-chip-order"${on ? '' : ' hidden'}>${on ? idx + 1 : ''}</span>` +
        `<span aria-hidden="true">${s.icon}</span><span>${esc(s.label)}</span></button>`;
    }).join('');
    const count = $('#mobile-tab-count');
    if (count) {
      count.textContent = mobileTabPicks.length
        ? `${mobileTabPicks.length} of ${MAX_MOBILE_TABS} tabs picked`
        : `No picks yet — the tab bar will use ${DEFAULT_MOBILE_TABS.map((k) => (NAV_SECTIONS.find((s) => s.key === k) || {}).label || k).join(', ')}.`;
    }
  }

  function initMobileChips() {
    const host = $('#mobile-tab-chips');
    if (!host || host.dataset.wired) return;
    host.dataset.wired = '1';
    host.addEventListener('click', (event) => {
      const btn = event.target.closest('[data-key]');
      if (!btn) return;
      const key = btn.getAttribute('data-key');
      const at = mobileTabPicks.indexOf(key);
      if (at >= 0) {
        mobileTabPicks.splice(at, 1);
      } else {
        if (mobileTabPicks.length >= MAX_MOBILE_TABS) {
          toast(`Up to ${MAX_MOBILE_TABS} tabs — remove one first.`, 'err');
          return;
        }
        mobileTabPicks.push(key);
      }
      renderMobileChips();
    });
  }

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
      $('#set-ai-enabled').checked = !!s.local_ai_enabled;
      $('#set-ai-base').value = s.local_ai_base_url || 'http://localhost:11434';
      $('#set-ai-model').value = s.local_ai_model || 'qwen3:4b';
      $('#set-plantnet-key').value = s.plantnet_api_key || '';
      mobileTabPicks = parseMobileTabs(s.mobile_tabs) || [];
      initMobileChips();
      renderMobileChips();
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
          mobile_tabs: JSON.stringify(mobileTabPicks),
          local_ai_enabled: $('#set-ai-enabled').checked,
          local_ai_base_url: $('#set-ai-base').value.trim(),
          local_ai_model: $('#set-ai-model').value.trim(),
          plantnet_api_key: $('#set-plantnet-key').value.trim(),
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

    // Local AI: ping the model server (GET /api/ai/status hits /api/tags).
    $('#ai-test').addEventListener('click', async () => {
      const box = $('#ai-test-status');
      box.textContent = 'Checking…';
      try {
        const st = await api.get('/api/ai/status');
        if (!st.enabled) {
          box.textContent = 'Enable it and save first, then test.';
        } else if (st.reachable) {
          const n = (st.models || []).length;
          if (st.model_present === false) {
            box.textContent = `Connected ✓, but "${st.model}" isn't on the server — run \`ollama pull ${st.model}\` where Ollama runs, then test again.`;
          } else {
            box.textContent = `Connected ✓${n ? ` (${n} model${n === 1 ? '' : 's'} on the server)` : ''}`;
          }
        } else {
          box.textContent = st.hint || 'Not reachable.';
          if (st.error) box.textContent += ` (detail: ${st.error})`;
        }
      } catch (error) {
        box.textContent = `Check failed: ${error.message}`;
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

    async function detectZone({ silent } = {}) {
      const lat = Number($('#set-lat').value);
      const lon = Number($('#set-lon').value);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
        if (!silent) toast('Enter your coordinates first, then detect.', 'err');
        return;
      }
      const note = $('#zone-detect-note');
      try {
        const res = await api.get(`/api/settings/detect-zone?lat=${lat}&lon=${lon}`);
        if (res && res.ok && res.zone_setting) {
          $('#set-zone').value = res.zone_setting;
          if (note) {
            note.textContent = `Detected from your coordinates: USDA zone ${res.zone} → set to zone ${res.zone_setting}.`;
            note.classList.remove('hidden');
          }
        } else if (!silent) {
          toast('No hardiness zone found for those coordinates.', 'err');
        }
      } catch (error) {
        if (!silent) toast(`Zone detection failed: ${error.message}`, 'err');
      }
    }

    $('#zone-detect').addEventListener('click', () => detectZone());

    // Auto-detect the zone when coordinates change and no zone is set yet.
    let zoneTimer = null;
    const maybeAutoDetect = () => {
      clearTimeout(zoneTimer);
      zoneTimer = setTimeout(() => {
        if (!$('#set-zone').value) detectZone({ silent: true });
      }, 600);
    };
    $('#set-lat').addEventListener('change', maybeAutoDetect);
    $('#set-lon').addEventListener('change', maybeAutoDetect);

    load().catch((error) => toast(`Could not load settings: ${error.message}`, 'err'));
  }

  globalThis.Verdant.onBoot(initSettings);
})();
