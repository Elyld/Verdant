/* Backyard planner — drag-and-drop container layout per season. */
(() => {
  'use strict';

  const { $, $$, esc, api, toast } = globalThis.Verdant;

  const KIND_ICON = { 'grow bag': '🛍️', 'raised bed': '🟫', 'pot': '🪴', 'planter': '🗄️' };
  const KIND_TONE = {
    'grow bag': 'bg-sage-100 ring-sage-300',
    'raised bed': 'bg-amber-100 ring-amber-300',
    'pot': 'bg-sky-100 ring-sky-300',
    'planter': 'bg-orange-100 ring-orange-300',
  };

  function initPlanner() {
    const canvas = $('#planner-canvas');
    if (!canvas) return;

    let containers = [];
    let plants = [];
    let locations = [];
    let years = [];
    let year = new Date().getFullYear();
    let drag = null;

    const plantName = (id) => (plants.find((p) => p.id === id) || {}).variety_name || '';

    function card(c) {
      const el = document.createElement('button');
      el.type = 'button';
      el.className = `absolute flex w-28 -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-0.5 rounded-xl px-2 py-2 text-center shadow ring-2 ${KIND_TONE[c.kind] || KIND_TONE['grow bag']}`;
      el.style.left = `${c.x}%`;
      el.style.top = `${c.y}%`;
      el.dataset.containerId = c.id;
      el.innerHTML = `
        <span class="text-2xl leading-none">${KIND_ICON[c.kind] || '🛍️'}</span>
        <span class="w-full truncate text-xs font-semibold text-navy-800">${esc(c.name)}</span>
        ${c.size ? `<span class="text-[10px] text-navy-500">${esc(c.size)}</span>` : (c.volume_value ? `<span class="text-[10px] text-navy-500">${esc(String(c.volume_value))} ${esc(c.volume_unit || '')}</span>` : '')}
        <span class="w-full truncate text-[10px] ${c.plant_id ? 'font-semibold text-sage-700' : 'text-navy-400'}">${c.plant_id ? esc(plantName(c.plant_id)) : 'empty'}</span>`;
      el.addEventListener('pointerdown', (e) => startDrag(e, c, el));
      el.addEventListener('click', () => { if (!dragMoved) openModal(c); });
      return el;
    }

    let dragMoved = false;
    function startDrag(e, c, el) {
      e.preventDefault();
      dragMoved = false;
      const rect = canvas.getBoundingClientRect();
      const startX = e.clientX, startY = e.clientY;
      const origX = c.x, origY = c.y;
      el.setPointerCapture(e.pointerId);
      const move = (ev) => {
        const dx = ((ev.clientX - startX) / rect.width) * 100;
        const dy = ((ev.clientY - startY) / rect.height) * 100;
        if (Math.abs(dx) + Math.abs(dy) > 0.5) dragMoved = true;
        c.x = Math.min(97, Math.max(3, origX + dx));
        c.y = Math.min(94, Math.max(6, origY + dy));
        el.style.left = `${c.x}%`;
        el.style.top = `${c.y}%`;
      };
      const up = () => {
        el.removeEventListener('pointermove', move);
        el.removeEventListener('pointerup', up);
        el.removeEventListener('pointercancel', up);
        if (dragMoved) {
          api.patch(`/api/containers/${c.id}`, { x: Math.round(c.x * 10) / 10, y: Math.round(c.y * 10) / 10 })
            .catch(() => toast('Could not save position.', 'error'));
        }
        drag = null;
        setTimeout(() => { dragMoved = false; }, 0);
      };
      el.addEventListener('pointermove', move);
      el.addEventListener('pointerup', up);
      el.addEventListener('pointercancel', up);
      drag = { el };
    }

    function render() {
      canvas.querySelectorAll('[data-container-id]').forEach((n) => n.remove());
      const empty = $('#planner-empty');
      empty.classList.toggle('hidden', containers.length > 0);
      empty.classList.toggle('flex', containers.length === 0);
      containers.forEach((c) => canvas.appendChild(card(c)));
    }

    async function load() {
      const [cs, p, l, ys] = await Promise.all([
        api.get(`/api/containers/?year=${year}`).catch(() => []),
        api.get('/api/plants/').catch(() => []),
        api.get('/api/locations/').catch(() => []),
        api.get('/api/containers/years').catch(() => []),
      ]);
      containers = Array.isArray(cs) ? cs : [];
      plants = Array.isArray(p) ? p : [];
      locations = Array.isArray(l) ? l : [];
      years = Array.isArray(ys) ? ys : [];
      if (!years.includes(year)) years.push(year);
      years.sort((a, b) => b - a);
      $('#planner-year').innerHTML = years.map((y) => `<option value="${y}"${y === year ? ' selected' : ''}>${y}</option>`).join('');
      $('#copy-from').innerHTML = years.filter((y) => y !== year).map((y) => `<option value="${y}">${y}</option>`).join('');
      $('#copy-to-label').textContent = year;
      $('#container-plant').innerHTML = '<option value="">— empty —</option>' +
        plants.map((x) => `<option value="${x.id}">${esc(x.variety_name)}</option>`).join('');
      $('#container-location').innerHTML = '<option value="">— none —</option>' +
        locations.map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join('');
      render();
    }

    function openModal(c) {
      $('#container-modal-title').textContent = c ? 'Edit container' : 'Add container';
      $('#container-submit').textContent = c ? 'Save changes' : 'Add container';
      $('#container-delete').classList.toggle('hidden', !c);
      $('#container-id').value = c ? c.id : '';
      $('#container-name').value = c ? c.name : '';
      $('#container-kind').value = c ? c.kind : 'grow bag';
      $('#container-size').value = c ? (c.size || '') : '';
      $('#container-volume-value').value = c && c.volume_value != null ? c.volume_value : '';
      $('#container-volume-unit').value = c ? (c.volume_unit || '') : '';
      $('#container-location').value = c && c.location_id ? c.location_id : '';
      $('#container-plant').value = c && c.plant_id ? c.plant_id : '';
      $('#container-soil').value = c ? (c.soil_notes || '') : '';
      $('#container-modal').classList.remove('hidden');
      $('#container-modal').classList.add('flex');
      $('#container-name').focus();
    }

    function closeModal() {
      $('#container-modal').classList.add('hidden');
      $('#container-modal').classList.remove('flex');
    }

    $('#planner-add').addEventListener('click', () => openModal(null));
    $('#container-close').addEventListener('click', closeModal);
    $('#container-cancel').addEventListener('click', closeModal);
    $('#planner-year').addEventListener('change', (e) => { year = Number(e.target.value); load(); });

    $('#container-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const id = $('#container-id').value;
      const payload = {
        name: $('#container-name').value.trim(),
        kind: $('#container-kind').value,
        size: $('#container-size').value.trim(),
        volume_value: $('#container-volume-value').value ? Number($('#container-volume-value').value) : null,
        volume_unit: $('#container-volume-unit').value,
        location_id: $('#container-location').value ? Number($('#container-location').value) : null,
        plant_id: $('#container-plant').value ? Number($('#container-plant').value) : null,
        soil_notes: $('#container-soil').value.trim(),
        season_year: year,
      };
      try {
        if (id) await api.patch(`/api/containers/${id}`, payload);
        else await api.post('/api/containers/', payload);
        closeModal();
        toast(id ? 'Container updated.' : 'Container added — drag it where it really sits.');
        load();
      } catch (err) {
        toast(err.message || 'Could not save.', 'error');
      }
    });

    $('#container-delete').addEventListener('click', async () => {
      const id = $('#container-id').value;
      if (!id || !confirm('Remove this container from the plan?')) return;
      try {
        await api.del(`/api/containers/${id}`);
        closeModal();
        toast('Removed.');
        load();
      } catch (err) {
        toast(err.message || 'Could not delete.', 'error');
      }
    });

    $('#planner-copy').addEventListener('click', () => {
      if (!years.filter((y) => y !== year).length) { toast('No other season to copy from yet.', 'error'); return; }
      $('#copy-modal').classList.remove('hidden');
      $('#copy-modal').classList.add('flex');
    });
    $('#copy-cancel').addEventListener('click', () => {
      $('#copy-modal').classList.add('hidden');
      $('#copy-modal').classList.remove('flex');
    });
    $('#copy-go').addEventListener('click', async () => {
      try {
        await api.post('/api/containers/copy-season', { from_year: Number($('#copy-from').value), to_year: year });
        $('#copy-modal').classList.add('hidden');
        $('#copy-modal').classList.remove('flex');
        toast(`Copied into ${year}.`);
        load();
      } catch (err) {
        toast(err.message || 'Could not copy season.', 'error');
      }
    });

    load();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPlanner);
  } else {
    initPlanner();
  }
})();
