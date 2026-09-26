# Spec

Language-independent contract of **PAPPA** (Piecewise Adaptive Poly-Patch
Approximation):

- `pappa.schema.json` — JSON Schema (draft 2020-12) документа описания сечения
  (`pappa v2.0`): раскладка, коэффициенты, члены фичера ям, статистика.
  Структурный источник — `python/pappa/io/model_file.py`.
- `sample.schema.json` — JSON Schema манифеста папки образца
  (`pappa-sample v1.0`): единицы, конфиг метода, список сечений, след входного CSV.
- `check_schema.py` — исполняемая проверка обеих схем **без зависимостей**
  (реализовано подмножество JSON Schema, которое используется в схемах) плюс
  инварианты, которые схемой не выражаются: `len(patches) == n_patches`,
  `len(coefs) == degree + 1`, чётность степени, согласованность манифеста и
  документов:
  ```bash
  python spec/check_schema.py                                     # все папки samples/
  python spec/check_schema.py samples/synthetic_sphere_r          # одна папка/порт
  ```
  Коды: `0` — всё сошлось, `1` — нарушения, `2` — нечего проверять.
  Проверено на всех папках образцов всех портов (22 папки × 10 сечений + манифесты
  = 242 файла).
- `conformance/` — golden vectors (`input -> expected output`) used to verify
  every language port against the reference implementation;
  see `conformance/README.md` for the vector format and tolerances.

Документы форматов-предшественников (`pmodel v1.0`, `appa v2.0`) читаются слоем
совместимости референса, но этими схемами **не** описываются: схемы фиксируют
только текущий формат `pappa v2.0`.

A port is considered correct when it reproduces all conformance vectors within
the documented tolerance and (for the full pipeline) matches the reference sample
folder numerically (curve 1e-6 mm; see docs/method.md §11).

Tools:

| Что | Чем |
|-----|-----|
| Проверить документы по схемам | `python spec/check_schema.py [папки]` |
| Сгенерировать векторы | `python python/studies/make_conformance.py` |
| Проверить порт по векторам | `cpp/build-*/…/pappa_conformance spec/conformance/vectors` (без Python) |
| Проверить VBA-порт (Excel) | `powershell -File vba/build_vba.ps1 -Vectors` / `-Test` / `-Pipeline` (модули `.bas` импортируются в книгу через COM) |
| Сверить порт с референсом на образце | `python python/studies/verify_port.py` |
| Всё сразу, по всем портам | `powershell -File verify_all.ps1 [-Full]` |

A sample folder (`samples/<name>/`) is the unit of exchange: `sample.json`
manifest + one `pappa.json` document per section + `report/verify.json` with the
numeric check of the port.


