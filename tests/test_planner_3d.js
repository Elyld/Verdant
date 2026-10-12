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
 'view-2d', 'view-3d', 'view-walk', 'view-daynight', 'view-tape', 'view-sound',
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

  // soft painters run on a stub ctx with a full 2d API surface
  let drawCalls = 0;
  const gradStub = { addColorStop: () => {} };
  const stubCtx = {
    fillStyle: '', strokeStyle: '', lineWidth: 1, lineCap: '', globalAlpha: 1,
    fillRect: () => { drawCalls++; }, strokeRect: () => { drawCalls++; },
    beginPath: () => {}, closePath: () => {}, moveTo: () => {}, lineTo: () => {},
    quadraticCurveTo: () => {}, bezierCurveTo: () => {},
    arc: () => { drawCalls++; }, ellipse: () => { drawCalls++; },
    fill: () => { drawCalls++; }, stroke: () => { drawCalls++; },
    createLinearGradient: () => gradStub, createRadialGradient: () => gradStub,
  };
  const rng = walkApi.mulberry32(5);
  Object.entries(walkApi.painters).forEach(([name, fn]) => {
    drawCalls = 0;
    fn(stubCtx, 64, rng);
    check(`painter ${name} paints`, drawCalls > 5);
  });

  // makePixTexture sets NearestFilter (crisp pixels) with a stub THREE
  const THREEStub = {
    NearestFilter: 1003, NearestMipmapLinearFilter: 1004, LinearFilter: 1005,
    LinearMipmapLinearFilter: 1006,
    sRGBEncoding: 3001, RepeatWrapping: 1000,
    CanvasTexture: function (cv) {
      this.image = cv;
      this.repeat = { x: 0, y: 0, set: function (x, y) { this.x = x; this.y = y; } };
    },
  };
  const origCreate = global.document.createElement;
  global.document.createElement = () => ({ width: 0, height: 0, getContext: () => stubCtx });
  const tex = walkApi.makePixTexture(THREEStub, 64, walkApi.painters.paintGrass, 11, [4, 4]);
  global.document.createElement = origCreate;
  check('soft texture uses LinearFilter', tex.magFilter === 1005);
  check('soft texture is 64px', tex.image.width === 64 && tex.image.height === 64);
  check('soft texture repeats', tex.wrapS === 1000 && tex.repeat.x === 4 && tex.repeat.y === 4);

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
  check('hotbar starts on blocks tab', buildApi.tab === 'blocks' && buildApi.buildSlots().length === 22);
  buildApi.buildSelect(2);
  check('buildSelect sets index', buildApi.index === 2 && buildApi.buildSelected().key === 'pot');
  buildApi.buildCycle(1);
  check('buildCycle forward', buildApi.index === 3);
  buildApi.buildCycle(-1);
  check('buildCycle backward', buildApi.index === 2);
  buildApi.buildSelect(21);
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

  // ---- garden arch geometry (pure helpers; smooth torus ribs now) ----
  const crown = walkApi.archArcPoint(4, 7, 0.5);
  check('arch crown height ≈ 7 ft', Math.abs(crown.y - 7) < 1e-9 && Math.abs(crown.x) < 1e-9);
  const footL = walkApi.archArcPoint(4, 7, 0), footR = walkApi.archArcPoint(4, 7, 1);
  check('arch feet at ground level, span ±2', Math.abs(footL.y) < 1e-9 && Math.abs(footR.y) < 1e-9 && Math.abs(Math.abs(footL.x) - 2) < 1e-9);
  check('arch rib count 5-7 for a 4-ft run', walkApi.archRibCount(4) >= 5 && walkApi.archRibCount(4) <= 7);
  check('arch rib count caps at 7', walkApi.archRibCount(20) === 7);
  // the arc is smooth: midpoints between samples stay on the ellipse
  const arcMid = walkApi.archArcPoint(4, 7, 0.25);
  const onEllipse = Math.pow(arcMid.x / 2, 2) + Math.pow(arcMid.y / 7, 2);
  check('arch arc is a true half-ellipse', Math.abs(onEllipse - 1) < 1e-9);

  // ---- world dressing: fence auto-connect, lamp light cap, day/night ----
  // fenceSides: single fence = post only; neighbors add mesh per side
  const noFence = walkApi.fenceCells([]);
  check('lone fence has no mesh sides', Object.values(walkApi.fenceSides(5, 5, noFence)).every((v) => v === false));
  const rowCells = walkApi.fenceCells([
    { kind: 'fence', grid_x: 4, grid_y: 5, grid_w: 1, grid_h: 1 },
    { kind: 'fence', grid_x: 5, grid_y: 5, grid_w: 1, grid_h: 1 },
    { kind: 'fence', grid_x: 6, grid_y: 5, grid_w: 1, grid_h: 1 },
  ]);
  const mid = walkApi.fenceSides(5, 5, rowCells);
  check('middle of fence run meshes east+west only', mid.e === true && mid.w === true && mid.n === false && mid.s === false);
  const end = walkApi.fenceSides(4, 5, rowCells);
  check('fence run end meshes one side', end.e === true && end.w === false && end.n === false && end.s === false);
  const cornerCells = walkApi.fenceCells([
    { kind: 'fence', grid_x: 2, grid_y: 2, grid_w: 1, grid_h: 1 },
    { kind: 'fence', grid_x: 3, grid_y: 2, grid_w: 1, grid_h: 1 },
    { kind: 'fence', grid_x: 3, grid_y: 3, grid_w: 1, grid_h: 1 },
  ]);
  const corner = walkApi.fenceSides(3, 2, cornerCells);
  check('fence corner meshes two adjacent sides', corner.w === true && corner.s === true && corner.n === false && corner.e === false);
  check('non-fence kinds ignored by fenceCells', walkApi.fenceCells([{ kind: 'lamp', grid_x: 9, grid_y: 9 }]).size === 0);
  // multi-cell fence covers its full rect
  const big = walkApi.fenceCells([{ kind: 'fence', grid_x: 0, grid_y: 0, grid_w: 2, grid_h: 1 }]);
  check('resized fence covers both cells', big.has('0,0') && big.has('1,0'));

  // nearestLampIds: capped at N nearest, by squared distance
  const lamps = [{ x: 0, z: 0 }, { x: 10, z: 0 }, { x: 3, z: 4 }, { x: 1, z: 1 }];
  const near2 = walkApi.nearestLampIds(lamps, 0, 0, 2);
  check('nearest 2 lamps win the light cap', near2.length === 2 && near2[0] === 0 && near2[1] === 3);
  check('cap larger than lamp count returns all', walkApi.nearestLampIds(lamps, 0, 0, 20).length === 4);
  check('no lamps, no lights', walkApi.nearestLampIds([], 0, 0, 8).length === 0);

  // day/night toggle flips state (scene ops no-op without THREE in node)
  check('starts in day mode', walkApi.dayNight === 'day');
  walkApi._toggleDayNight();
  check('toggle flips to night', walkApi.dayNight === 'night');
  walkApi._toggleDayNight();
  check('toggle flips back to day', walkApi.dayNight === 'day');

  // hotbar grew: 16 blocks across two rows of 8, new kinds present
  const blockKeys = buildApi.buildSlots().map((s) => s.key);
  check('BLOCKS hotbar has 22 slots', blockKeys.length === 22);
  check('dressing kinds in hotbar', ['lamp', 'fence', 'bucket', 'path'].every((k) => blockKeys.includes(k)));
  check('new asset kinds in hotbar', ['rain barrel', 'compost bin', 'hoop house', 'fence gate', 'bird bath'].every((k) => blockKeys.includes(k)));
  check('graphics-batch kinds in hotbar', ['fruit tree', 'shed', 'pergola', 'stone edging', 'sprinkler', 'drip line'].every((k) => blockKeys.includes(k)));
  buildApi._setTab('blocks');
  buildApi.buildSelect(10);
  check('slot 11 selectable (wheel cycles all)', buildApi.buildSelected().key === 'path');
  buildApi.buildSelect(15);
  check('slot 16 selectable', buildApi.buildSelected().key === 'bird bath');
  buildApi.buildSelect(16);
  check('slot 17 is the fruit tree', buildApi.buildSelected().key === 'fruit tree');
  buildApi.buildSelect(21);
  check('slot 22 is the drip line', buildApi.buildSelected().key === 'drip line');
  buildApi.buildSelect(22);
  check('selection wraps past the end', buildApi.buildSelected().key === 'raised bed');
  const hbHtml = buildApi._hotbar()._children[1].innerHTML;
  check('hotbar wraps to three rows (8/8/6)', (hbHtml.match(/margin-bottom:4px/g) || []).length === 3);
  buildApi._setTab('plants');
  const plantHtml = buildApi._hotbar()._children[1].innerHTML;
  check('PLANTS tab stays one row', (plantHtml.match(/margin-bottom:4px/g) || []).length === 1);
  buildApi._setTab('blocks');

  // new soft painters registered (auto-covered by the painter loop above too)
  ['paintBarrel', 'paintCompost', 'paintHoopPlastic', 'paintBasin', 'paintGroundSide', 'paintLeaf'].forEach((n) => {
    check(`painter ${n} registered`, typeof walkApi.painters[n] === 'function');
  });
  check('voxel painters are gone', walkApi.painters.paintGrassTop === undefined &&
    walkApi.painters.paintSprite === undefined && walkApi.painters.SPRITES === undefined);

  // soft plant foliage: deterministic clusters, fruiting archetypes bear fruit
  const fol1 = walkApi.plantFoliage('tomato', 1234), fol2 = walkApi.plantFoliage('tomato', 1234);
  check('foliage deterministic (same seed)', JSON.stringify(fol1) === JSON.stringify(fol2));
  const fol3 = walkApi.plantFoliage('tomato', 999);
  check('foliage seed-sensitive', JSON.stringify(fol1) !== JSON.stringify(fol3));
  check('foliage has 2-4 blobs', fol1.blobs.length >= 2 && fol1.blobs.length <= 4);
  check('tomato bears fruit', fol1.fruits.length >= 2 && fol1.fruits.every((f) => f.c === 0xd9402e));
  const folPep = walkApi.plantFoliage('pepper', 1234);
  check('pepper bears orange fruit', folPep.fruits.length >= 2 && folPep.fruits.every((f) => f.c === 0xe08a2e));
  const folLeafy = walkApi.plantFoliage('leafy', 1234);
  check('leafy has no fruit', folLeafy.fruits.length === 0);
  const folFlower = walkApi.plantFoliage('flower', 1234);
  check('flowers bloom in pastel colors', folFlower.fruits.length >= 1 &&
    folFlower.fruits.every((f) => [0xe06ba8, 0xf2d13d, 0xf5f5f5].includes(f.c)));
  check('blobs sit above the soil', fol1.blobs.every((b) => b.dy > 0.2 && b.dy < 1.1));

  // per-kind placement footprints: hoop house is 4x8, everything else 1x1
  check('hoop house footprint 4x8', JSON.stringify(buildApi.placeFootprint('hoop house')) === '[4,8]');
  check('default footprint 1x1', JSON.stringify(buildApi.placeFootprint('rain barrel')) === '[1,1]' &&
    JSON.stringify(buildApi.placeFootprint('bogus kind')) === '[1,1]');
  check('4x8 fits on empty grid', buildApi.cellFree(0, 0, 4, 8, [], 24, 16, null) === true);
  check('4x8 blocked by overlap', buildApi.cellFree(0, 0, 4, 8,
    [{ id: 1, grid_x: 2, grid_y: 2, grid_w: 1, grid_h: 1 }], 24, 16, null) === false);
  check('4x8 blocked out of bounds', buildApi.cellFree(21, 0, 4, 8, [], 24, 16, null) === false);
  check('4x8 ignores the ignored id', buildApi.cellFree(0, 0, 4, 8,
    [{ id: 7, grid_x: 0, grid_y: 0, grid_w: 4, grid_h: 8 }], 24, 16, 7) === true);

  // fence gate joins the fence connection set, both directions
  const gateCells = walkApi.fenceCells([{ kind: 'fence gate', grid_x: 5, grid_y: 5, grid_w: 1, grid_h: 1 }]);
  check('fence gate counts as a fence cell', gateCells.has('5,5'));
  const fenceCells2 = walkApi.fenceCells([{ kind: 'fence', grid_x: 4, grid_y: 5, grid_w: 1, grid_h: 1 }]);
  const both = new Set([...fenceCells2, ...gateCells]);
  check('fence meshes toward adjacent gate', walkApi.fenceSides(4, 5, both).e === true);
  check('gate meshes toward adjacent fence', walkApi.fenceSides(5, 5, both).w === true);
  check('lone gate has no connections', Object.values(walkApi.fenceSides(9, 9, both)).every((v) => v === false));

  // measuring tape: pure distance math, 1 unit = 1 ft
  check('tape 3-4-5 triangle', walkApi.tapeDistance({ x: 0, z: 0 }, { x: 3, z: 4 }) === 5);
  check('tape zero distance', walkApi.tapeDistance({ x: 1, z: 1 }, { x: 1, z: 1 }) === 0);
  check('tape diagonal', Math.abs(walkApi.tapeDistance({ x: 0, z: 0 }, { x: 10, z: 10 }) - Math.SQRT2 * 10) < 1e-9);

  // sound synth: stubbed AudioContext, thunk + crunch run, mute respected
  const madeNodes = [];
  global.window.AudioContext = function () {
    this.currentTime = 0; this.sampleRate = 44100; this.destination = {};
    this.createOscillator = () => { const o = { type: '', frequency: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {}, start() {}, stop() {} }; madeNodes.push(o); return o; };
    this.createGain = () => { const g = { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() {} }; madeNodes.push(g); return g; };
    this.createBuffer = (ch, len) => ({ getChannelData: () => new Float32Array(len) });
    this.createBufferSource = () => { const s = { buffer: null, connect() {}, start() {} }; madeNodes.push(s); return s; };
    this.createBiquadFilter = () => ({ type: '', frequency: {}, connect() {} });
  };
  walkApi.Sound.enabled = true;
  let soundThrew = false;
  try { walkApi.Sound.thunk(); walkApi.Sound.crunch(); } catch (e) { soundThrew = true; }
  check('sound synth runs on stubbed AudioContext', !soundThrew && madeNodes.length > 0);
  const nodesBeforeMute = madeNodes.length;
  walkApi.Sound.enabled = false;
  walkApi.Sound.thunk(); walkApi.Sound.crunch();
  check('sound muted when disabled', madeNodes.length === nodesBeforeMute);
  walkApi.Sound.enabled = true;

  // break particles: spawn count + expiry, with an injected minimal THREE
  const pMeshes = [];
  const fakeTHREE = {
    BoxGeometry: function () { this.dispose = () => {}; },
    MeshBasicMaterial: function (opts) { this.opacity = 1; this.color = opts && opts.color; this.dispose = () => {}; },
    Mesh: function (geo, mat) {
      this.geometry = geo; this.material = mat;
      this.position = { x: 0, y: 0, z: 0, set() {} };
      this.rotation = { x: 0, y: 0 };
      pMeshes.push(this);
    },
  };
  walkApi._setT({ THREE: fakeTHREE, scene: { add() {}, remove() {} } });
  walkApi.spawnParticles(0, 1, 0);
  check('break spawns 12 particles', walkApi.particleCount() === 12 && pMeshes.length === 12);
  walkApi.updateParticles(1.0); // age past every particle's life
  check('particles expire and clean up', walkApi.particleCount() === 0);
  walkApi._setT(null);
  walkApi.spawnParticles(0, 1, 0);
  check('no particles without a 3D context', walkApi.particleCount() === 0);

  // ---- graphics batch: sky, grass, fireflies, new-kind connections ----
  // new pixel painters registered (auto-covered by the painter loop above too)
  ['paintLeaf', 'paintGrassTuft', 'paintWildflower'].forEach((n) => {
    check(`painter ${n} registered`, typeof walkApi.painters[n] === 'function');
  });

  // stone edging + drip line auto-connect (fenceSides pattern, own cell sets)
  const edgeRun = walkApi.edgingCells([
    { kind: 'stone edging', grid_x: 1, grid_y: 1, grid_w: 1, grid_h: 1 },
    { kind: 'stone edging', grid_x: 2, grid_y: 1, grid_w: 1, grid_h: 1 },
    { kind: 'stone edging', grid_x: 3, grid_y: 1, grid_w: 1, grid_h: 1 },
  ]);
  const edgeMid = walkApi.fenceSides(2, 1, edgeRun);
  check('edging run middle connects east+west', edgeMid.e === true && edgeMid.w === true && edgeMid.n === false && edgeMid.s === false);
  check('lone edging has no connections', Object.values(walkApi.fenceSides(9, 9, edgeRun)).every((v) => v === false));
  check('non-edging kinds ignored by edgingCells', walkApi.edgingCells([{ kind: 'fence', grid_x: 1, grid_y: 1 }]).size === 0);
  const dripRun = walkApi.dripCells([
    { kind: 'drip line', grid_x: 5, grid_y: 5, grid_w: 1, grid_h: 1 },
    { kind: 'drip line', grid_x: 5, grid_y: 6, grid_w: 1, grid_h: 1 },
  ]);
  const dripTop = walkApi.fenceSides(5, 5, dripRun);
  check('drip run connects north+south', dripTop.s === true && dripTop.n === false);
  check('edging and drip sets stay separate', walkApi.dripCells([{ kind: 'stone edging', grid_x: 1, grid_y: 1 }]).size === 0);

  // per-kind placement footprints for the new structures
  check('shed footprint 4x6', JSON.stringify(buildApi.placeFootprint('shed')) === '[4,6]');
  check('pergola footprint 2x4', JSON.stringify(buildApi.placeFootprint('pergola')) === '[2,4]');
  check('shed 4x6 fits on empty grid', buildApi.cellFree(0, 0, 4, 6, [], 24, 16, null) === true);
  check('shed 4x6 blocked out of bounds', buildApi.cellFree(21, 0, 4, 6, [], 24, 16, null) === false);

  // gradient sky palette flips with the day/night toggle
  const dayPal = walkApi.skyColors(false), nightPal = walkApi.skyColors(true);
  check('sky palette differs day vs night', dayPal.top !== nightPal.top && dayPal.horizon !== nightPal.horizon);
  check('night sky is dark', nightPal.top < 0x111111 && nightPal.horizon < 0x223355);
  check('day sky is bright blue', dayPal.top > 0x222222 && dayPal.horizon > 0x888888);

  // grass scatter: deterministic, never on occupied cells, capped, in bounds
  const occ = walkApi.occupiedCellSet([
    { id: 1, grid_x: 0, grid_y: 0, grid_w: 2, grid_h: 2 },
    { id: 2, grid_x: 5, grid_y: 5, grid_w: 1, grid_h: 1 },
  ]);
  check('occupiedCellSet covers rects', occ.has('0,0') && occ.has('1,1') && occ.has('5,5') && !occ.has('2,2'));
  const g1 = walkApi.grassLayout(24, 16, occ, 4242);
  const g2 = walkApi.grassLayout(24, 16, occ, 4242);
  check('grass layout deterministic (same seed)', JSON.stringify(g1) === JSON.stringify(g2));
  const g3 = walkApi.grassLayout(24, 16, occ, 999);
  check('grass layout seed-sensitive', JSON.stringify(g1) !== JSON.stringify(g3));
  check('grass never on occupied cells', g1.every((c) => !occ.has(`${c.gx},${c.gy}`)));
  check('grass capped for perf', g1.length <= 240 && g1.length > 50);
  check('grass cells in bounds', g1.every((c) => c.gx >= 0 && c.gy >= 0 && c.gx < 24 && c.gy < 16));
  check('grass has tufts and flowers', g1.some((c) => c.variant === 'tuft') && g1.some((c) => c.variant.startsWith('flower')));
  check('empty grid still caps grass', walkApi.grassLayout(60, 60, new Set(), 4242).length <= 240);

  // fireflies: gentle drift around their base, pure math
  const fb = { x: 1, y: 1, z: 1 };
  const fp0 = walkApi.fireflyPos(fb, 0.5, 0), fp1 = walkApi.fireflyPos(fb, 0.5, 2);
  check('firefly drifts with time', Math.abs(fp0.x - fp1.x) > 1e-6 || Math.abs(fp0.y - fp1.y) > 1e-6);
  check('firefly stays near its base', Math.abs(fp0.x - fb.x) <= 0.6 && Math.abs(fp0.y - fb.y) <= 0.35 && Math.abs(fp0.z - fb.z) <= 0.6);
  check('firefly phase matters', walkApi.fireflyPos(fb, 0, 1).x !== walkApi.fireflyPos(fb, 2, 1).x);

  console.log(failures ? `\n${failures} check(s) failed.` : '\nAll checks passed.');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
