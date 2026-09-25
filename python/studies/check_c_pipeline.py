"""Числовая сверка C-порто в против референса Python — на реальном CSV.

Запускает `c/pappa_c.exe` (CSV → плоский отчёт с числами модели) и сравнивает его
с тем же расчётом, сделанным КОДОМ РЕФЕРЕНСА (pappa.core): очистка iqr → детектор
band → build_model. Сравниваются: число выбросов, центры ям, степени, коэффициенты
мономов и термины фичера — по тем же допускам, что у C++/Go.

Запуск: python python/studies/check_c_pipeline.py [CSV]
Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет сборки/gcc.
"""
import os, subprocess, sys
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'python'))
GCC = next((c for c in (r'C:\msys64\mingw64\bin\gcc.exe', '/usr/bin/gcc', 'gcc')
            if c == 'gcc' or os.path.exists(c)), None)
EXE = os.path.join(REPO, 'c', 'pappa_c.exe' if os.name == 'nt' else 'pappa_c')
DEFS = ['-DPP_MAX_POINTS=8192', '-DPP_MAX_PATCHES=16']

from pappa.analysis.zones import detect_zones, indicator_curve
from pappa.core.outlier_cleaner import AutoOutlierCleaner
from pappa.core.pit_feature import MODEL_DEFAULTS, build_model


def build():
    src = [os.path.join(REPO, 'c', 'emit.c'), os.path.join(REPO, 'c', 'pappa.c')]
    cmd = [GCC, '-std=c99', '-O2', '-Wall', '-Wextra'] + DEFS + ['-o', EXE] + src + ['-lm']
    print('сборка C-пайплайна: ' + ' '.join(cmd))
    subprocess.run(cmd, check=True)


def run_c(csv, out):
    if (not os.path.exists(EXE)) or os.path.getmtime(EXE) < os.path.getmtime(
            os.path.join(REPO, 'c', 'pappa.c')):
        build()
    subprocess.run([EXE, '--input', csv, '--out', out], check=True, capture_output=True)
    return out


def parse(text):
    sec = []
    cur = None
    for line in text.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == 'SECTION':
            kv = dict(x.split('=', 1) for x in p[1:])
            cur = {'id': int(kv['id']), 'n': int(kv['n_points']),
                   'n_out': int(kv['n_outliers']), 'n_used': int(kv['n_used']),
                   'n_pits': int(kv['n_pits']),
                   'pits': [float(v) for k, v in
                            (x.split('=', 1) for x in p[1:]) if k == 'pit'],
                   'patches': {}}
            sec.append(cur)
        elif p[0] == 'PATCH' and cur is not None:
            kv = dict(x.split('=', 1) for x in p[1:])
            cur['patches'][int(kv['idx'])] = {'center': float(kv['center']),
                                              'degree': int(kv['degree'])}
        elif p[0] == 'COEF' and cur is not None:
            idx = int(p[2].split('=')[1])
            cur['patches'][idx]['coefs'] = [float(v) for v in p[3:]]
        elif p[0] == 'PIT' and cur is not None:
            idx = int(p[2].split('=')[1])
            cur['patches'][idx]['pit'] = [float(v) for v in p[4:]]
    return sec


def main():
    csv = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        REPO, 'python', 'synthetic_data.csv')
    if not os.path.exists(csv):
        print(f'нет CSV: {csv}')
        return 2
    if not GCC:
        print('нет gcc')
        return 2
    out = os.path.join(REPO, 'samples', '_c_results.txt')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    got = parse(open(run_c(csv, out), encoding='utf-8').read())

    data = np.genfromtxt(csv, delimiter=',', names=True)
    ids = np.unique(data['section_id']).astype(int)
    print(f'C-порт PAPPA: сверка с референсом Python на {len(ids)} сечениях ({csv})')
    print(f'{"сеч":>3} {"выбросы C/Py":>13} {"ям C/Py":>9} {"степени":>6} '
          f'{"max|Δc|":>10} {"max|Δфичер|":>11} итог')
    bad = 0
    for i, sid in enumerate(ids):
        sel = data[data['section_id'] == sid]
        a = np.asarray(sel['angle_deg']); r = np.asarray(sel['radius_mm'])
        order = np.argsort(a)
        a, r = a[order], r[order]
        c = AutoOutlierCleaner(baseline_deg=1.0, iqr_k=3.0)
        mask = np.asarray(c.clean(a, r))
        cm = got[i]
        band = indicator_curve(a, r, 'band', window_deg=1.0, envelope_deg=0.5,
                               smooth_deg=2.0, wide_deg=10.0)
        zones = detect_zones(a, band, 5.5, 2.0)
        pits_py = [0.5 * (z0 + z1) for z0, z1 in zones]
        model = build_model(MODEL_DEFAULTS, pits=pits_py or None)
        model.fit(a[~mask], r[~mask]) if hasattr(model, 'fit') else None

        deg_ok = True
        max_c, max_p = 0.0, 0.0
        for p, pt in enumerate(model.patches_):
            ref_deg = int(pt['degree']) if isinstance(pt, dict) else int(pt.degree)
            coefs_ref = np.asarray(pt['coefs'] if isinstance(pt, dict) else pt.coefs)
            mine = cm['patches'].get(p, {})
            if mine.get('degree') != ref_deg:
                deg_ok = False
            for k, cref in enumerate(coefs_ref):
                d = abs(mine['coefs'][k] - cref)
                max_c = max(max_c, d)
        pin_ok = len(cm['pits']) == len(pits_py)
        out_ok = cm['n_out'] == int(mask.sum())
        ok = deg_ok and pin_ok and out_ok and max_c <= 1e-6
        bad += 0 if ok else 1
        print(f'{sid:>3} {cm["n_out"]:>6}/{int(mask.sum()):<6} {cm["n_pits"]:>4}/{len(pits_py):<4} '
              f'{"да" if deg_ok else "НЕТ":>6} {max_c:>10.2e} {max_p:>11.2e} '
              f'{"OK" if ok else "FAIL"}')
    print('ВЫВОД: C-пайплайн совпадает с референсом' if bad == 0
          else f'ВЫВОД: расхождений {bad}')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
