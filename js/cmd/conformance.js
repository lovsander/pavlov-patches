#!/usr/bin/env node
// Проверка JS-порта PAPPA по конформанс-векторам.
// Запуск: node js/cmd/conformance.js [каталог с векторами]
// Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет каталога.
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { loadVectors, checkVector } from '../pappa/conformance.js';

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, '..', '..');
const vecDir = process.argv[2] ?? join(repo, 'spec', 'conformance', 'vectors');

if (!existsSync(vecDir)) {
  console.log(`нет каталога векторов: ${vecDir}`);
  process.exit(2);
}

const vectors = loadVectors(vecDir);
console.log(`JS-порт PAPPA: ${vectors.length} векторов (node ${process.version})`);
let bad = 0;
for (const { file, vector } of vectors) {
  const { ok, detail, notes } = checkVector(vector);
  if (!ok) bad++;
  console.log(`${file.padEnd(46)} ${ok ? 'OK' : 'FAIL'} ${detail}`);
  for (const n of notes.slice(0, 4)) console.log(`${' '.repeat(52)}-> ${n}`);
}
console.log(bad === 0 ? 'ВЫВОД: JS-порт проходит все векторы'
  : `ВЫВОД: расхождений ${bad}`);
process.exit(bad === 0 ? 0 : 1);
