/* NFC tag manager page. */
(() => {
  'use strict';

  const { $, $$, esc, api, toast } = globalThis.Verdant;

  const ACTIONS = {
    plant: { label: '🌱 Open plant profile', target: 'plant', hint: 'Tap → that plant\u2019s profile opens.' },
    quick_plant: { label: '⚡ Quick-log for a plant', target: 'plant', hint: 'Tap → Quick Log opens for that plant (water, harvest, note).' },
    fertilize: { label: '🧪 Log a feeding', target: 'fertilizer', hint: 'Stick on the fertilizer bottle — tap → feeding form with that fertilizer pre-selected.' },
    pest: { label: '🐛 Log pest treatment', target: 'text', textLabel: 'Product name', hint: 'Stick on the spray bottle — tap → pest log with the product pre-filled.' },
    harvest: { label: '🧺 Harvest log for a plant', target: 'plant', hint: 'Tap → Quick Log with the harvest stepper ready for that plant.' },
    harvest_any: { label: '🧺 Harvest log (any plant)', target: 'none', hint: 'Stick on the harvest basket — tap → Quick Log harvest mode.' },
    location: { label: '📍 Quick-log for a location', target: 'location', hint: 'Stick on a bed or bag cluster — tap → Quick Log filtered to that location.' },
    seed_add: { label: '🌱 Add seed packet', target: 'none', hint: 'Stick on the seed binder — tap → the seed catalog add form opens.' },
    water: { label: '💧 Watering log for a location', target: 'location', hint: 'Stick on the hose or watering can — tap → Quick Log watering for that location.' },
  };

  function initTags() {
    if (!$('#panel-tags')) return;
    let plants = [], fertilizers = [], locations = [];

    function targetLabel(tag) {
      const meta = ACTIONS[tag.action] || {};
      if (meta.target === 'text') return esc(tag.target_text || '—');
      if (meta.target === 'none') return '<span class="text-navy-400">—</span>';
      const pools = { plant: plants, fertilizer: fertilizers, location: locations };
      const found = (pools[meta.target] || []).find((x) => x.id === tag.target_id);
      const name = found ? (found.variety_name || found.name) : null;
      return esc(name || `id ${tag.target_id || '?'}`);
    }

    function tagUrl(tag) {
      return `${location.origin}/t/${tag.code}`;
    }

    function row(tag) {
      const meta = ACTIONS[tag.action] || { label: tag.action };
      const url = tagUrl(tag);
      return `<div class="rounded-xl bg-beige-50 p-4 ring-1 ring-beige-200">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p class="font-semibold text-navy-800">🏷️ ${esc(tag.label)}</p>
            <p class="text-sm text-navy-500">${esc(meta.label)} · ${targetLabel(tag)}</p>
            <p class="mt-1 text-xs text-navy-400">${tag.tap_count} tap${tag.tap_count === 1 ? '' : 's'}${tag.last_tapped_at ? ` · last tapped ${esc(tag.last_tapped_at.slice(0, 16).replace('T', ' '))}` : ''}</p>
          </div>
          <button type="button" data-del-tag="${tag.id}" class="text-xs text-red-700 underline">delete</button>
        </div>
        <div class="mt-2 flex items-center gap-2">
          <input type="text" readonly value="${esc(url)}" class="inp font-mono text-xs" onclick="this.select()" aria-label="Tag URL" />
          <button type="button" data-copy-tag="${esc(url)}" class="btn-ghost shrink-0 text-xs">Copy</button>
        </div>
      </div>`;
    }

    async function load() {
      const tags = await api.get('/api/tags/').catch(() => []);
      const list = Array.isArray(tags) ? tags : [];
      $('#tag-empty').classList.toggle('hidden', list.length > 0);
      $('#tag-list').innerHTML = list.map(row).join('');
    }

    async function loadTargets() {
      const [p, f, l] = await Promise.all([
        api.get('/api/plants/').catch(() => []),
        api.get('/api/fertilizers/').catch(() => []),
        api.get('/api/locations/').catch(() => []),
      ]);
      plants = Array.isArray(p) ? p : [];
      fertilizers = Array.isArray(f) ? f : [];
      locations = Array.isArray(l) ? l : [];
      syncTargetField();
    }

    function syncTargetField() {
      const action = $('#tag-action').value;
      const meta = ACTIONS[action] || {};
      const selWrap = $('#tag-target-wrap');
      const textWrap = $('#tag-text-wrap');
      selWrap.classList.toggle('hidden', meta.target !== 'plant' && meta.target !== 'fertilizer' && meta.target !== 'location');
      textWrap.classList.toggle('hidden', meta.target !== 'text');
      $('#tag-action-hint').textContent = meta.hint || '';
      if (meta.target === 'plant') {
        $('#tag-target-lbl').textContent = 'Plant';
        $('#tag-target').innerHTML = plants.map((x) => `<option value="${x.id}">${esc(x.variety_name)}</option>`).join('');
      } else if (meta.target === 'fertilizer') {
        $('#tag-target-lbl').textContent = 'Fertilizer';
        $('#tag-target').innerHTML = fertilizers.map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join('');
      } else if (meta.target === 'location') {
        $('#tag-target-lbl').textContent = 'Location';
        $('#tag-target').innerHTML = locations.map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join('');
      } else if (meta.target === 'text') {
        $('#tag-text-lbl').textContent = meta.textLabel || 'Value';
        $('#tag-text').placeholder = action === 'pest' ? 'Neem oil' : '';
      }
    }

    $('#tag-action').innerHTML = Object.entries(ACTIONS)
      .map(([k, v]) => `<option value="${k}">${esc(v.label)}</option>`).join('');
    $('#tag-action').addEventListener('change', syncTargetField);

    $('#tag-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const action = $('#tag-action').value;
      const meta = ACTIONS[action] || {};
      const payload = { label: $('#tag-label').value.trim(), action };
      if (meta.target === 'plant' || meta.target === 'fertilizer' || meta.target === 'location') {
        payload.target_id = $('#tag-target').value ? Number($('#tag-target').value) : null;
      } else if (meta.target === 'text') {
        payload.target_text = $('#tag-text').value.trim();
      }
      if (!payload.label) { toast('Give the tag a label.', 'error'); return; }
      try {
        await api.post('/api/tags/', payload);
        e.target.reset();
        $('#tag-action').value = 'plant';
        syncTargetField();
        toast('Tag created — write its URL onto a blank NFC tag.');
        load();
      } catch (err) {
        toast(err.message || 'Could not create tag.', 'error');
      }
    });

    $('#tag-list').addEventListener('click', async (e) => {
      const copyBtn = e.target.closest('[data-copy-tag]');
      if (copyBtn) {
        try {
          await navigator.clipboard.writeText(copyBtn.dataset.copyTag);
          toast('URL copied.');
        } catch {
          toast('Copy failed — long-press the field instead.', 'error');
        }
        return;
      }
      const delBtn = e.target.closest('[data-del-tag]');
      if (delBtn) {
        if (!confirm('Delete this tag? The physical tag will stop working.')) return;
        try {
          await api.del(`/api/tags/${delBtn.dataset.delTag}`);
          toast('Deleted.');
          load();
        } catch (err) {
          toast(err.message || 'Could not delete.', 'error');
        }
      }
    });

    loadTargets().then(load);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTags);
  } else {
    initTags();
  }
})();
