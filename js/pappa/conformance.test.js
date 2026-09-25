// Тест встроенным раннером Node (node --test): конформанс-векторы должны проходить
// целиком. Дополнительно — дымовой тест пайплайна на крошечном CSV.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { loadVectors, checkVector } from './conformance.js';
import { parseCsv, fitSection } from '../cmd/pappa.js';

const repo = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const vecDir = join(repo, 'spec', 'conformance', 'vectors');

test('конформанс-векторы: JS-порт проходит все', () => {
  const vectors = loadVectors(vecDir);
  assert.ok(vectors.length >= 4, `ожидались минимум 4 вектора, нашли ${vectors.length}`);
  for (const { file, vector } of vectors) {
    const r = checkVector(vector);
    assert.ok(r.ok, `${file}: ${r.detail} ${r.notes.join('; ')}`);
  }
});

test('разбор CSV по заголовку и обучение сечения', () => {
  const rows = ['section_id,height_mm,angle_deg,radius_mm'];
  for (let i = 0; i < 360; i++) {
    const a = i;
    rows.push(`0,0,${a},${(50 + 0.4 * Math.sin(a * Math.PI / 180)).toFixed(6)}`);
  }
  const secs = parseCsv(rows.join('\n'));
  assert.equal(secs.length, 1);
  assert.equal(secs[0].angles.length, 360);

  const r = fitSection(secs[0].angles, secs[0].radii, true);
  assert.equal(r.model.patches.length, 7);
  assert.equal(r.nOutliers, 0);
  // Гладкая синусоида должна воспроизводиться точно.
  const curve = r.model.eval(secs[0].angles);
  let maxErr = 0;
  secs[0].radii.forEach((v, i) => { maxErr = Math.max(maxErr, Math.abs(curve[i] - v)); });
  assert.ok(maxErr < 1e-6, `max|Δ| = ${maxErr}`);
});
