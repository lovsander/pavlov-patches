# pavlov-patches

**PAPPA — Piecewise Adaptive Poly-Patch Approximation** — *aka “Pavlov patches”.*

Adaptive **piecewise** polynomial approximation of closed (periodic) profiles:
`N` overlapping local patches on a **normalized local coordinate**
(`x / half_train ∈ [-1, 1]`), each patch an even-degree polynomial whose degree is
chosen by the **RMSE-elbow rule** on its own training window, blended by a
**normalized smoothstep partition of unity** (C¹, no derivative jumps at the
seams), with optional **tapered-Gaussian pit terms** for narrow deep defects.

A model is a plain JSON document (`pappa.json`) — a fixed, small set of
coefficients per section — so the same model is evaluable in any language.

## Scope and honest status

Intended application: in-process geometry of **bodies of revolution** measured by
non-contact (laser/optical) scanning in sections along the axis, where a narrow
deep defect (pit, crack) is either smeared by low-order global bases or forces a
very high degree on a fixed-degree patch grid. Here the degree adapts per patch
and a pit can be carried by an explicit basis term.

Validated so far **on synthetic data only** (10 sections × 6000 pts, R = 15 mm,
three cracks ~4–6° wide, plus injected outliers) and against the C++ port through
`spec/conformance` vectors; no measurements on a real scanner are claimed yet.
Known limits are documented (degree cap and conditioning, overfitting spike at
high degree; legacy methods kept only for reproducing old measurements).

> Status: **work in progress.** Reference implementation in `python/`
> (package `pappa/`); ports (`cpp/`, `go/`) follow the same document format and are
> checked against the reference by `python/studies/verify_port.py`.

---

## Idea in one paragraph

Divide the domain into `N` overlapping sectors. Fit an independent low-order
polynomial over each sector; the sector’s residual behaviour (RMSE on the training
window, “elbow” rule) picks its degree. Reconstruct the profile as a normalized
smoothstep-weighted blend (partition of unity) of the patches, so the result is
continuous, C¹, and locally faithful without global ringing.

Distinctive features:

- **Local** — error is bounded per sector, no global Gibbs-type ringing;
- **Adaptive** — busy sectors get more degrees, smooth ones fewer;
- **Feature-aware** — a narrow pit can be carried by a tapered-Gaussian basis term
  instead of forcing a high polynomial degree;
- **Compact / deterministic** — a fixed, small set of coefficients per model;
- **Portable** — the model is a plain JSON document (`pappa.json`, schema and
  conformance vectors in `spec/`), reproducible in any language.

## Quickstart

```bash
# 1) reference model of a sample (10 sections) built by Python
python studies/build_sample.py                # -> samples/<name>/{sample.json, sections/*.pappa.json}

# 2) the port writes the same folder layout
<port> --input python/synthetic_data.csv --out-dir samples/<name>_cpp --no-pause

# 3) numeric check of the port against the reference (exit code 0/1/2)
python studies/verify_port.py --cpp-dir samples/<name>_cpp

# 4) optional: one wide figure (profile, residual to ideal, parity per section)
python studies/verify_port_figure.py --cpp-dir samples/<name>_cpp   # -> python/plots/
```

## Repository layout

| Path | Purpose |
|------|---------|
| `python/` | Reference implementation: package `pappa/` (`core`, `io`, `analysis`, `viz`, `report`); entry points in `studies/`, `demos/`, `generator/`; `research/` (rejected hypotheses and finished studies) and `deprecated/` (archive) |
| `samples/` | Generated sample folders (`sample.json` + one `pappa.json` per section + `report/`) — not committed |
| `cpp/`  | C++17 port (CMake): full pipeline, checked numerically against the reference (`ctest`) |
| `go/`   | Go port: full pipeline + core, checked by the conformance vectors and numerically against the reference (`go test ./...`) |
| `c/`    | C99 port (dependency-free core usable on MCU + host pipeline), checked by the vectors (`python/studies/check_c_port.py`) and numerically (`verify_port.py`) |
| `js/`   | JavaScript port (Node, ESM, zero packages): vectors + pipeline, checked numerically (`node js/cmd/conformance.js`) |
| `java/` | Java port (JDK, plain `javac`, own mini-JSON): vectors + pipeline + `pappa.SelfTest` |
| `kotlin/` | Kotlin port (uses the `kotlinc` bundled with Android Studio): vectors + pipeline + `pappa.SelfTest` |
| `rust/` | Rust port (cargo, **no crates**, offline build): vectors + pipeline + `cargo test` |
| `pascal/` | Free Pascal port (FPC 3.2, no units beyond RTL): vectors + pipeline + `selftest` |
| `swift/` | Swift port (SwiftPM, no packages; needs `SDKROOT` on Windows): vectors + pipeline + `swift test` |
| `julia/` | Julia port (package `Pappa`, **stdlib only**, works offline without `Pkg.instantiate`): vectors + pipeline + `test/runtests.jl` via `build_julia.ps1` |
| `docs/` | Method description, presentation assets, embedded (MCU) feasibility study |
| `spec/` | Model document schema + conformance vectors |

## License

[MIT](LICENSE) **with an additional field-of-use restriction** (the additional
condition takes precedence over the MIT permissions where they conflict):

* the software, its derivative works, the **PAPPA method** implemented here and
  any output produced by it (models, coefficients, approximated profiles) must
  **not** be used in military systems manufactured outside the Russian
  Federation — weapons, military and special equipment, and dual-use systems
  employed for military purposes whose manufacturer is located outside the
  Russian Federation;
* use in military systems of Russian origin **is permitted**;
* the restriction also covers granting third parties the right to do the above
  (sublicensing, distribution, supplying such customers).

Because of this restriction the project is **source-available, not OSI open
source**. Everything else (rights, warranty disclaimer, liability) is plain MIT.

