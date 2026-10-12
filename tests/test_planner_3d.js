/* Planner 3D / new-kind checks: arch + pallet cards render their icons,
 * and the 3D toggle degrades gracefully when the Three.js CDN can't load
 * (node has no document.head, so the script load must fail cleanly).
 */
'use strict';
const fs = require('fs');
const path = require('path');

let failures = 0;
function check(name, ok) {
  if (!ok) { failures += 1; console.error(`FAIL: ${name}`); }
  else { console.log(`ok: ${name}`); }
}

function makeEl() {
  const classes = new Set();
  const listeners = {};
  const children = [];
  const el = {
    style: {},
    dataset: {},
    _attrs: {},
    _listeners: listeners,
    _children: children,
    checked: false,
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)),
      remove: (...c) => c.forEach((x) => classes.delete(x)),
      contains: (c) => classes.has(c),
      toggle: (c, force) => { const on = force !== undefined ? force : !classes.has(c); on ? classes.add(c) : classes.delete(c); return on; },
    },
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    removeEventListener: () => {},
    setPointerCapture: () => {},
    focus: () => {},
    setAttribute: (k, v) => { el._attrs[k] = v; },
    getAttribute: (k) => (k in el._attrs ? el._attrs[k] : null),
    querySelector: (sel) => named[sel] || makeEl(),
    querySelectorAll: () => [],
    appendChild: (c) => { children.push(c); return c; },
    append: () => {},
    getBoundingClientRect: () => ({ width: 800, height: 500, left: 0, top: 0 }),
    textContent: '',
    value: '',
  };
  let html = '';
  Object.defineProperty(el, 'innerHTML', { get: () => html, set: (v) => { html = String(v); } });
  return el;
}

const named = {};
['panel-planner', 'planner-canvas', 'planner-3d', 'planner-empty',
 'planner-2d-hint', 'planner-3d-hint',
 'view-2d', 'view-3d',
 'planner-year', 'planner-copy', 'planner-add',
 'grid-cols', 'grid-rows', 'grid-apply',
 'rotation-banner', 'rotation-list', 'rotation-dismiss',
 'container-modal', 'container-modal-title', 'container-submit',
 'container-delete', 'container-id', 'container-name', 'container-kind',
 'container-grid-w', 'container-grid-h',
 'container-size', 'container-height', 'container-volume-value', 'container-volume-unit',
 'container-location', 'container-plantings',
 'container-plant-add', 'container-plant-add-btn', 'container-soil',
 'container-close', 'container-cancel', 'container-form',
 'copy-modal', 'copy-from', 'copy-to-label', 'copy-go', 'copy-cancel',
 'toasts', 'app-version',
].forEach((id) => { named[`#${id}`] = makeEl(); });
// mirror the template's initial classes: 3D view starts hidden
named['#planner-3d'].classList.add('hidden');
named['#planner-3d-hint'].classList.add('hidden');

global.document = {
  readyState: 'complete',
  querySelector: (sel) => named[sel] || makeEl(),
  querySelectorAll: () => [],
  addEventListener: () => {},
  createElement: () => makeEl(),
  documentElement: makeEl(),
  body: makeEl(),
};
global.window = { location: { pathname: '/planner', origin: 'http://localhost:3119' }, addEventListener: () => {}, confirm: () => true };
global.confirm = () => true;
global.location = { search: '', origin: 'http://localhost:3119' };

const seenToasts = [];
global.fetch = async (url, options) => {
  const method = (options && options.method) || 'GET';
  let resp = {};
  if (url === '/api/containers/grid') resp = { cols: 24, rows: 16 };
  else if (url.startsWith('/api/containers/plantings')) resp = [
    { id: 31, container_id: 12, plant_id: 5, variety_name: 'Kentucky Wonder', season_year: 2026, slot: 0, notes: '' },
  ];
  else if (url.startsWith('/api/containers/rotation-warnings')) resp = [];
  else if (url === '/api/containers/years') resp = [2026];
  else if (url === '/api/plants/') resp = [{ id: 5, variety_name: 'Kentucky Wonder' }];
  else if (url === '/api/locations/') resp = [];
  else if (url.startsWith('/api/containers/') && url.includes('year=')) resp = [
    { id: 12, name: 'Bean Arch', kind: 'arch', grid_x: 2, grid_y: 2, grid_w: 4, grid_h: 4, season_year: 2026 },
    { id: 13, name: 'Pallet Bin', kind: 'pallet', grid_x: 8, grid_y: 2, grid_w: 4, grid_h: 3, season_year: 2026 },
  ];
  else if (method !== 'GET') resp = { id: 99 };
  return { ok: true, status: 200, json: async () => resp };
};

globalThis.Verdant = {
  $: (sel) => named[sel] || makeEl(),
  $$: () => [],
  esc: (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
  api: {
    get: (p) => fetch(p).then((r) => r.json()),
    post: (p, j) => fetch(p, { method: 'POST', body: JSON.stringify(j) }).then((r) => r.json()),
    patch: (p, j) => fetch(p, { method: 'PATCH', body: JSON.stringify(j) }).then((r) => r.json()),
    del: (p) => fetch(p, { method: 'DELETE' }).then((r) => r.json()),
  },
  toast: (m) => seenToasts.push(String(m)),
  year: () => 2026,
  setYear: () => {},
};

const tick = (ms) => new Promise((r) => setTimeout(r, ms));
const fire = (el, type, ev) => (el._listeners[type] || []).forEach((fn) => fn(ev || { preventDefault: () => {} }));

(async () => {
  require(path.join(__dirname, '..', 'app/static/js/planner.js'));
  await tick(50);

  const canvas = named['#planner-canvas'];
  const archCard = canvas._children.find((c) => c.dataset && c.dataset.containerId === 12);
  const palletCard = canvas._children.find((c) => c.dataset && c.dataset.containerId === 13);
  check('arch card rendered', !!archCard);
  check('arch card shows bridge icon', archCard && archCard.innerHTML.includes('🌉'));
  check('arch card spans 4x4 cells', archCard && archCard.style.gridColumn === '3 / span 4' && archCard.style.gridRow === '3 / span 4');
  check('pallet card rendered', !!palletCard);
  check('pallet card shows wood icon', palletCard && palletCard.innerHTML.includes('🪵'));
  check('arch card shows its plant', archCard && archCard.innerHTML.includes('Kentucky Wonder'));

  // modal: arch kind pre-fills 4x4 footprint and 7 ft height
  fire(named['#planner-add'], 'click');
  check('new modal height blank for grow bag', named['#container-height'].value === '');
  named['#container-kind'].value = 'arch';
  fire(named['#container-kind'], 'change', { target: named['#container-kind'] });
  check('arch kind pre-fills 4x4 footprint', named['#container-grid-w'].value === 4 && named['#container-grid-h'].value === 4);
  check('arch kind pre-fills 7 ft height', named['#container-height'].value === 7);

  // view toggle exists, starts in 2D
  check('2D button active initially', named['#view-2d'].className.includes('bg-sage-200'));
  check('3D container hidden initially', named['#planner-3d'].classList.contains('hidden'));

  // 3D toggle with no CDN available: must toast and stay in 2D, not throw
  fire(named['#view-3d'], 'click');
  await tick(50);
  check('3D load failure toasts', seenToasts.some((t) => t.includes('Could not load the 3D library')));
  check('stays in 2D after 3D failure', !named['#planner-canvas'].classList.contains('hidden'));
  check('3D container still hidden after failure', named['#planner-3d'].classList.contains('hidden'));

  // ---- Minecraft voxel edition: pixel painters, seeded PRNG, walk physics ----
  const walkApi = named['#planner-3d']._walk;
  check('walk test handle exposed', !!walkApi);

  // mulberry32 determinism
  const r1 = walkApi.mulberry32(42), r2 = walkApi.mulberry32(42), r3 = walkApi.mulberry32(7);
  check('mulberry32 deterministic', r1() === r2() && r1() === r2());
  check('mulberry32 seed-sensitive', r1() !== r3());

  // plant archetype mapping
  const arch = walkApi.plantArchetype;
  check('tomato archetype', arch('Tomato') === 'tomato');
  check('pepper archetype', arch('Pepper') === 'pepper' && arch('Sweet Pepper') === 'pepper');
  check('leafy archetype', arch('Genovese Basil') === 'leafy' && arch('Lettuce') === 'leafy');
  check('vine archetype', arch('Cucumber') === 'vine' && arch('Bean') === 'vine');
  check('flower archetype', arch('Marigold') === 'flower');
  check('generic fallback', arch('Mystery Plant') === 'generic' && arch('') === 'generic' && arch(null) === 'generic');

  // pixel painters run on a stub ctx
  const paintCalls = [];
  const stubCtx = { fillStyle: '', fillRect: (x, y, w, h) => paintCalls.push([x, y, w, h, stubCtx.fillStyle]) };
  const rng = walkApi.mulberry32(5);
  Object.entries(walkApi.painters).forEach(([name, fn]) => {
    if (name === 'SPRITES' || name === 'paintSprite') return;
    paintCalls.length = 0;
    fn(stubCtx, 16, rng);
    check(`painter ${name} paints pixels`, paintCalls.length > 10);
  });
  paintCalls.length = 0;
  walkApi.painters.paintSprite(stubCtx, 'tomato');
  check('tomato sprite paints pixels', paintCalls.length > 20);
  check('all 6 sprites defined', ['tomato', 'pepper', 'leafy', 'vine', 'flower', 'generic'].every((k) => Array.isArray(walkApi.painters.SPRITES[k])));

  // makePixTexture sets NearestFilter (crisp pixels) with a stub THREE
  const THREEStub = {
    NearestFilter: 1003, NearestMipmapLinearFilter: 1004, LinearFilter: 1005,
    sRGBEncoding: 3001, RepeatWrapping: 1000,
    CanvasTexture: function (cv) {
      this.image = cv;
      this.repeat = { x: 0, y: 0, set: function (x, y) { this.x = x; this.y = y; } };
    },
  };
  const origCreate = global.document.createElement;
  global.document.createElement = () => ({ width: 0, height: 0, getContext: () => stubCtx });
  const tex = walkApi.makePixTexture(THREEStub, 16, walkApi.painters.paintGrassTop, 11, [4, 4]);
  global.document.createElement = origCreate;
  check('pixel texture uses NearestFilter', tex.magFilter === 1003);
  check('pixel texture repeats', tex.wrapS === 1000 && tex.repeat.x === 4 && tex.repeat.y === 4);

  // AABB collision math
  const box1 = { minX: -1, maxX: 1, minZ: -1, maxZ: 1 };
  let res = walkApi.resolvePlayerCollision(0, 0, [box1], 0.35);
  check('center-inside pushes out on -x (tie)', res.x === -1.35 && res.z === 0);
  res = walkApi.resolvePlayerCollision(0.9, 0, [box1], 0.35);
  check('edge overlap pushes radially out', Math.abs(res.x - 1.35) < 1e-9 && res.z === 0);
  res = walkApi.resolvePlayerCollision(5, 5, [box1], 0.35);
  check('clear of box unchanged', res.x === 5 && res.z === 5);
  res = walkApi.resolvePlayerCollision(100, -100, [], 0.35);
  check('world bounds clamp', res.x === 15.5 && res.z === -11.5); // cols 24, rows 16
  // arch (id 12) excluded from colliders, pallet (id 13) included
  const colliders = walkApi.walkColliders();
  check('arch excluded from colliders', colliders.length === 1);

  // walk loop start/stop with stubbed rAF
  const frames = [];
  global.requestAnimationFrame = (fn) => { frames.push(fn); return 7; };
  walkApi._set({ locked: true, loopId: 0, keys: { KeyW: true }, last: 0, x: 0, z: 0, yaw: 0 });
  walkApi._setMode(true);
  walkApi._startLoop();
  check('walk loop starts (rAF scheduled)', frames.length === 1 && walkApi._get().loopId === 7);
  walkApi._tick(16);
  check('WASD moves player forward (-z at yaw 0)', walkApi._get().z < 0);
  walkApi._setMode(false);
  const kept = walkApi._tick(32);
  check('walk loop stops when mode exits', kept === false && walkApi._get().loopId === 0);
  delete global.requestAnimationFrame;

  // ---- build mode (Minecraft creative): pure helpers + hotbar ----
  const buildApi = named['#planner-3d']._build;
  check('build test handle exposed', !!buildApi);

  // cellFromWorld: inverse of container placement (wx = gx + w/2 - cols/2); cols 24, rows 16
  let cell = buildApi.cellFromWorld(0, 0, 24, 16);
  check('cellFromWorld center', cell.gx === 12 && cell.gy === 8);
  cell = buildApi.cellFromWorld(-12, -8, 24, 16);
  check('cellFromWorld corner', cell.gx === 0 && cell.gy === 0);
  cell = buildApi.cellFromWorld(11.9, 7.9, 24, 16);
  check('cellFromWorld edge floors', cell.gx === 23 && cell.gy === 15);

  // rectsOverlap
  check('rects overlap', buildApi.rectsOverlap(0, 0, 2, 2, 1, 1, 2, 2) === true);
  check('rects touching edges do not overlap', buildApi.rectsOverlap(0, 0, 2, 2, 2, 0, 2, 2) === false);
  check('rects disjoint', buildApi.rectsOverlap(0, 0, 1, 1, 5, 5, 1, 1) === false);

  // cellFree against the stub containers: id 12 arch at (2,2,4,4), id 13 pallet at (8,2,4,3)
  const clist = [
    { id: 12, grid_x: 2, grid_y: 2, grid_w: 4, grid_h: 4 },
    { id: 13, grid_x: 8, grid_y: 2, grid_w: 4, grid_h: 3 },
  ];
  check('cellFree empty spot', buildApi.cellFree(0, 0, 1, 1, clist, 24, 16, null) === true);
  check('cellFree inside container blocked', buildApi.cellFree(3, 3, 1, 1, clist, 24, 16, null) === false);
  check('cellFree overlapping edge blocked', buildApi.cellFree(5, 3, 2, 2, clist, 24, 16, null) === false);
  check('cellFree out of bounds rejected', buildApi.cellFree(-1, 0, 1, 1, clist, 24, 16, null) === false);
  check('cellFree past grid edge rejected', buildApi.cellFree(24, 0, 1, 1, clist, 24, 16, null) === false);
  check('cellFree ignoreId skips self', buildApi.cellFree(3, 3, 1, 1, clist, 24, 16, 12) === true);
  check('cellFree ignoreId still blocked by others', buildApi.cellFree(9, 3, 1, 1, clist, 24, 16, 12) === false);

  // hotbar tabs / selection
  check('hotbar starts on blocks tab', buildApi.tab === 'blocks' && buildApi.buildSlots().length === 7);
  buildApi.buildSelect(2);
  check('buildSelect sets index', buildApi.index === 2 && buildApi.buildSelected().key === 'pot');
  buildApi.buildCycle(1);
  check('buildCycle forward', buildApi.index === 3);
  buildApi.buildCycle(-1);
  check('buildCycle backward', buildApi.index === 2);
  buildApi.buildSelect(6);
  buildApi.buildCycle(1);
  check('buildCycle wraps around', buildApi.index === 0);
  buildApi.buildToggleTab();
  check('Q toggles to plants tab', buildApi.tab === 'plants' && buildApi.index === 0 && buildApi.buildSlots().length === 6);
  check('plants tab first slot is tomato', buildApi.buildSelected().key === 'tomato');
  buildApi.buildToggleTab();
  check('Q toggles back to blocks', buildApi.tab === 'blocks' && buildApi.index === 0);
  const hb = buildApi._hotbar();
  const hbSlotsHtml = hb._children[1].innerHTML;
  check('hotbar renders block slots', hbSlotsHtml.includes('🟫') && hbSlotsHtml.includes('∞'));
  buildApi._setTab('plants');
  check('hotbar renders plant slots', hb._children[1].innerHTML.includes('🍅'));
  buildApi._setTab('blocks');

  // nextContainerName avoids clashes (stub containers: 'Bean Arch', 'Pallet Bin')
  check('nextContainerName no clash', buildApi.nextContainerName('raised bed') === 'Raised Bed 1');

  // needsBreakConfirm: stub planting id 31 sits in container 12
  check('break confirm when plantings exist', buildApi.needsBreakConfirm({ id: 12 }) === true);
  check('no confirm when empty', buildApi.needsBreakConfirm({ id: 13 }) === false);

  // ---- cattle-panel arch geometry (pure helpers) ----
  const ribCells = walkApi.archRibCells(4, 7);
  check('arch ribs are stepped arcs (many voxel segments)', ribCells.length > 20);
  const crown = walkApi.archArcPoint(4, 7, 0.5);
  check('arch crown height ≈ 7 ft', Math.abs(crown.y - 7) < 1e-9 && Math.abs(crown.x) < 1e-9);
  const footL = walkApi.archArcPoint(4, 7, 0), footR = walkApi.archArcPoint(4, 7, 1);
  check('arch feet at ground level, span ±2', Math.abs(footL.y) < 1e-9 && Math.abs(footR.y) < 1e-9 && Math.abs(Math.abs(footL.x) - 2) < 1e-9);
  check('arch rib count 5-7 for a 4-ft run', walkApi.archRibCount(4) >= 5 && walkApi.archRibCount(4) <= 7);
  check('arch rib count caps at 7', walkApi.archRibCount(20) === 7);
  // every rib voxel sits on the true arc (stepped, not floating)
  let worstGap = 0;
  ribCells.forEach((c) => {
    let best = 1e9;
    for (let i = 0; i <= 60; i++) {
      const p = walkApi.archArcPoint(4, 7, i / 60);
      const d = Math.hypot(c.x - p.x, c.y - p.y);
      if (d < best) best = d;
    }
    if (best > worstGap) worstGap = best;
  });
  check('rib voxels hug the arc (worst gap < 0.3)', worstGap < 0.3);
  // vine blobs sit ON the rib: small outward offset, never floating nearby
  let vineOk = true;
  for (let i = 0; i <= 20; i++) {
    const p = walkApi.archArcPoint(4, 7, 0.05 + 0.9 * (i / 20));
    const vo = walkApi.archVineOffset(4, 7, p);
    if (Math.abs(Math.hypot(vo.x, vo.y) - 0.16) > 1e-9) vineOk = false;
  }
  check('vine blobs hug the rib (0.16 outward offset)', vineOk);

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
