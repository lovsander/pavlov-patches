"""spec/check_schema.py - проверка документов PAPPA по схемам БЕЗ зависимостей.

Зачем: спецификация должна быть исполняемой. Порты пишут два вида файлов -
документ сечения (spec/pappa.schema.json) и манифест образца
(spec/sample.schema.json) - и эта программа проверяет, что записанное им
соответствует контракту. Никаких пакетов: реализовано только подмножество
JSON Schema, реально используемое в схемах (type, const, enum, required,
properties, additionalProperties, items, minItems, minimum, exclusiveMinimum,
maximum, exclusiveMaximum, pattern).

Плюс проверяются инварианты, которых схема выразить не может:
  * len(patches) == global.n_patches;
  * len(coefs) == degree + 1;  degree чётная и лежит в [deg_min, deg_max];
  * pit_terms есть только там, где есть global.pit;
  * манифест и документы согласованы (index/file/section_id/height_mm).

Запуск:
    python spec/check_schema.py                    # каталог samples/ по умолчанию
    python spec/check_schema.py samples/synthetic_sphere_r samples/synthetic_sphere_go
Коды: 0 - всё сошлось; 1 - есть нарушения; 2 - нечего проверять/ошибка вызова.
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

PATTERN_CACHE = {}


def type_ok(expected, value):
    names = {
        "object": dict, "array": list, "string": str, "boolean": bool,
        "number": (int, float), "integer": int, "null": type(None),
    }
    if not isinstance(expected, list):
        expected = [expected]
    for name in expected:
        want = names.get(name)
        if want is None:
            continue
        if name in ("number", "integer") and isinstance(value, bool):
            continue          # bool - подкласс int, но в JSON это не число
        if isinstance(value, want):
            return True
    return False


def check(schema, value, path, errors):
    """Рекурсивная проверка значения по подмножеству JSON Schema."""
    if not isinstance(schema, dict):
        return
    if "type" in schema and not type_ok(schema["type"], value):
        errors.append(f"{path}: тип {type(value).__name__}, ожидалось {schema['type']}")
        return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: {value!r}, ожидалось {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} не из {schema['enum']}")
    if isinstance(value, str) and "pattern" in schema:
        pat = PATTERN_CACHE.setdefault(schema["pattern"], re.compile(schema["pattern"]))
        if not pat.match(value):
            errors.append(f"{path}: {value!r} не подходит под {schema['pattern']!r}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        for key, cmp in (("minimum", "<"), ("exclusiveMinimum", "<="),
                         ("maximum", ">"), ("exclusiveMaximum", ">=")):
            if key not in schema:
                continue
            limit = schema[key]
            bad = (value < limit) if cmp == "<" else \
                  (value <= limit) if cmp == "<=" else \
                  (value > limit) if cmp == ">" else (value >= limit)
            if bad:
                errors.append(f"{path}: {value} нарушает {key} {limit}")

    if isinstance(value, dict):
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}: нет обязательного ключа '{name}'")
        props = schema.get("properties", {})
        extra_allowed = schema.get("additionalProperties", True)
        for name, item in value.items():
            child = f"{path}.{name}" if path else name
            if name in props:
                check(props[name], item, child, errors)
            elif extra_allowed is False:
                errors.append(f"{child}: ключ не описан схемой")
            elif isinstance(extra_allowed, dict):
                check(extra_allowed, item, child, errors)

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: элементов {len(value)} < minItems {schema['minItems']}")
        if "items" in schema:
            for i, item in enumerate(value):
                check(schema["items"], item, f"{path}[{i}]", errors)


def load(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def check_document(doc, path, errors):
    """Инварианты документа, которые не выражаются схемой."""
    glob = doc.get("global", {})
    patches = doc.get("patches", [])
    if isinstance(glob.get("n_patches"), int) and len(patches) != glob["n_patches"]:
        errors.append(f"{path}: patches={len(patches)}, а global.n_patches={glob['n_patches']}")

    deg_min, deg_max = glob.get("deg_min"), glob.get("deg_max")
    for i, patch in enumerate(patches):
        deg = patch.get("degree")
        coefs = patch.get("coefs", [])
        if isinstance(deg, int):
            if deg % 2 != 0:
                errors.append(f"{path}: patches[{i}].degree={deg} нечётная")
            if isinstance(deg_min, int) and isinstance(deg_max, int) and not (deg_min <= deg <= deg_max):
                errors.append(f"{path}: patches[{i}].degree={deg} вне [{deg_min}, {deg_max}]")
            if len(coefs) != deg + 1:
                errors.append(f"{path}: patches[{i}].coefs={len(coefs)}, ожидалось degree+1={deg + 1}")
        if patch.get("pit_terms") and not glob.get("pit"):
            errors.append(f"{path}: patches[{i}].pit_terms есть, а global.pit отсутствует")


def check_manifest_against_docs(manifest, doc_paths, path, errors):
    """Манифест не должен расходиться с документами, которые он перечисляет."""
    for entry in manifest.get("sections", []):
        index = entry.get("index")
        if not isinstance(index, int) or not (0 <= index < len(doc_paths)):
            errors.append(f"{path}: sections[{index}].index вне диапазона файлов")
            continue
        doc_path = doc_paths[index]
        if entry.get("file") and doc_path.name != Path(str(entry["file"])).name:
            errors.append(f"{path}: sections[{index}].file={entry['file']!r}, а файл {doc_path.name!r}")
        doc = load(doc_path)
        meta = doc.get("meta", {})
        for key in ("section_id", "height_mm"):
            if key in meta and entry.get(key) != meta[key]:
                errors.append(f"{path}: sections[{index}].{key}={entry.get(key)!r} != meta.{key}={meta[key]!r}")


def run(sample_dirs):
    model_schema = load(HERE / "pappa.schema.json")
    sample_schema = load(HERE / "sample.schema.json")
    # самопроверка схем: они обязаны читаться как корректный JSON и не падать
    for name, schema in (("pappa", model_schema), ("sample", sample_schema)):
        probe = []
        check(schema, {}, "", probe)
        if not any("обязательного ключа" in e for e in probe):
            print(f"схема {name} не описывает обязательные ключи (проверьте файл)", file=sys.stderr)
            return 2

    files, bad_folders, problems = 0, 0, []
    for sample in sample_dirs:
        sample = Path(sample)
        manifest_path = sample / "sample.json"
        doc_dir = sample / "sections"
        doc_paths = sorted(doc_dir.glob("*.pappa.json")) if doc_dir.is_dir() else []
        if not manifest_path.exists() or not doc_paths:
            problems.append(f"{sample}: нет sample.json или sections/*.pappa.json")
            bad_folders += 1
            continue

        errors = []
        manifest = load(manifest_path)
        check(sample_schema, manifest, "sample.json", errors)
        for doc_path in doc_paths:
            doc = load(doc_path)
            check(model_schema, doc, doc_path.name, errors)
            check_document(doc, doc_path.name, errors)
        check_manifest_against_docs(manifest, doc_paths, "sample.json", errors)

        files += 1 + len(doc_paths)
        if errors:
            bad_folders += 1
            problems.append(f"{sample}:")
            problems.extend(f"    {e}" for e in errors[:12])
            if len(errors) > 12:
                problems.append(f"    ... и ещё {len(errors) - 12}")
        else:
            print(f"OK   {sample}  ({len(doc_paths)} сечений)")

    print()
    if problems:
        print("НАРУШЕНИЯ:")
        print("\n".join(problems))
        print(f"\nпроверено файлов: {files}, папок с нарушениями: {bad_folders}")
        return 1
    print(f"схемы: OK, проверено файлов: {files}")
    return 0


def main(argv):
    args = argv[1:]
    if args:
        targets = [Path(a) for a in args]
    else:
        targets = sorted([p for p in (REPO / "samples").glob("*") if p.is_dir()])
    targets = [t for t in targets if (t / "sample.json").exists() or (t / "sections").is_dir()]
    if not targets:
        print("нечего проверять: нет папок образцов (samples/<имя>/)", file=sys.stderr)
        return 2
    return run(targets)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main(sys.argv))

