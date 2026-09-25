"""
appa.paths — общие пути проекта.

Зачем: раньше каждый скрипт имел свою копию resolve_path() и считал файлы
относительно СВОЕЙ папки. После разбиения на пакет у скриптов разные уровни
вложенности, поэтому корень `python/` (где лежат synthetic_data.csv и
*.pappa.json) определяется здесь один раз.

Рисунки пишутся не в корень, а в python/plots/ (resolve_plot) — см. CONTEXT §21.
"""

from pathlib import Path

PY_ROOT = Path(__file__).resolve().parents[1]        # каталог python/
REPO_ROOT = PY_ROOT.parent                           # корень репозитория
PLOTS_DIR = PY_ROOT / "plots"                        # все .png проекта
# описания геометрических тел образцов: samples/<имя>/ (манифест + sections/)
SAMPLES_DIR = REPO_ROOT / "samples"


def resolve_path(name):
    """Путь к файлу относительно каталога python/ (не текущего каталога)."""
    p = Path(name)
    return p if p.is_absolute() else PY_ROOT / name


def resolve_plot(name):
    """
    Путь к рисунку в python/plots/ (каталог создаётся при первом обращении).

    Раньше .png падали в корень python/ вперемешку с данными и кодом; теперь
    рисунки лежат в одной папке, а корень остаётся местом данных. Абсолютный
    путь передаётся как есть (для внешних вызовов из C++ и скриптов).
    """
    p = Path(name)
    if p.is_absolute():
        return p
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    return PLOTS_DIR / p.name
