/* Winter seed-order assistant tab on the Seeds page.
   Ratings table (grow again?), last-year spend by vendor, and the wishlist. */
(() => {
  'use strict';

  const { $, esc, api, toast, fmtDate } = globalThis.Verdant;

  const RATINGS = [
    { value: 'no', label: '👎 Skip' },
    { value: 'yes', label: '👍 Grow again' },
    { value: 'favorite', label: '⭐ Favorite' },
  ];
  const RATING_LABEL = Object.fromEntries(RATINGS.map((r) => [r.value, r.label]));

  function initOrderAssistant() {
    const host = $('#seed-tab-assistant');
    if (!host) return {};
    let data = null;

    const stashAge = (p) => {
      if (!p.year_acquired) return '<span class="text-navy-300">—</span>';
      const yrs = p.stash_age_years;
      const age = yrs === 0 ? 'this year' : `${yrs} yr${yrs === 1 ? '' : 's'} old`;
      return `bought ${p.year_acquired} · ${age}`;
    };
    const lastOrder = (lo) => {
      if (!lo || !lo.order_date) return '<span class="text-navy-300">—</span>';
      return `${esc(lo.vendor || 'Unknown vendor')} · ${fmtDate(lo.order_date)}`;
    };
    const money = (n) => `$${Number(n || 0).toFixed(2)}`;

    function renderSpend() {
      const rows = data.vendor_spend || [];
      $('#oa-spend-year').textContent = data.last_year;
      $('#oa-spend-empty').classList.toggle('hidden', rows.length > 0);
      $('#oa-spend').innerHTML = rows.map((r) => `
        <div class="rounded-xl bg-beige-50 px-4 py-3 ring-1 ring-beige-200">
          <p class="font-semibold text-navy-800">${esc(r.vendor)}</p>
          <p class="text-sm text-navy-600">${money(r.total)} <span class="text-navy-400">· ${r.orders} order${r.orders === 1 ? '' : 's'}</span></p>
        </div>`).join('');
    }

    function ratingButtons(p) {
      return RATINGS.map((r) => {
        const active = p.grow_again === r.value;
        return `<button type="button" data-oa-rate="${r.value}" data-packet="${p.id}" title="${esc(r.label)}"
          class="rounded-lg px-2 py-1 text-sm ring-1 ${active ? 'bg-sage-600 text-beige-50 ring-sage-600' : 'bg-beige-50 text-navy-600 ring-beige-200 hover:ring-sage-400'}">${esc(r.label)}</button>`;
      }).join(' ');
    }

    function renderRatings() {
      const rows = data.packets || [];
      $('#oa-ratings-empty').classList.toggle('hidden', rows.length > 0);
      $('#oa-ratings').innerHTML = rows.map((p) => `
        <tr class="border-t border-beige-200 align-top">
          <td class="py-2 pr-3">
            <p class="font-semibold text-navy-800">${esc(p.variety_name)}</p>
            ${p.category ? `<p class="text-xs text-navy-400">${esc(p.category)}</p>` : ''}
          </td>
          <td class="py-2 pr-3 text-sm text-navy-600">${stashAge(p)}</td>
          <td class="py-2 pr-3 text-sm text-navy-600">${lastOrder(p.last_order)}</td>
          <td class="py-2 pr-3"><div class="flex flex-wrap gap-1">${ratingButtons(p)}</div></td>
          <td class="py-2 text-right">
            <button type="button" data-oa-to-wish="${p.id}" class="text-xs text-sage-700 underline" title="Copy to the wishlist below">+ wishlist</button>
          </td>
        </tr>`).join('');
    }

    function renderWishlist() {
      const rows = data.wishlist || [];
      $('#oa-wishlist-empty').classList.toggle('hidden', rows.length > 0);
      $('#oa-wishlist').innerHTML = rows.map((w) => `
        <div class="flex items-start gap-3 rounded-xl bg-beige-50 p-3 ring-1 ring-beige-200">
          <input type="checkbox" data-oa-check="${w.id}" ${w.checked ? 'checked' : ''} class="mt-1 h-5 w-5 shrink-0 accent-sage-600" aria-label="Order ${esc(w.variety_name)}" />
          <div class="min-w-0 flex-1">
            <p class="font-semibold text-navy-800 ${w.checked ? '' : ''}">${esc(w.variety_name)}</p>
            <p class="text-xs text-navy-500">${w.vendor_name ? `${esc(w.vendor_name)} · ` : ''}last ordered: ${lastOrder(w.last_order)}</p>
            ${w.notes ? `<p class="mt-0.5 text-xs text-navy-500">${esc(w.notes)}</p>` : ''}
          </div>
          <button type="button" data-oa-wdel="${w.id}" class="shrink-0 text-xs text-red-700 underline">delete</button>
        </div>`).join('');
      const checked = rows.filter((w) => w.checked);
      const list = $('#oa-order-list');
      list.classList.toggle('hidden', checked.length === 0);
      if (checked.length) {
        list.innerHTML = `🧾 <strong>Order list (${checked.length}):</strong> ` +
          checked.map((w) => esc(w.variety_name) + (w.vendor_name ? ` <span class="text-sage-600">(${esc(w.vendor_name)})</span>` : '')).join(' · ');
      }
    }

    async function load() {
      try {
        data = await api.get('/api/order-assistant/');
      } catch (err) {
        toast(err.message || 'Could not load the order assistant.', 'error');
        return;
      }
      renderSpend();
      renderRatings();
      renderWishlist();
    }

    async function setRating(packetId, value) {
      const packet = (data.packets || []).find((p) => p.id === packetId);
      const next = packet && packet.grow_again === value ? '' : value; // tap again to clear
      try {
        await api.patch(`/api/seed-packets/${packetId}`, { grow_again: next });
        if (packet) packet.grow_again = next;
        renderRatings();
      } catch (err) {
        toast(err.message || 'Could not save rating.', 'error');
      }
    }

    host.addEventListener('click', async (event) => {
      const rateBtn = event.target.closest('[data-oa-rate]');
      if (rateBtn) {
        await setRating(Number(rateBtn.dataset.packet), rateBtn.dataset.oaRate);
        return;
      }
      const wishBtn = event.target.closest('[data-oa-to-wish]');
      if (wishBtn) {
        const p = (data.packets || []).find((x) => x.id === Number(wishBtn.dataset.oaToWish));
        if (p) {
          $('#oa-wish-variety').value = p.variety_name || '';
          $('#oa-wish-vendor').value = (p.last_order && p.last_order.vendor) || p.vendor_name || '';
          $('#oa-wish-variety').focus();
          $('#oa-wish-form').scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
      }
      const delBtn = event.target.closest('[data-oa-wdel]');
      if (delBtn) {
        const w = (data.wishlist || []).find((x) => x.id === Number(delBtn.dataset.oaWdel));
        if (!w || !confirm(`Remove "${w.variety_name}" from the wishlist?`)) return;
        try {
          await api.del(`/api/wishlist/${w.id}`);
          data.wishlist = data.wishlist.filter((x) => x.id !== w.id);
          renderWishlist();
        } catch (err) {
          toast(err.message || 'Could not delete.', 'error');
        }
      }
    });

    host.addEventListener('change', async (event) => {
      const box = event.target.closest('[data-oa-check]');
      if (!box) return;
      const id = Number(box.dataset.oaCheck);
      try {
        await api.patch(`/api/wishlist/${id}`, { checked: box.checked });
        const w = (data.wishlist || []).find((x) => x.id === id);
        if (w) w.checked = box.checked;
        renderWishlist();
      } catch (err) {
        box.checked = !box.checked;
        toast(err.message || 'Could not save.', 'error');
      }
    });

    $('#oa-wish-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const variety = $('#oa-wish-variety').value.trim();
      if (!variety) {
        toast('Variety is required.', 'error');
        return;
      }
      try {
        const created = await api.post('/api/wishlist/', {
          variety_name: variety,
          vendor_name: $('#oa-wish-vendor').value.trim(),
          notes: $('#oa-wish-notes').value.trim(),
        });
        // The fresh row has no invoice history yet — reload for last-vendor/date.
        await load();
        $('#oa-wish-variety').value = '';
        $('#oa-wish-vendor').value = '';
        $('#oa-wish-notes').value = '';
        toast(`"${created.variety_name}" added to the wishlist.`);
      } catch (err) {
        toast(err.message || 'Could not add.', 'error');
      }
    });

    $('#seed-tabbtn-assistant').addEventListener('click', load);

    load();
    return {};
  }

  globalThis.Verdant.onBoot(initOrderAssistant);
})();
