/* Voice quick-log parser tests (parseVoiceCommand is pure — no DOM needed).
   Run with: node tests/test_voice_log.js
*/
'use strict';
const fs = require('fs');
const path = require('path');

let failures = 0;
function check(name, cond) {
  if (cond) { console.log(`ok - ${name}`); }
  else { failures++; console.log(`FAIL - ${name}`); }
}

const src = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', 'voice_log.js'), 'utf8');
eval(src);
const { parseVoiceCommand } = globalThis.VerdantVoice;

const PLANTS = [
  { id: 1, variety_name: 'Cherokee Purple', species_type: 'Tomato' },
  { id: 2, variety_name: 'California Wonder', species_type: 'Bell Pepper' },
  { id: 3, variety_name: 'Genovese', species_type: 'Basil' },
];

let d = parseVoiceCommand('watered the tomatoes', PLANTS);
check('water verb', d.action === 'water');
check('species match (plural)', d.plant_id === 1 && d.plant_name === 'Cherokee Purple');

d = parseVoiceCommand('I harvested 3 peppers', PLANTS);
check('harvest verb + qty', d.action === 'harvest' && d.qty === 3);
check('pepper match', d.plant_id === 2);

d = parseVoiceCommand('fed the basil', PLANTS);
check('feed verb', d.action === 'fertilize' && d.plant_id === 3);

d = parseVoiceCommand('fertilized the Cherokee Purple', PLANTS);
check('variety-name match beats nothing', d.action === 'fertilize' && d.plant_id === 1);

d = parseVoiceCommand('the tomatoes look great today', PLANTS);
check('no verb -> note', d.action === 'note' && d.plant_id === 1);

d = parseVoiceCommand('need to buy more mulch', PLANTS);
check('no plant -> null plant, still a note', d.action === 'note' && d.plant_id === null);

d = parseVoiceCommand('watered the tomatoes and the peppers', PLANTS);
check('full-name match preferred', d.plant_id === 1);

d = parseVoiceCommand('picked 12 cherry tomatoes', PLANTS);
check('pick verb + qty 12', d.action === 'harvest' && d.qty === 12);

d = parseVoiceCommand('watering', PLANTS);
check('bare verb, no plant', d.action === 'water' && d.plant_id === null);

d = parseVoiceCommand('', PLANTS);
check('empty text -> note', d.action === 'note' && d.text === '');

d = parseVoiceCommand('watered the tomatoes', null);
check('null plant list tolerated', d.action === 'water' && d.plant_id === null);

d = parseVoiceCommand('Watered The TOMATOES', PLANTS);
check('case-insensitive', d.plant_id === 1);

if (failures) { console.error(`${failures} failure(s)`); process.exit(1); }
console.log('voice parser: all green');
