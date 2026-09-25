#!/usr/bin/env node
// PAPPA: JS-пайплайн (CSV -> папка образца в том же формате, что у Python/C++/Go/C).
// Запуск: node js/cmd/pappa.js --input FILE.csv [--out-dir DIR --name NAME]
//         [--description ТЕКСТ] [--no-pits]
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import { pathToFileURL } from 'node:url';

import { PatchApproximator } from '../pappa/model.js';
import { cleanIqr } from '../pappa/cleaner.js';
import { pits as detectPits } from '../pappa/detector.js';
import { saveSample } from '../pappa/document.js';

// Конфигурация — ровно как в референсе и портах C/C++/Go.
export const PIPELINE = {
  model: {
    nPatches: 7,
    phaseDeg: 24.75,
    degMin: 4,
    degMax: 14,
    overlapTrain: 15.0,
    overlapUse: 5.0,
    degElbowTol: 0.05,
  },
  cleaner: { baselineDeg: 1.0, iqrK: 3.0 },
  detector: {
    windowDeg: 1.0, wideDeg: 10.0, smoothDeg: 2.0, k: 5.5, minZoneDeg: 2.0,
  },
  pitShape: {
    sigmaDeg: 3.0, coreSigma: 2.0, windowSigma: 3.2, pitMinAmp: 3e-3, tapering: true,
  },
};

// Разбор CSV по заголовку: нужны section_id, height_mm, angle_deg, radius_mm.
export function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== '');
  if (lines.length === 0) throw new Error('пустой CSV');
  const head = lines[0].split(',').map((s) => s.trim());
  const idx = (name) => head.indexOf(name);
  const iSec = idx('section_id');
  const iH = idx('height_mm');
  const iA = idx('angle_deg');
  const iR = idx('radius_mm');
  if ([iSec, iH, iA, iR].some((i) => i < 0)) {
    throw new Error('в заголовке нужны section_id, height_mm, angle_deg, radius_mm');
  }
  const byId = new Map();
  for (let i = 1; i < lines.length; i++) {
    const f = lines[i].split(',');
    if (f.length <= Math.max(iSec, iH, iA, iR)) continue;
    const sid = parseInt(f[iSec], 10);
    if (!byId.has(sid)) {
      byId.set(sid, { sectionId: sid, heightMm: parseFloat(f[iH]), angles: [], radii: [] });
    }
    const s = byId.get(sid);
    s.angles.push(parseFloat(f[iA]));
    s.radii.push(parseFloat(f[iR]));
  }
  return [...byId.values()];
}

export function fitSection(angles, radii, usePits = true) {
  const sorted = angles.map((a, i) => [a, radii[i]]).sort((p, q) => p[0] - q[0]);
  const ang = sorted.map((p) => p[0]);
  const rad = sorted.map((p) => p[1]);

  const { mask, nOutliers } = cleanIqr(ang, rad, PIPELINE.cleaner);
  const ca = [];
  const cr = [];
  ang.forEach((a, i) => { if (!mask[i]) { ca.push(a); cr.push(rad[i]); } });

  const found = usePits ? detectPits(ca, cr, PIPELINE.detector) : [];
  const model = new PatchApproximator({ ...PIPELINE.model });
  if (found.length) {
    model.setPitShape(PIPELINE.pitShape);
    model.setPits(found);
  }
  const t0 = performance.now();
  model.fit(ca, cr);
  const fitMs = performance.now() - t0;
  return { model, nOutliers, nUsed: ca.length, pits: found, fitMs };
}

export function runPipeline(csvPath, outDir, name, description = 'PAPPA JS port', usePits = true) {
  const sections = parseCsv(readFileSync(csvPath, 'utf8')).map((s) => {
    const r = fitSection(s.angles, s.radii, usePits);
    return {
      sectionId: s.sectionId,
      heightMm: s.heightMm,
      model: r.model,
      nPointsTotal: s.angles.length,
      nOutliers: r.nOutliers,
      fitTimeMs: r.fitMs,
      source: 'csv',
      description: 'сечение из CSV',
      pits: r.pits,
      nUsed: r.nUsed,
    };
  });
  const anyPits = sections.some((s) => s.pits.length > 0);
  saveSample(outDir, name, sections, {
    pits: anyPits,
    inputCsv: csvPath,
    description,
    cleanerBaselineDeg: PIPELINE.cleaner.baselineDeg,
    cleanerIqrK: PIPELINE.cleaner.iqrK,
  });
  return sections;
}

function main() {
  const argv = process.argv.slice(2);
  let input = null;
  let outDir = null;
  let name = 'sample';
  let description = 'PAPPA JS port';
  let usePits = true;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--input') input = argv[++i];
    else if (argv[i] === '--out-dir') outDir = argv[++i];
    else if (argv[i] === '--name') name = argv[++i];
    else if (argv[i] === '--description') description = argv[++i];
    else if (argv[i] === '--no-pits') usePits = false;
  }
  if (!input) {
    console.log('PAPPA (JS): --input FILE.csv [--out-dir DIR --name NAME] '
      + '[--description ТЕКСТ] [--no-pits]');
    return 2;
  }
  console.log('CONFIG n_patches=7 phase_deg=24.75 deg_min=4 deg_max=14 '
    + 'overlap_train=15 overlap_use=5 deg_elbow_tol=0.05 baseline_deg=1 iqr_k=3 '
    + 'detector_window=1 wide=10 smooth=2 k=5.5 min_zone=2');
  const sections = runPipeline(input, outDir ?? 'samples/js_out', name, description, usePits);
  for (const s of sections) {
    const deg = s.model.getDegrees().join(',');
    console.log(`SECTION id=${s.sectionId} height=${s.heightMm} n_points=${s.nPointsTotal} `
      + `n_used=${s.nUsed} n_outliers=${s.nOutliers} n_pits=${s.pits.length} `
      + `fit_ms=${s.fitTimeMs.toFixed(1)} degrees=[${deg}]`);
  }
  console.log(`образец записан: ${outDir ?? 'samples/js_out'}`);
  console.log(`сечений: ${sections.length}`);
  return 0;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exit(main());
}
