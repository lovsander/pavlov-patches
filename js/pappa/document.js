// Запись папки образца из JS — тот же контракт, что у Python/C++/Go/C:
//   <out_dir>/sample.json              манифест (format pappa-sample v1.0)
//   <out_dir>/sections/NN.pappa.json   документ сечения (pappa v2.0)
// Ключи и их порядок повторяют cpp/sample_writer.cpp: папки от разных портов
// сравниваются численно (python/studies/verify_port.py).
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const PORT_VERSION = '0.1.0';

// Число в стиле %.17g (как C/C++): целые — без дробной части, иначе 17 значащих.
export function num(v) {
  if (!Number.isFinite(v)) return '0';
  if (Number.isInteger(v) && Math.abs(v) < 1e15) return String(v);
  return v.toPrecision(17);
}

export function isoUtcNow() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
}

function q(s) { return JSON.stringify(String(s ?? '')); }

// Плоский pretty-printer: отступ 2 пробела, как JsonWriter в C++.
export class J {
  constructor() { this.parts = []; this.depth = 0; }

  get ind() { return '  '.repeat(this.depth); }

  beginObject() { this.parts.push('{'); this.depth += 1; this.parts.push('\n' + this.ind); }
  endObject() { this.depth -= 1; this.parts.push('\n' + this.ind + '}'); }
  beginArray() { this.parts.push('['); this.depth += 1; this.parts.push('\n' + this.ind); }
  endArray() { this.depth -= 1; this.parts.push('\n' + this.ind + ']'); }

  key(k) { this.parts.push(this.ind + q(k) + ': '); }
  value(v) {
    if (typeof v === 'string') this.parts.push(q(v));
    else if (typeof v === 'boolean' || v === null) this.parts.push(String(v));
    else this.parts.push(num(v));
  }
  kv(k, v) { this.key(k); this.value(v); }
  comma() { this.parts.push(','); this.parts.push('\n' + this.ind); }
  toString() { return this.parts.join(''); }
}

function writePatches(w, m) {
  w.key('patches');
  w.beginArray();
  m.patches.forEach((p, i) => {
    w.parts.push(i ? ',\n' + w.ind : '\n' + w.ind);
    w.beginObject();
    w.kv('center_deg', p.center);     w.comma();
    w.kv('degree', p.degree);         w.comma();
    w.kv('n_points', p.nPoints);      w.comma();
    w.key('coefs');
    w.beginArray();
    p.coefs.forEach((c, j) => { if (j) w.parts.push(', '); w.value(c); });
    w.endArray();
    w.comma();

    w.key('metrics');
    w.beginObject();
    w.kv('amplitude_mm', p.metrics.amplitude_mm);           w.comma();
    w.kv('mean_radius_mm', p.metrics.mean_radius_mm);       w.comma();
    w.kv('amplitude_norm', p.metrics.amplitude_norm);       w.comma();
    w.kv('deg_elbow_tol', p.metrics.deg_elbow_tol);         w.comma();
    w.kv('rmse_selected_mm', p.metrics.rmse_selected_mm);   w.comma();
    w.kv('rmse_best_mm', p.metrics.rmse_best_mm);           w.comma();
    w.kv('n_train_points', p.metrics.n_train_points);
    w.endObject();
    w.comma();

    w.key('stats');
    w.beginObject();
    w.kv('rmse_mm', p.stats.rmse_mm);              w.comma();
    w.kv('mae_mm', p.stats.mae_mm);                w.comma();
    w.kv('max_err_mm', p.stats.max_err_mm);        w.comma();
    w.kv('correlation', p.stats.correlation);
    w.endObject();

    // Термины фичера ям — ключ у КАЖДОГО патча, когда модель с ямами
    // (включая пустой список): так ждёт загрузчик Python.
    if (m.hasPits) {
      w.comma();
      w.key('pit_terms');
      w.beginArray();
      p.pitOffsets.forEach((dx, j) => {
        if (j) w.parts.push(', ');
        w.beginObject();
        w.kv('dx_deg', dx);   w.comma();
        w.kv('amp', p.pitCoefs[j]);
        w.endObject();
      });
      w.endArray();
    }
    w.endObject();
  });
  w.parts.push('\n' + w.ind);
  w.endArray();
}


export function saveSectionDocument(path, section) {
  const m = section.model;
  if (!m.isFitted) throw new Error('saveSectionDocument: модель не обучена');
  const w = new J();
  w.beginObject();
  w.kv('format', 'pappa');   w.comma();
  w.kv('version', '2.0');    w.comma();
  w.kv('method', m.hasPits ? 'PitPatchApproximator' : 'PatchApproximator'); w.comma();
  w.kv('created', isoUtcNow());  w.comma();

  w.key('software');
  w.beginObject();
  w.kv('language', 'js');    w.comma();
  w.kv('pappa_version', PORT_VERSION);
  w.endObject();
  w.comma();

  w.key('meta');
  w.beginObject();
  w.kv('section_id', section.sectionId);    w.comma();
  w.kv('height_mm', section.heightMm);      w.comma();
  w.kv('source', section.source ?? '');     w.comma();
  w.kv('description', section.description ?? '');
  w.endObject();
  w.comma();

  w.key('global');
  w.beginObject();
  w.key('units');
  w.beginObject();
  w.kv('angle', 'degree');  w.comma();
  w.kv('length', 'mm');
  w.endObject();
  w.comma();
  w.kv('n_patches', m.opt.nPatches);             w.comma();
  w.kv('half_sector_deg', m.halfSector);         w.comma();
  w.kv('phase_deg', m.opt.phaseDeg);             w.comma();
  w.kv('half_train_deg', m.halfTrain);           w.comma();
  w.kv('half_use_deg', m.halfUse);               w.comma();
  w.kv('overlap_train_deg', m.opt.overlapTrain); w.comma();
  w.kv('overlap_use_deg', m.opt.overlapUse);     w.comma();
  w.kv('deg_min', m.opt.degMin);                 w.comma();
  w.kv('deg_max', m.opt.degMax);                 w.comma();
  w.kv('coord_mode', m.opt.coordMode);           w.comma();
  w.kv('deg_elbow_tol', m.opt.degElbowTol);      w.comma();
  w.kv('amplitude_scale', m.opt.amplitudeScale);
  if (m.hasPits) {
    w.comma();
    w.key('pit');
    w.beginObject();
    w.kv('sigma_deg', m.pit.sigmaDeg);        w.comma();
    w.kv('core_sigma', m.pit.coreSigma);      w.comma();
    w.kv('window_sigma', m.pit.windowSigma);  w.comma();
    w.kv('pit_min_amp', m.pit.pitMinAmp);     w.comma();
    w.kv('tapering', m.pit.tapering);         w.comma();
    w.key('centers_deg');
    w.beginArray();
    m.pits.forEach((c, i) => { if (i) w.parts.push(', '); w.value(c); });
    w.endArray();
    w.endObject();
  }
  w.endObject();
  w.comma();

  writePatches(w, m);
  w.comma();

  w.key('statistics');
  w.beginObject();
  w.kv('n_points_total', section.nPointsTotal);    w.comma();
  w.kv('n_outliers_removed', section.nOutliers);   w.comma();
  w.kv('fit_time_ms', section.fitTimeMs);
  w.endObject();

  w.endObject();
  writeFileSync(path, w.toString() + '\n', 'utf8');
  return path;
}

export function saveSample(outDir, name, sections, options = {}) {
  const opt = {
    cleanerBaselineDeg: 1.0,
    cleanerIqrK: 3.0,
    pits: false,
    inputCsv: '',
    description: '',
    ...options,
  };
  mkdirSync(join(outDir, 'sections'), { recursive: true });

  const ordered = sections.slice().sort((a, b) => a.sectionId - b.sectionId);
  const first = ordered.length ? ordered[0].model : null;

  const w = new J();
  w.beginObject();
  w.kv('format', 'pappa-sample');   w.comma();
  w.kv('version', '1.0');           w.comma();
  w.kv('name', name);               w.comma();
  w.kv('created', isoUtcNow());     w.comma();

  w.key('units');
  w.beginObject();
  w.kv('angle', 'degree');  w.comma();
  w.kv('length', 'mm');
  w.endObject();
  w.comma();

  w.key('meta');
  w.beginObject();
  w.kv('description', opt.description);
  w.endObject();
  w.comma();

  if (opt.inputCsv) {
    w.key('input');
    w.beginObject();
    w.kv('csv', opt.inputCsv);
    w.endObject();
    w.comma();
  }

  w.key('config');
  w.beginObject();
  w.kv('n_patches', first ? first.opt.nPatches : 0);           w.comma();
  w.kv('phase_deg', first ? first.opt.phaseDeg : 0.0);         w.comma();
  w.kv('deg_min', first ? first.opt.degMin : 0);               w.comma();
  w.kv('deg_max', first ? first.opt.degMax : 0);               w.comma();
  w.kv('overlap_train', first ? first.opt.overlapTrain : 0.0); w.comma();
  w.kv('overlap_use', first ? first.opt.overlapUse : 0.0);     w.comma();
  w.kv('deg_elbow_tol', first ? first.opt.degElbowTol : 0.0);  w.comma();
  w.key('cleaner');
  w.parts.push('{"mode": "auto", "auto": {"method": "iqr", '
    + `"baseline_deg": ${num(opt.cleanerBaselineDeg)}, "iqr_k": ${num(opt.cleanerIqrK)}}}`);
  w.comma();
  w.kv('pits', opt.pits);
  if (opt.pits && first) {
    w.comma();
    w.kv('sigma_deg', first.pit.sigmaDeg);           w.comma();
    w.kv('pit_core_sigma', first.pit.coreSigma);     w.comma();
    w.kv('pit_window_sigma', first.pit.windowSigma); w.comma();
    w.kv('pit_min_amp', first.pit.pitMinAmp);        w.comma();
    w.kv('tapering', first.pit.tapering);
  }
  w.comma();
  w.key('detector');
  w.value(null);
  w.endObject();
  w.comma();

  w.key('sections');
  w.beginArray();
  ordered.forEach((s, i) => {
    const file = `sections/${String(i).padStart(2, '0')}.pappa.json`;
    saveSectionDocument(join(outDir, file), s);
    w.parts.push(i ? ',\n' + w.ind : '\n' + w.ind);
    w.beginObject();
    w.kv('index', i);                 w.comma();
    w.kv('section_id', s.sectionId);  w.comma();
    w.kv('height_mm', s.heightMm);    w.comma();
    w.kv('file', file);               w.comma();
    w.kv('n_points', s.nPointsTotal); w.comma();
    w.kv('n_outliers', s.nOutliers);
    w.endObject();
  });
  w.parts.push('\n' + w.ind);
  w.endArray();

  w.endObject();
  writeFileSync(join(outDir, 'sample.json'), w.toString() + '\n', 'utf8');
  return outDir;
}
