# вырезано из _src_pit_feature.py / _src_star_layout.py (рефакторинг, CONTEXT.md §21)
"""
appa.report.sample_report — текстовые отчёты по папке образца.

Печать в консоль по правилу слоёв (§21): считает io/analysis, рисует viz,
печатает report. Здесь — всё, что видит человек при сборке и проверке образца.
"""


def _fmt(value, nd=5):
    return f"{value:.{nd}f}" if isinstance(value, float) else str(value)


def print_built_sample(root_dir, rows, manifest, docs=()):
    """
    Итог сборки образца: что записано, где, и с какими числами.

    rows     — список словарей на сечение: index, section_id, height_mm, n_points,
               n_outliers, degrees, n_pits, rmse_ideal;
    manifest — манифест (для строки с конфигом);
    docs     — пары (путь, ok) из validate_model по каждому документу.
    """
    bar = "=" * 96
    print(bar)
    print(f"ОБРАЗЕЦ СОБРАН: {manifest.get('name')}")
    print(bar)
    print(f"Папка:        {root_dir}")
    print(f"Манифест:     {root_dir / 'sample.json'}")
    inp = manifest.get("input") or {}
    if inp:
        print(f"Данные:       {inp.get('csv')} (sha256 {str(inp.get('sha256'))[:12]}...)")
    cfg = manifest.get("config") or {}
    if cfg:
        print(f"Конфиг:       n_patches={cfg.get('n_patches')}, "
              f"phase_deg={cfg.get('phase_deg')}, "
              f"deg={cfg.get('deg_min')}..{cfg.get('deg_max')}, "
              f"cleaner={cfg.get('cleaner')}")
        pits_on = bool(cfg.get("pits"))
        print(f"Фичер ям:     {'включён' if pits_on else 'выключен'} "
              f"(sigma={cfg.get('sigma_deg')}°, окно={cfg.get('pit_window_sigma')}σ), "
              f"детектор={cfg.get('detector')}")
    print(f"Сечений:      {len(rows)}")
    print()
    print(f"{'idx':>3} {'sec':>4} {'h, мм':>8} {'точек':>7} {'выбр.':>6} "
          f"{'ям':>3} {'RMSE к эталону':>15}  степени")
    for r in sorted(rows, key=lambda x: x["index"]):
        rmse = r.get("rmse_ideal")
        print(f"{r['index']:>3} {r['section_id']:>4} {r['height_mm']:>8.1f} "
              f"{r['n_points']:>7} {r['n_outliers']:>6} {r['n_pits']:>3} "
              f"{(_fmt(rmse) if rmse is not None else '        -'):>15}  "
              f"{r.get('degrees')}")
    if docs:
        bad = [p for p, ok in docs if not ok]
        print()
        print(f"Валидация документов: {len(docs) - len(bad)}/{len(docs)} OK"
              + (f", ошибки: {bad}" if bad else ""))
