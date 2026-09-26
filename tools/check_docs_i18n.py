#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PAPPA: every description file must be in ONE language (docs localization).

    python3 tools/check_docs_i18n.py            check every *.md in the repository
    python3 tools/check_docs_i18n.py --list     list the files and their detected language
    python3 tools/check_docs_i18n.py --only README,docs/method
    python3 tools/check_docs_i18n.py --quiet    print the summary only

Exit code: 0 = clean, 1 = findings, 2 = nothing to check.

Convention (documented in README.md and docs/README.md):

  * the canonical language is English: `README.md`, `docs/method.md`;
  * a translation lives next to its original as `<name>.<lang>.md` (ISO 639-1),
    starts with a language switcher line and repeats the heading structure of the
    original - otherwise the two texts drift apart silently;
  * every other `*.md` sticks to one language: a Russian document must not contain
    English PROSE paragraphs and an English document must not contain Cyrillic
    prose (identifiers, code, tables, log excerpts and proper names are not prose,
    so code fences, table rows and lines that are mostly inline code are skipped).

The language of a file is NOT declared anywhere - it is detected: a file with
enough Cyrillic is Russian, otherwise it is English. So a jump is loud by itself.

NOTE: output is ASCII only on purpose (console code pages on Windows are not
UTF-8); Cyrillic lives in comments, where mangling is harmless.
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Языковые суффиксы, которые считаются переводами (`README.<lang>.md`).
LANGS = ("ru", "uk", "be", "de", "fr", "es", "it", "pt", "zh", "ja", "ko", "tr", "ar")

# Каталоги, которые не являются частью описаний репозитория.
SKIP_DIRS = {
    ".git", ".vscode", "node_modules", "__pycache__", ".venv", "venv",
    "build", "build-cmake", "out", "bin", "obj", "target", ".build", "samples",
}

# Локальные заметки, которые в репозиторий не входят и языку не подчиняются.
LOCAL_SUFFIX = ".local.md"
SKIP_FILES = {"CONTEXT.md"}

SUFFIX_RE = re.compile(r"^(?P<base>.+)\.(?P<lang>[a-z]{2}(?:-[A-Za-z]{2,4})?)\.md$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
CYR_RE = re.compile(r"[\u0400-\u04FF]")
LAT_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]{1,}")
HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
SWITCHER_HINT = ("](README.", "](method.", "](docs/", "**Русский**", "**English**")

# Порог «это русский файл»: кириллических букв не меньше, чем латинских.
CYR_SHARE_MIN = 0.10
# Сколько латинских слов подряд без единой кириллической буквы = абзац на чужом языке.
JUMP_WORDS = 8


def rel(path):
    return path.relative_to(REPO).as_posix()


def ascii_safe(text, limit=72):
    out = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in text.strip())
    return out[:limit]


def md_files():
    found = []
    for path in REPO.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        name = path.name
        if name.endswith(LOCAL_SUFFIX) or name in SKIP_FILES:
            continue
        found.append(path)
    return sorted(found)


def read(path):
    # utf-8-sig: файлы репозитория без BOM, но чужой BOM не должен ломать разбор.
    return path.read_text(encoding="utf-8-sig", errors="replace")


def detect_lang(text):
    cyr = len(CYR_RE.findall(text))
    lat = len(re.findall(r"[A-Za-z]", text))
    total = cyr + lat
    if total == 0:
        return "?", 0.0
    share = cyr / total
    return ("ru" if share >= CYR_SHARE_MIN else "en"), share


def prose_blocks(text):
    """Абзацы вне кода: (номер первой строки, склеенный текст)."""
    block, first, in_fence = [], None, False
    for lineno, line in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            if block:
                yield first, " ".join(block)
                block, first = [], None
            continue
        if in_fence:
            continue
        if line.strip():
            if first is None:
                first = lineno
            block.append(line.strip())
        elif block:
            yield first, " ".join(block)
            block, first = [], None
    if block:
        yield first, " ".join(block)


def looks_like_code(text):
    stripped = text.strip()
    if stripped.startswith(("|", "#", "![", "http")):
        return True
    if "http://" in text or "https://" in text:
        return True
    if "`" in text and len(text) > 0:
        code_chars = sum(len(part) for part in text.split("`")[1::2])
        if code_chars * 2 >= len(text):
            return True
    return False


def is_switcher(text):
    """Строка-переключатель языка: в ней ссылка на брата `X.<lang>.md`.

    Кириллица в ней законна даже в английском файле: это НАЗВАНИЕ языка.
    """
    for target in re.findall(r"\]\(([^)\s]+\.md)\)", text):
        if SUFFIX_RE.match(Path(target).name) and Path(target).name.split(".")[-2] in LANGS:
            return True
    return False


# Слова-маркеры английской прозы: одно такое слово в блоке без кириллицы
# означает, что абзац написан по-английски, а не является списком терминов.
EN_FUNCTION_WORDS = frozenset("""
a an the and or nor of to in on at for with by from as is are was were be been being
not no that this these those it its if then than when where which while so but per
into over under all any each most only also can will must should may has have had do
does did there their them they we you your our one two both same very more less up
out off own such about after before during without within between because
""".split())


def is_prose(text):
    """Проза, а не имя собственное или список терминов."""
    words = LAT_WORD_RE.findall(text)
    if len(words) < 6:
        return False
    lower = sum(1 for w in words if w.islower())
    markers = sum(1 for w in words if w.lower() in EN_FUNCTION_WORDS)
    return markers >= 1 or lower >= 0.3 * len(words)


def check_language(path, text):
    """Перескок языка: абзац без кириллицы в русском файле, кириллица в английском."""
    problems = []
    lang, share = detect_lang(text)
    if lang == "?":
        return problems, lang, share
    for lineno, block in prose_blocks(text):
        if looks_like_code(block) or is_switcher(block):
            continue
        has_cyr = bool(CYR_RE.search(block))
        if lang == "ru" and not has_cyr:
            if is_prose(block):
                problems.append(
                    "%s:%d  jump: latin-only paragraph in a Russian file: %s"
                    % (rel(path), lineno, ascii_safe(block)))
        elif lang != "ru" and has_cyr:
            problems.append(
                "%s:%d  jump: Cyrillic paragraph in a %s file: %s"
                % (rel(path), lineno, lang, ascii_safe(block)))
    return problems, lang, share


def heading_levels(text):
    levels = []
    for line in text.splitlines():
        if FENCE_RE.match(line):
            continue
        m = HEADING_RE.match(line.strip())
        if m:
            levels.append(len(m.group(1)))
    return levels


def check_pairing(path, text):
    """`X.<lang>.md` должен иметь оригинал `X.md` и переключатель языка в обоих."""
    problems = []
    m = SUFFIX_RE.match(path.name)
    if not m or m.group("lang") not in LANGS:
        return problems
    base_name = m.group("base") + ".md"
    canonical = path.with_name(base_name)
    if not canonical.exists():
        problems.append(
            "%s  no canonical original %s (translation without a source): the "
            "English text must exist first" % (rel(path), base_name))
        return problems
    other = read(canonical)
    if path.name not in other:
        problems.append(
            "%s  has no language switcher: the canonical %s never links back to it"
            % (rel(path), base_name))
    if base_name not in text:
        problems.append(
            "%s  has no language switcher: the file never links to %s"
            % (rel(path), base_name))
    a, b = heading_levels(other), heading_levels(text)
    if a != b:
        diff = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y),
                    min(len(a), len(b)))
        problems.append(
            "%s  heading structure differs from %s: %d headings vs %d, first "
            "mismatch at heading #%d (level %s vs %s) - a translated chapter was "
            "renamed, added or lost"
            % (rel(path), base_name, len(b), len(a), diff + 1,
               b[diff] if diff < len(b) else "-", a[diff] if diff < len(a) else "-"))
    return problems


def main(argv):
    ap = argparse.ArgumentParser(
        description="check that every description file sticks to ONE language")
    ap.add_argument("--list", action="store_true",
                    help="list the files with the detected language and exit")
    ap.add_argument("--only", default="",
                    help="comma-separated path fragments, e.g. README,docs/method")
    ap.add_argument("--quiet", action="store_true", help="print the summary only")
    args = ap.parse_args(argv)

    only = [part.strip() for part in args.only.split(",") if part.strip()]
    files = [p for p in md_files()
             if not only or any(part in rel(p) for part in only)]
    if not files:
        print("nothing to check: no *.md matched")
        return 2

    findings, checked, langs = [], 0, {"en": 0, "ru": 0, "?": 0}
    for path in files:
        text = read(path)
        problems, lang, share = check_language(path, text)
        langs[lang] = langs.get(lang, 0) + 1
        problems += check_pairing(path, text)
        if args.list:
            print("%-46s %-3s cyrillic %5.1f%%  %5d lines  %s"
                  % (rel(path), lang, 100.0 * share, text.count("\n") + 1,
                     "translation" if SUFFIX_RE.match(path.name) else ""))
        elif problems and not args.quiet:
            for line in problems:
                print(line)
        findings += problems
        checked += 1

    if not args.list:
        print("docs i18n: %d files checked (%d EN, %d RU, %d unknown), %d findings"
              % (checked, langs.get("en", 0), langs.get("ru", 0),
                 langs.get("?", 0), len(findings)))
        return 1 if findings else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
