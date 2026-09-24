# python/deprecated — архив истории

Здесь лежат материалы, которые **больше не участвуют** в текущем пайплайне, но
сохранены как история исследований и итераций по методу Adaptive Poly-Patch
Approximation (APPA, «Pavlov patches»).

Ничего не удаляется — только перенесено сюда. Git-история перемещённых
скриптов сохранена (перенос сделан через `git mv`).

## Что оставлено в `python/` (актуальное)

* **Классы:** `outlier_cleaner.py` (OutlierCleaner), `patch_approximator.py`
  (PatchApproximator), `crack_detector.py` (CrackDetector), `pmodel.py`
  (сериализация `.pmodel.json`).
* **Генератор данных:** `generate_data_crack_many.py`.
* **Использование классов:** `demo_full_pipeline.py`, `demo_pmodel.py`,
  `patch_approximator_use.py`, `compare_patch_counts.py`.
* **Инструмент проверки C++ порта:** `cpp_plot_results.py`.

## `scripts/` — устаревшие скрипты

| Скрипт | Почему в архиве |
|---|---|
| `generate_data.py`, `generate_data_1.py`, `generate_data_crack.py` | ранние версии генератора данных, вытеснены `generate_data_crack_many.py` |
| `clean_outliers.py`, `clean_strong.py` | прототипы очистки выбросов, вытеснены классом `OutlierCleaner` |
| `approximate.py`, `approximate_4patches.py`, `approximate_8patches.py` | прототипы аппроксимации с жёстко заданным числом патчей, вытеснены `PatchApproximator` + `compare_patch_counts.py` |
| `approximate_fourier.py`, `furie_vs_8patches.py`, `comparison_auto.py`, `comparison_auto_2.py`, `smart_patch.py` | исследовательские сравнения с рядом Фурье и автоподбором параметров |
| `patches_about.py`, `patches_about1.py`, `patches_about2.py`, `patches_about3.py`, `patches_evolution.py` | итерации иллюстраций «как работает метод» (`final_step*.png`, `patches_evolution.png`) |
| `local_poly_reg.py` | альтернативный метод (локальная полиномиальная регрессия, LPR) для сравнения |

## `plots/` — старые картинки

Сгенерированы перечисленными выше скриптами (все имена — их выходные файлы,
кроме актуальных `generator_check.png`, `pipeline_*.png`,
`patch_count_comparison*.png`, `cpp_pipeline_results_analysis.png`, которые
остались в `python/`).

Вложенная папка `plots/about_patches_method/` — комплект шаговых иллюстраций
метода (`final_step0…4`), который когда-то выводился в отдельный каталог
`python/about_patches_method/`.

## `reports/` — старые отчёты и модели

`report_*.txt`, `model_*.txt`, `model_pavlov_section0.npz` — артефакты прежних
запусков (`*.txt` пишет демонстрация сериализации модели, `*.npz` — старая
форма сохранения `PatchApproximator.save()`).

---

Примечание: скрипты отсюда остаются рабочими, если запускать их из папки
`python/` (они читают `./synthetic_data.csv` и пишут картинки в текущий
каталог).
