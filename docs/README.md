# Docs

**English** · [Русский](README.ru.md)

- `method.md` — formal description of PAPPA (math + pseudocode), Russian:
  [`method.ru.md`](method.ru.md).
- `embedded.md` — feasibility of running the C++ core on microcontrollers
  (Arduino/Cortex-M/ESP32): measured per-phase cost, memory, per-board verdicts,
  optimisation plan with parity impact. **Russian only** for now — its English
  translation is still pending.
- `assets/` — curated images used in the README and presentations: the method
  figures (`method_*.png`, built by `python/studies/make_method_figures.py`, numbers
  in `method.md` §14) and the charts from the study scripts in `python/pappa/viz/`,
  committed here as final assets.

## Documentation languages

English is canonical (`README.md`, `docs/method.md`), a translation lives next to
its original as `<name>.<lang>.md` (ISO 639-1) and starts with a language switcher.
`python tools/check_docs_i18n.py` verifies the pairs (both switchers present, the
section structure identical) and refuses language jumps inside any file — an
English prose paragraph in a Russian document or Cyrillic prose in an English one.
