/* CSV import page. */
(() => {
  'use strict';

  const { $, $$, esc, fmtDate, fmtDateTime, api, toast, markdown,
            uploadFiles, wireDraft, renderStats, healthBar, plantCard } = globalThis.Verdant;

  function initImport() {
    const panel = $('#panel-import');
    if (!panel) return {};
    const entitySel = $('#import-entity');
    const fileInput = $('#import-file');
    const previewBtn = $('#import-preview-btn');
    const previewCard = $('#import-preview');
    const previewBody = $('#import-preview-body');
    const assignHost = $('#import-assign');
    const runBtn = $('#import-run-btn');
    const resultCard = $('#import-result');
    const resultBody = $('#import-result-body');
    let lastPreview = null;
    let lastEntity = null;
    let lastFile = null;

    const pill = (status) => {
      const tones = {
        new: 'bg-sage-100 text-sage-800 ring-sage-300',
        skip: 'bg-beige-200 text-navy-600 ring-beige-300',
        error: 'bg-red-100 text-red-800 ring-red-300',
        needs_plant: 'bg-amber-100 text-amber-800 ring-amber-300',
      };
      const labels = { new: 'new', skip: 'already here', error: 'problem', needs_plant: 'needs plant' };
      return `<span class="pill ring-1 ${tones[status] || tones.skip}">${labels[status] || status}</span>`;
    };

    function renderPreview(p) {
      const c = p.counts;
      let html = `<p><b>${p.total_rows}</b> rows of <b>${esc(p.entity_label)}</b>: `
        + `<span class="font-semibold text-sage-700">${c.new} new</span>, ${c.skip} already here`
        + (c.needs_plant ? `, <span class="font-semibold text-amber-700">${c.needs_plant} need a plant</span>` : '')
        + (c.error ? `, <span class="font-semibold text-red-700">${c.error} with problems</span>` : '')
        + '.</p>';
      if (p.warnings.length) {
        html += `<div class="rounded-xl border border-amber-300 bg-amber-50 p-3 text-amber-900 text-xs"><ul class="list-disc pl-5 space-y-1">`
          + p.warnings.map((w) => `<li>${esc(w)}</li>`).join('') + `</ul></div>`;
      }
      html += `<table class="w-full text-xs"><tbody>`
        + p.sample.map((r) => `<tr class="border-t border-beige-200"><td class="py-1.5 pr-2">${pill(r.status)}</td><td class="py-1.5">${esc(r.label)}</td></tr>`).join('')
        + `</tbody></table>`;
      if (p.truncated) html += `<p class="text-xs text-navy-400">Showing the first ${p.sample.length} rows.</p>`;
      previewBody.innerHTML = html;

      assignHost.classList.add('hidden');
      assignHost.innerHTML = '';
      if (p.assign_rows && p.assign_rows.length) {
        if (p.needs_plants_first) {
          assignHost.classList.remove('hidden');
          assignHost.innerHTML = `<div class="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">These harvests need plants to attach to — import your <b>Plants</b> file first, then come back.</div>`;
        } else {
          const opts = (selId) => `<option value="">— pick a plant —</option>` + p.plant_options.map((o) =>
            `<option value="${o.id}"${String(o.id) === String((p.suggested_assignments || {})[selId]) ? ' selected' : ''}>${esc(o.variety_name)} (${esc(o.plant_id)})</option>`).join('');
          assignHost.classList.remove('hidden');
          assignHost.innerHTML = `<h4 class="font-semibold text-sm">Which plant was harvested?</h4>` + p.assign_rows.map((r) =>
            `<label class="block text-sm"><span class="text-navy-600">${esc(r.label)}</span>`
            + `<select class="inp mt-1" data-assign="${esc(r.key)}">${opts(r.key)}</select></label>`).join('');
        }
      }
      runBtn.textContent = `⬇ Import ${c.new} row${c.new === 1 ? '' : 's'}`;
      runBtn.disabled = c.new === 0;
    }

    previewBtn.addEventListener('click', async () => {
      const file = fileInput.files[0];
      if (!file) { toast('Choose a CSV file first.', 'err'); return; }
      previewBtn.disabled = true;
      previewBtn.textContent = 'Reading…';
      try {
        const form = new FormData();
        form.append('entity', entitySel.value);
        form.append('file', file);
        lastPreview = await api.upload('/api/import/preview', form);
        lastEntity = entitySel.value;
        lastFile = file;
        renderPreview(lastPreview);
        previewCard.classList.remove('hidden');
        resultCard.classList.add('hidden');
      } catch (error) {
        toast(error.message, 'err');
      } finally {
        previewBtn.disabled = false;
        previewBtn.textContent = '👁 Preview';
      }
    });

    runBtn.addEventListener('click', async () => {
      if (!lastPreview || !lastFile) return;
      const assignments = {};
      $$('#import-assign [data-assign]').forEach((sel) => {
        if (sel.value) assignments[sel.dataset.assign] = parseInt(sel.value, 10);
      });
      runBtn.disabled = true;
      runBtn.textContent = 'Importing…';
      try {
        const form = new FormData();
        form.append('entity', lastEntity);
        form.append('file', lastFile);
        form.append('assignments', JSON.stringify(assignments));
        const res = await api.upload('/api/import/run', form);
        resultCard.classList.remove('hidden');
        const bits = [`<b>${res.imported}</b> imported`, `${res.skipped} skipped`];
        let html = `<p>${bits.join(' · ')}.</p>`;
        if (res.errors.length) {
          html += `<div class="mt-2 rounded-xl border border-red-300 bg-red-50 p-3 text-red-800 text-xs"><ul class="list-disc pl-5 space-y-1">`
            + res.errors.map((e) => `<li>${esc(e)}</li>`).join('') + `</ul></div>`;
        }
        if (res.warnings.length) {
          html += `<div class="mt-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-amber-900 text-xs"><ul class="list-disc pl-5 space-y-1">`
            + res.warnings.map((w) => `<li>${esc(w)}</li>`).join('') + `</ul></div>`;
        }
        resultBody.innerHTML = html;
        toast(`Import done: ${res.imported} new, ${res.skipped} skipped.`, 'ok');
        previewCard.classList.add('hidden');
      } catch (error) {
        toast(error.message, 'err');
      } finally {
        runBtn.disabled = false;
      }
    });
    return {};
  }

  globalThis.Verdant.onBoot(initImport);
})();
