/* Today dashboard detail pass (v2.47.0):
   - hero banner with the fern artwork (text clean on the left)
   - section labels (Up next / Forecast / Season) + count badges on cards
   - richer empty states; "Right now" label on the weather card
*/
'use strict';
const path = require('path');
const fs = require('fs');

let failures = 0;
function check(name, ok) {
  if (!ok) { failures += 1; console.error(`FAIL: ${name}`); }
  else { console.log(`ok: ${name}`); }
}

const ROOT = path.resolve(__dirname, '..');
const tpl = fs.readFileSync(path.join(ROOT, 'app', 'templates', 'today.html'), 'utf8');
const js = fs.readFileSync(path.join(ROOT, 'app', 'static', 'js', 'today.js'), 'utf8');

/* --- template --- */
check('hero banner uses the fern artwork', tpl.includes('/static/img/fern-hero.svg'));
check('hero has greeting + date + subtitle', tpl.includes('id="today-greeting"') && tpl.includes('id="today-date"') && tpl.includes('What needs doing out there?'));
check('care-due card has section label + count badge', tpl.includes('Up next') && tpl.includes('id="today-due-count"'));
check('harvest card has section label + count badge', tpl.includes('Forecast') && tpl.includes('id="today-harvest-count"'));
check('frost card has section label', tpl.includes('Season') && tpl.includes('id="today-frost"'));

/* --- JS behavior --- */
check('weather card gets a "Right now" label', js.includes('Right now'));
check('due badge shows count and hides when empty', js.includes('today-due-count') && js.includes('due.length} due'));
check('harvest badge shows count and hides when empty', js.includes('today-harvest-count') && js.includes('on the way'));
check('due empty state is a rich card', js.includes('Nothing due right now') && js.includes('bg-sage-50'));
check('harvest empty state is a rich card', js.includes('No predictions yet') && js.includes('bg-sage-50'));
check('overdue / rain-hold rendering preserved', js.includes('overdue') && js.includes('rain hold'));

if (failures) { console.error(`\n${failures} failure(s)`); process.exit(1); }
console.log('\nAll today-dashboard checks passed.');
