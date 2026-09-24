"""
appa.paths — общие пути проекта.

Зачем: раньше каждый скрипт имел свою копию resolve_path() и считал файлы
относительно СВОЕЙ папки. После разбиения на пакет у скриптов разные уровни
вложенности, поэтому корень `python/` (где лежат synthetic_data.csv и .png)
определяется здесь один раз.
"""

from pathlib import Path

PY_ROOT = Path(__file__).resolve().parents[1]        # каталог python/
REPO_ROOT = PY_ROOT.parent                           # корень репозитория


def resolve_path(name):
    """Путь к файлу относительно каталога python/ (не текущего каталога)."""
    p = Path(name)
    return p if p.is_absolute() else PY_ROOT / name
