"""Проверка C-порта PAPPA по конформанс-векторам (spec/conformance/vectors).

C-ядро (c/pappa.c) собирается в DLL и вызывается через ctypes: в самом C-коде нет
ни JSON, ни файлового ввода-вывода (только <math.h>), а векторы читает Python.
Допуски — те же, что у C++/Go: контур 1e-6 мм, коэффициенты max(1e-8, 1e-9·|c|),
детектор/очистка — доля точек (frac).

Запуск: python python/studies/check_c_port.py [каталог с векторами]
Коды:   0 — всё сошлось; 1 — расхождения; 2 — нет каталога/gcc.
"""
import ctypes, glob, json, os, subprocess, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO, 'c', 'pappa.c')
DLL = os.path.join(REPO, 'c', 'pappa.dll' if os.name == 'nt' else 'pappa.so')
GCC = next((c for c in (r'C:\msys64\mingw64\bin\gcc.exe', '/usr/bin/gcc', 'gcc')
            if c == 'gcc' or os.path.exists(c)), None)


def load():
    if (not os.path.exists(DLL)) or os.path.getmtime(DLL) < os.path.getmtime(SRC):
        cmd = [GCC, '-std=c99', '-O2', '-Wall', '-Wextra', '-shared', '-o', DLL, SRC]
        print('сборка C-ядра: ' + ' '.join(cmd))
        subprocess.run(cmd, check=True)
    lib = ctypes.CDLL(DLL)
    lib.pp_model_size.restype = ctypes.c_long
    lib.pp_detector_cfg_size.restype = ctypes.c_long
    P, D = ctypes.c_void_p, ctypes.c_double
    lib.pp_model_config.argtypes = [P, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    D, D, D, D, ctypes.c_int]
    lib.pp_model_set_pits.argtypes = [P, ctypes.POINTER(D), ctypes.c_int]
    lib.pp_model_set_pit_shape.argtypes = [P, D, D, D, D, ctypes.c_int]
    lib.pp_model_fit.argtypes = [P, ctypes.POINTER(D), ctypes.POINTER(D), ctypes.c_int]
    lib.pp_model_eval.argtypes = [P, ctypes.POINTER(D), ctypes.c_int, ctypes.POINTER(D)]
    lib.pp_detector_config.argtypes = [P, D, D, D, D, D]
    lib.pp_detector_band.argtypes = [P, ctypes.POINTER(D), ctypes.POINTER(D),
                                     ctypes.c_int, ctypes.POINTER(D)]
    lib.pp_detector_zones.argtypes = [P, ctypes.POINTER(D), ctypes.POINTER(D),
                                      ctypes.c_int, ctypes.POINTER(D)]
    lib.pp_detector_zones.restype = ctypes.c_int
    lib.pp_detector_pits.argtypes = [P, ctypes.POINTER(D), ctypes.POINTER(D),
                                     ctypes.c_int, ctypes.POINTER(D)]
    lib.pp_detector_pits.restype = ctypes.c_int
    lib.pp_clean_iqr.argtypes = [ctypes.POINTER(D), ctypes.POINTER(D), ctypes.c_int,
                                 D, D, ctypes.POINTER(ctypes.c_ubyte),
                                 ctypes.POINTER(ctypes.c_int)]
    lib.pp_model_n_patches.argtypes = [P]
    lib.pp_patch_degree.argtypes = [P, ctypes.c_int]
    lib.pp_patch_n_points.argtypes = [P, ctypes.c_int]
    lib.pp_patch_center.argtypes = [P, ctypes.c_int]
    lib.pp_patch_center.restype = D
    lib.pp_patch_coef.argtypes = [P, ctypes.c_int, ctypes.c_int]
    lib.pp_patch_coef.restype = D
    lib.pp_patch_n_pit.argtypes = [P, ctypes.c_int]
    lib.pp_patch_pit_off.argtypes = [P, ctypes.c_int, ctypes.c_int]
    lib.pp_patch_pit_off.restype = D
    lib.pp_patch_pit_amp.argtypes = [P, ctypes.c_int, ctypes.c_int]
    lib.pp_patch_pit_amp.restype = D
    return lib


def arr(vals):
    a = (ctypes.c_double * len(vals))()
    for i, v in enumerate(vals):
        a[i] = float(v)
    return a


def check_model(lib, v):
    cfg, exp = v['config'], v['expected']
    ia, ir = arr(v['input']['angles_deg']), arr(v['input']['radii_mm'])
    m = ctypes.create_string_buffer(lib.pp_model_size())
    lib.pp_model_config(m, int(cfg['n_patches']), int(cfg['deg_min']),
                        int(cfg['deg_max']), float(cfg['phase_deg']),
                        float(cfg['overlap_train']), float(cfg['overlap_use']),
                        float(cfg['deg_elbow_tol']),
                        1 if cfg.get('coord_mode', 'normalized') == 'raw' else 0)
    pits = cfg.get('pits_deg') or []
    if pits:
        lib.pp_model_set_pit_shape(m, float(cfg.get('sigma_deg', 3.0)),
                                   float(cfg.get('pit_core_sigma', 2.0)),
                                   float(cfg.get('pit_window_sigma', 3.2)),
                                   float(cfg.get('pit_min_amp', 3e-3)),
                                   1 if cfg.get('tapering', True) else 0)
        lib.pp_model_set_pits(m, arr(pits), len(pits))
    lib.pp_model_fit(m, ia, ir, len(ia))

    rel = float(v['tolerance'].get('coefs_rel', 1e-9))
    floor = float(v['tolerance'].get('coefs_abs_floor', 1e-8))
    tol_curve = float(v['tolerance'].get('curve_mm', 1e-6))
    notes, ok = [], True

    degs = [lib.pp_patch_degree(m, i) for i in range(lib.pp_model_n_patches(m))]
    if degs != list(exp['degrees']):
        ok = False
        notes.append(f'степени {degs} != {exp["degrees"]}')
    worst_c = 0.0
    for p, ref in enumerate(exp['coefs']):
        for k, cref in enumerate(ref):
            dc = abs(lib.pp_patch_coef(m, p, k) - cref)
            worst_c = max(worst_c, dc)
            if dc > max(floor, rel * abs(cref)):
                ok = False
                notes.append(f'патч {p} коэф {k}: Δ={dc:.3e}')
    pit_dev = 0.0
    for p, rt in enumerate(exp.get('pit_terms', [])):
        if isinstance(rt, dict):                       # {'dx_deg': [...], 'amp': [...]}
            ref_dx = list(rt.get('dx_deg', []))
            ref_amp = list(rt.get('amp', []))
        else:                                          # альтернатива: список пар
            ref_dx = [t[0] for t in rt]
            ref_amp = [t[1] for t in rt]
        n_keep = lib.pp_patch_n_pit(m, p)
        if n_keep != len(ref_dx):
            ok = False
            notes.append(f'патч {p}: терминов {n_keep} != {len(ref_dx)}')
            continue
        for j in range(n_keep):
            pit_dev = max(pit_dev,
                          abs(lib.pp_patch_pit_off(m, p, j) - ref_dx[j]),
                          abs(lib.pp_patch_pit_amp(m, p, j) - ref_amp[j]))
    ca, cr = arr(exp['curve']['angles_deg']), exp['curve']['radii_mm']
    out = (ctypes.c_double * len(ca))()
    lib.pp_model_eval(m, ca, len(ca), out)
    max_curve = max(abs(out[i] - cr[i]) for i in range(len(cr)))
    if max_curve > tol_curve:
        ok = False
        notes.append(f'контур {max_curve:.3e} > {tol_curve:g} мм')
    detail = (f'степени {degs} | коэф. {worst_c:.2e} | фичер {pit_dev:.2e} | '
              f'контур {max_curve:.3e} мм')
    return ok, detail, notes



def check_detector(lib, v):
    cfg, exp = v['config'], v['expected']
    ia, ir = arr(v['input']['angles_deg']), arr(v['input']['radii_mm'])
    n = len(ia)
    c = ctypes.create_string_buffer(lib.pp_detector_cfg_size())
    lib.pp_detector_config(c, float(cfg['window_deg']), float(cfg['wide_deg']),
                           float(cfg['smooth_deg']), float(cfg['k']),
                           float(cfg['min_zone_deg']))
    band = (ctypes.c_double * n)()
    lib.pp_detector_band(c, ia, ir, n, band)
    zones = (ctypes.c_double * 128)()
    nz = lib.pp_detector_zones(c, ia, band, n, zones)
    pits = (ctypes.c_double * 16)()
    npits = lib.pp_detector_pits(c, ia, ir, n, pits)
    notes = []
    ok = nz == len(exp['zones_deg']) and npits == len(exp['pits_deg'])
    if nz != len(exp['zones_deg']):
        notes.append(f'зон {nz} != {len(exp["zones_deg"])}')
    if npits != len(exp['pits_deg']):
        notes.append(f'ям {npits} != {len(exp["pits_deg"])}')
    dev = 0.0
    for i, (a0, a1) in enumerate(exp['zones_deg']):
        if i < nz:
            dev = max(dev, abs(zones[2 * i] - a0), abs(zones[2 * i + 1] - a1))
    for i, p in enumerate(exp['pits_deg']):
        if i < npits:
            d = abs(pits[i] - p)
            dev = max(dev, d)
            if d > 1e-6:
                ok = False
    detail = (f'зон {nz}/{len(exp["zones_deg"])}, ям {npits}/{len(exp["pits_deg"])}, '
              f'max|Δ| {dev:.2e}°')
    return ok, detail, notes


def check_cleaner(lib, v):
    cfg, exp = v['config'], v['expected']
    ia, ir = arr(v['input']['angles_deg']), arr(v['input']['radii_mm'])
    n = len(ia)
    mask = (ctypes.c_ubyte * n)()
    n_out = ctypes.c_int(0)
    lib.pp_clean_iqr(ia, ir, n, float(cfg['baseline_deg']), float(cfg['iqr_k']),
                     mask, ctypes.byref(n_out))
    got = {i for i in range(n) if mask[i]}
    ref = set(exp['mask_true_indices'])
    tol = max(1, int(float(v['tolerance'].get('frac', 0.02)) * n))
    extra, missing = len(got - ref), len(ref - got)
    ok = (extra <= tol and missing <= tol and
          abs(len(got) - int(exp['n_outliers'])) <= tol)
    detail = (f'выбросов {len(got)} (эталон {exp["n_outliers"]}), лишних {extra}, '
              f'пропущено {missing}')
    return ok, detail, []


def main():
    vec_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        REPO, 'spec', 'conformance', 'vectors')
    if not os.path.isdir(vec_dir):
        print(f'нет каталога векторов: {vec_dir}')
        return 2
    if not GCC:
        print('нет gcc для сборки C-ядра')
        return 2
    lib = load()
    files = sorted(glob.glob(os.path.join(vec_dir, '*.json')))
    print(f'C-порт PAPPA: {len(files)} векторов')
    bad = 0
    for f in files:
        v = json.load(open(f, encoding='utf-8'))
        if v['kind'] == 'model':
            ok, detail, notes = check_model(lib, v)
        elif v['kind'] == 'detector':
            ok, detail, notes = check_detector(lib, v)
        else:
            ok, detail, notes = check_cleaner(lib, v)
        bad += 0 if ok else 1
        print(f'{os.path.basename(f):<46} {"OK" if ok else "FAIL":<5} {detail}')
        for note in notes[:4]:
            print(f'{"":<52} -> {note}')
    print('ВЫВОД: C-порт проходит все векторы' if bad == 0
          else f'ВЫВОД: расхождений {bad}')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
