/* Vendors tab on the Seeds page — a read-only directory of every place
   seeds came from, derived from the seed stash (plus any legacy seed-source
   entries not yet moved into the stash). To add seeds, add a packet on the
   🌱 My seed stash tab. */
(() => {
  'use strict';

  const { $, esc, api, toast } = globalThis.Verdant;

  function initSeedSources() {
    const host = $('#seed-groups');
    if (!host) return {};

    async function load() {
      let packets = [];
      let sources = [];
      try {
        [packets, sources] = await Promise.all([
          api.get('/api/seed-packets/').catch(() => []),
          api.get('/api/seed-sources/').catch(() => []),
        ]);
      } catch (error) {
        toast(`Could not load vendors: ${error.message}`, 'err');
        return;
      }
      if (!Array.isArray(packets)) packets = [];
      if (!Array.isArray(sources)) sources = [];

      const vendors = new Map();
      const add = (name) => {
        name = (name || '').trim();
        if (!name || vendors.has(name)) return vendors.get(name);
        const v = { name, packets: 0, years: new Set(), url: '' };
        vendors.set(name, v);
        return v;
      };
      packets.forEach((p) => {
        const v = add(p.vendor_name);
        if (!v) return;
        v.packets += 1;
        if (p.year_acquired) v.years.add(p.year_acquired);
        if (!v.url && p.vendor_url) v.url = p.vendor_url;
      });
      // Legacy seed-source rows not yet moved into the stash still count.
      sources.forEach((s) => { add(s.source); });

      const list = [...vendors.values()].sort((a, b) =>
        a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
      $('#seeds-empty').classList.toggle('hidden', list.length > 0);
      host.innerHTML = list.map((v) => {
        const years = [...v.years].sort();
        const yearLabel = years.length
          ? ` · ${years[0]}${years.length > 1 ? `–${years[years.length - 1]}` : ''}` : '';
        return `
        <div class="card flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 class="font-display text-lg font-semibold text-navy-800">🏪 ${esc(v.name)}</h3>
            <p class="text-sm text-navy-500">${v.packets} packet${v.packets === 1 ? '' : 's'} in the stash${yearLabel}</p>
          </div>
          <div class="flex gap-2">
            ${v.url ? `<a href="${esc(v.url)}" target="_blank" rel="noopener" class="btn-ghost text-xs">Visit ↗</a>` : ''}
            <button type="button" class="btn-ghost text-xs" data-vendor-stash="${esc(v.name)}">View in stash →</button>
          </div>
        </div>`;
      }).join('');
    }

    host.addEventListener('click', (event) => {
      const btn = event.target.closest('[data-vendor-stash]');
      if (!btn) return;
      const search = $('#catalog-search');
      if (search) {
        search.value = btn.dataset.vendorStash;
        search.dispatchEvent(new Event('input', { bubbles: true }));
      }
      const tab = $('#seed-tabbtn-catalog');
      if (tab) tab.click();
    });

    load();
    return {};
  }

  globalThis.Verdant.onBoot(initSeedSources);
})();
