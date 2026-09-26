# pavlov-patches

**English** · [Русский](README.ru.md)

**PAPPA — Piecewise Adaptive Poly-Patch Approximation** — *aka “Pavlov patches”.*

Adaptive **piecewise** polynomial approximation of closed (periodic) profiles:
`N` overlapping local patches on a **normalized local coordinate**
(`x / half_train ∈ [-1, 1]`), each patch an even-degree polynomial whose degree is
chosen by the **RMSE-elbow rule** on its own training window, blended by a
**normalized smoothstep partition of unity** (C¹, no derivative jumps at the
seams), with optional **tapered-Gaussian pit terms** for narrow deep defects. The
patches form one fixed **“star”** for the whole body — a single `N`, a single phase
shift of the seams — and are fitted to **cleaned** points (automatic IQR outlier
removal runs before the degree rule, the pit detector and the fit).

A model is a plain JSON document (`pappa.json`) — a fixed, small set of
coefficients per section — so the same model is evaluable in any language.

Full description of the method (math + pseudocode + parity pitfalls):
[`docs/method.md`](docs/method.md) (Russian: [`docs/method.ru.md`](docs/method.ru.md)).

## What exactly this method contributes

The language portfolio is about portability. The value of the method itself is four
decisions, each of which is visible in the model document and verified on synthetic
data (figures `docs/assets/method_star.png`, `method_degrees.png`,
`method_cleaning.png`; the numbers are printed by the very script that draws them):

| Decision | What it buys | Limits / cost |
|---|---|---|
| **The patch “star”**: N = 7 overlaps over the whole body, seams rotated by phase 24.75° | a narrow defect does not ring around the whole ring; no node sits next to a crack (minimum “pit → seam” clearance over 10 sections: **+9.92°** versus **+0.19°** at `phase_deg = 0`, where the seam comes within 2° of a crack in 5 sections out of 10) | the layout is an external parameter: N and the phase are chosen in advance by brute force (`python/studies/explore_star_layout.py`), not from the data of a given section |
| **Blending instead of “nearest patch”**: smoothstep partition of unity + training wider than use (±40.71° versus ±30.71°) | a C¹ contour; at the edge of its use zone a patch still rests on training data rather than on extrapolation, and the error stays inside its own sector | the overlap spends points on fitting twice (about 1337 points out of 5882 inside a patch window) |
| **Degree from residuals** (RMSE “elbow”, 5 % tolerance) | “busy” patches take 10–14, smooth ones 4–6 — locally, from their own window; the rule is checkable from the document (`rmse_selected_mm ≤ rmse_best_mm · 1.05`) | this is a budget choice, not magic: a uniform deg 14 is more accurate on this section (max\|Δr\| 0.049 mm versus 0.054 mm), but that is 109 coefficients versus **65** |
| **Outlier cleaning BEFORE the model** (auto `iqr`, k = 3.0, ring median) | outliers eat neither the degree choice nor the pit amplitudes: without cleaning max\|Δr\| is **0.124 mm** with degrees 6–8 instead of **0.054 mm** with 4–12 | on “sterile” data IQR → 0, the threshold hits its 1 mm cap and the cleaner effectively switches itself off (§7) |

Two more consequences are also worth counting as contribution: **locality** (the
error is bounded by the sector, which is why a truncated Fourier series loses
structurally rather than by coefficient count) and the **deterministic document** —
65 coefficients instead of the original measurements: the contour is reproduced
without the points it was built from.

What this claim does **not** contain is a promise of “magical accuracy”: with a
well-chosen window LPR gives a comparable error, and that analysis is in §14 of
[`docs/method.md`](docs/method.md).

## What is inside

* **“Star” layout** — `N` overlapping patches over the whole body; the seams
  (nodes) are moved away from difficult zones by the phase `phase_deg = 24.75°`:
  the minimum “pit centre → nearest seam” clearance over all 10 sections is
  **+9.92°** versus **+0.19°** at `phase_deg = 0`. A seam is the only place where
  the contour rests on no fresh patch centre at all, so it must not sit in a
  crack;
* **Blending, not “pick the nearest patch”** — a normalized smoothstep partition
  of unity, plus **training wider than use** (`half_train = 40.71°` versus
  `half_use = 30.71°`): at the edge of its use zone a patch rests on training data
  rather than on extrapolation. The contour is C¹: no derivative jump at the
  seams, and a constant is reproduced exactly;
* **Each patch picks its own degree** — the RMSE “elbow” rule on the residuals of
  its own window: “busy” sectors (a pit near the edge, an inflection) take 10–14,
  smooth ones 4–6. The rule is checkable from the document:
  `metrics.rmse_selected_mm ≤ metrics.rmse_best_mm · (1 + 0.05)`. The budget stays
  explicit: 65 coefficients versus 109 for a uniform deg 14 (see
  `method_degrees.png`);
* **Outlier cleaning runs BEFORE the model** (auto `iqr`, `k = 3.0`, median window
  over the ring): otherwise outliers eat both the degree choice and the pit
  amplitudes — the same model on dirty points gives max|Δr| 0.124 mm versus
  0.054 mm;
* **Pit feature** — a narrow deep pit is described by an explicit basis term (a
  tapered Gaussian at 3.2σ with a smooth return to the basis) instead of a forced
  rise of the polynomial degree. The pit layout shares the patch layout (one phase
  for the whole body);
* **Locality** — the error is bounded inside the sector, there is no global
  “ringing” (Gibbs) on narrow defects, and an outlier in one sector does not pull
  the profile in its neighbours;
* **Compactness and determinism** — a fixed, small set of coefficients per
  section; neither fitting nor evaluation needs the original measurements;
* **Portability** — a model is a plain JSON file (`spec/pappa.schema.json`), and
  the correctness of any language is checked by the same vectors
  (`spec/conformance/`) and by numerical comparison against the reference.

**16 language implementations** of one method (plus the Python reference): C++17,
C99, Go, JavaScript, Java, Kotlin, Rust, C# (.NET), F# (.NET), Free Pascal,
Fortran 2018, Swift, Julia, R, GNU Octave, VBA 7 (Microsoft Excel). Each one is a
full “CSV → sample folder” pipeline with its own gates (vectors + tests) and with
documents written to the common contract.

## What it looks like

The “star” layout: radial centres, seams, training wider than use, and the phase
fighting the cracks:

![“star” layout: rays, seams, training and use windows](docs/assets/method_star.png)

Degree selection: the “elbow” rule per patch, and cost versus error (one degree
for all patches versus the adaptive one):

![degree selection: the “elbow” rule and cost versus error](docs/assets/method_degrees.png)

Outlier cleaning: the mask, “abnormality” versus the IQR threshold, and the same
model fitted to dirty points:

![automatic outlier cleaning and the price of skipping it](docs/assets/method_cleaning.png)

The method from the inside, the pit detector and the comparisons:

![the method inside: patches, weights, error](docs/assets/method_patches.png)

![the band crack detector](docs/assets/method_detector.png)

![comparison with a truncated Fourier series](docs/assets/method_vs_fourier.png)

![comparison with local polynomial regression](docs/assets/method_vs_lpr.png)

All seven figures are built by one command —
`python python/studies/make_method_figures.py` — and it also prints the numbers
that go into this text (the error table, patch degrees, pit centres, seam
clearances, cleaning counters) plus two self-checks: the mirror of the “elbow”
rule on the figure gives exactly the degrees the model chose, and the cleaning
mask matches a direct call to `build_cleaner`. The analysis of the numbers is in
§14 of [`docs/method.md`](docs/method.md).

Degree comparison on section 0 (the same model, but the degree is forced to be
equal for all patches; coefficients as in the document, polynomials + pit terms):

| Variant | Coeff. | max\|Δr\| to truth, mm | RMSE, mm |
|---|---|---|---|
| all patches deg 4 | 39 | 3.98e-01 | 8.48e-02 |
| all patches deg 6 | 53 | 2.31e-01 | 4.81e-02 |
| all patches deg 8 | 67 | 1.06e-01 | 2.44e-02 |
| all patches deg 10 | 81 | 5.89e-02 | 1.64e-02 |
| all patches deg 12 | 95 | 5.42e-02 | 1.34e-02 |
| all patches deg 14 | 109 | 4.87e-02 | 1.22e-02 |
| **PAPPA: degree per patch** (4–12) | **65** | **5.42e-02** | **1.51e-02** |

An honest reading: at a similar budget the adaptive degree beats any uniform one
by a factor of two (deg 8: 67 coeff., 1.06e-01 versus 5.42e-02), and in max\|Δr\|
it is no worse than a uniform deg 12 at 95 coefficients; strictly more accurate
than the adaptive one is only deg 14 (4.87e-02) — but that is 109 numbers instead
of 65 and a least-squares fit on `x^14` in every patch. Cleaning, in turn, is not
“cosmetics”: without it the same model gives max\|Δr\| 0.124 mm and degrees
`[6, 8, 4, 8, 4, 8, 4]` instead of 0.054 mm and `[8, 10, 4, 12, 4, 12, 4]`.

## Status and scope

Intended application: in-process geometry of **bodies of revolution** measured by
non-contact (laser/optical) scanning in sections along the axis, where a narrow
deep defect (pit, crack) is either smeared by low-order global bases or forces a
very high degree on a fixed-degree patch grid. Here the degree adapts per patch
and a pit can be carried by an explicit basis term.

* verified **on synthetic data** (10 sections × 6000 points, R = 15 mm, three
  cracks 4–6° wide, 2 % injected outliers) and on the conformance vectors —
  measurements from a real scanner are **not** claimed yet;
* known limitations: the degree ceiling and conditioning, and the overfitting
  spike at high degrees; the “legacy” methods are kept only to reproduce older
  measurements;
* feasibility on microcontrollers (Arduino/Cortex-M/ESP32) is measured and
  described in [`docs/embedded.md`](docs/embedded.md) (Russian only) — per-board
  verdicts and per-phase cost are there.

> Status: **work in progress**, source-available (see the licence below).

---

## The idea in one paragraph

Divide the domain into `N` overlapping sectors. Fit an independent low-order
polynomial over each sector; the sector’s residual behaviour (RMSE on the training
window, “elbow” rule) picks its degree. Reconstruct the profile as a normalized
smoothstep-weighted blend (partition of unity) of the patches, so the result is
continuous, C¹, and locally faithful without global ringing.

## Quick start (5 commands)

The data is not stored in the repository: the synthetic CSV is reproduced by the
generator (`seed 42`, 10 sections × 6000 points, R = 15 mm, three cracks). It has
been checked that the generated file matches bit-for-bit the one all the results
below were computed on (the `sha256` matched).

```bash
# 0) data (the file is written to the current directory -> run inside python/)
cd python && python generator/generate_data_crack_many.py && cd ..

# 1) reference: CSV -> sample folder samples/synthetic_sphere (needs Python with numpy)
python python/studies/build_sample.py --name synthetic_sphere

# 2) any port writes the same folder on its own (example — R)
powershell -File r/build_r.ps1 -Pipeline

# 3) numerical comparison of the port against the reference: contour, degrees, pits (code 0/1/2)
python python/studies/verify_port.py --py-dir samples/synthetic_sphere --cpp-dir samples/synthetic_sphere_r

# 4) everything at once over all implementations: vectors + tests, and with -Full the pipeline and the comparison too
powershell -File verify_all.ps1 -Full

# the same without PowerShell (Linux / macOS / Git Bash) — the same set of gates:
python3 tools/verify_all.py --full
```

## How correctness is verified

```powershell
powershell -File verify_all.ps1            # build + conformance vectors + per-port tests
powershell -File verify_all.ps1 -Full      # + every port's pipeline and numerical comparison
powershell -File verify_all.ps1 -List      # what exactly is launched (port, command)
powershell -File verify_all.ps1 -Only r,julia
```

The same thing **without PowerShell** — for Linux, macOS and Git Bash:

```bash
python3 tools/verify_all.py            # build + conformance vectors + per-port tests
python3 tools/verify_all.py --full     # + every port's pipeline and numerical comparison
python3 tools/verify_all.py --list     # the port table and the exact commands
python3 tools/verify_all.py --only r,julia
python3 tools/verify_all.py --os posix --dry-run   # what the commands would be on POSIX (nothing runs)
```

`tools/verify_all.py` (stdlib Python 3, no dependencies) is the same set of gates,
with the same return codes and the same `SKIP` for missing toolchains, but the
commands are chosen by OS: `gcc-release` instead of `msvc-release`, `python3`
instead of `python`, `:` instead of `;` in the classpath, `dotnet pappa.dll`
instead of the apphost, `swift build`/`cargo build --release`, and so on. Windows
stays on `verify_all.ps1` (it is the primary and fully exercised entry point); the
driver is for the places where the PowerShell scripts do not apply — they contain
MSVC presets, `C:\msys64` and Excel COM. The only implementation that is
Windows-only by nature is `vba/`: VBA 7 lives inside Excel, so POSIX runs have no
row for it.

A run of the driver on the developer machine (Windows, all toolchains, `--full`):
**18 OK, 0 SKIP, 0 FAIL**, exit code 0 — the same as `verify_all.ps1 -Full`.

A port whose toolchain is not installed is marked `SKIP` with a reason and is not
counted as a failure: the repository must be readable on a machine that has 2–3 of
the 18 toolchains in the table below.

The result on the developer machine (Windows, 2026-09-25: all toolchains
available, `0 SKIP`, `0 FAIL`, exit code 0):

| Implementation | Vectors (`spec/conformance`) | Own tests | Pipeline + comparison with the reference |
|---|---|---|---|
| `python/` (reference) | — | — | builds `samples/synthetic_sphere` |
| `cpp/` | `ctest -R conformance_vectors` | `ctest` (including `port_parity_python`) | 10/10 sections, max Δr 1.34e-12 mm |
| `c/` | `python/studies/check_c_port.py` | `check_c_pipeline.py` | 10/10, 1.34e-12 |
| `go/` | `go run ./cmd/conformance` | `go test ./...` | 10/10, 1.34e-12 |
| `js/` | `node cmd/conformance.js` | `node --test` | 10/10, 1.34e-12 |
| `java/` | `pappa.SelfTest` | `pappa.SelfTest` | 10/10, 1.34e-12 |
| `kotlin/` | `pappa.SelfTest` | `pappa.SelfTest` | 10/10, 1.34e-12 |
| `rust/` | `bin/conformance` (cargo, offline) | `cargo test` | 10/10, 1.34e-12 |
| `pascal/` | `bin/conformance.exe` | `bin/selftest.exe` | 10/10, 1.38e-12 |
| `fortran/` | `build_fortran.ps1 -Vectors` → `bin/conformance.exe` (gfortran 10.3, no external libraries: own JSON/CSV/statistics) | `build_fortran.ps1 -Test` → `bin/selftest.exe` (JSON tests + vectors + smoke fit) | 10/10, 1.35e-12 |
| `swift/` | `ConformanceCLI` | `swift test` | 10/10, 1.34e-12 |
| `julia/` | `bin/conformance.jl` | `test/runtests.jl` | 10/10, 1.34e-12 |
| `r/` | `bin/conformance.R` | `tests/runtests.R` | 10/10, 1.36e-12 |
| `csharp/` | `pappa.exe conformance` (.NET 10, 0 NuGet packages) | `pappa.exe selftest` (vectors + smoke fit + document round-trip) | 10/10, 1.34e-12 |
| `fsharp/` | `pappa conformance` (.NET 10 / F# 10, 0 NuGet packages; without PowerShell: `bash fsharp/build_fsharp.sh --vectors`) | `pappa selftest` (vectors + smoke fit + document round-trip) | 10/10, 1.34e-12 |
| `octave/` | `bin/conformance.m` (Octave 11, core only: own JSON/CSV/statistics) | `bin/selftest.m` (vectors + smoke fit + document round-trip) | 10/10, 1.34e-12 |
| `vba/` | `powershell -File vba/build_vba.ps1 -Vectors` (Excel 16 / VBA 7 via COM: the modules are imported into a workbook) | `-Test` → `PappaSelftest` (49 checks: vectors + units + smoke fit + document round-trip) | 10/10, 1.37e-12 |
| `spec/` | `python spec/check_schema.py` | — | 242 document files against the schemas |

Here Δr is the maximum deviation of a port's contour from the reference on a
uniform grid of 6000 points in a section. The tolerance is `1e-6` mm, so the
actual deviation is six orders of magnitude below it: the match is machine-exact,
not “similar”. Protocol, tolerances and porting pitfalls:
`spec/conformance/README.md`, §11 of [`docs/method.md`](docs/method.md).

## Repository layout

| Path | Purpose |
|------|---------|
| `python/` | **Reference**: the `pappa/` package (`core`, `io`, `analysis`, `viz`, `report`); entry points in `studies/` (build a sample, generate vectors, verify a port), `demos/`, `generator/` (data); `research/` (rejected hypotheses and finished studies), `deprecated/` (archive, reports included) |
| `spec/` | Contract: `pappa.schema.json`, `sample.schema.json`, `check_schema.py` (executable schema check), `conformance/` — golden vectors and tolerances |
| `docs/` | `method.md` — formal description of the method (also `method.ru.md`); `embedded.md` — feasibility on microcontrollers; `assets/` — figures for the README and presentations |
| `samples/` | Sample folders (`sample.json` + one document per section + `report/verify.json`) — generated, not committed |
| `cpp/` | C++17 (CMake): full pipeline + `ctest` (vectors and the parity test) |
| `c/` | C99: dependency-free core (suitable for an MCU) + host pipeline; checked by `check_c_port.py` / `check_c_pipeline.py` |
| `go/` | Go: full pipeline + `go test ./...` |
| `js/` | JavaScript (Node, ESM, no packages): pipeline + `node --test` |
| `java/` | Java (JDK, `javac`, own mini-JSON): pipeline + `pappa.SelfTest` |
| `kotlin/` | Kotlin (`kotlinc` from Android Studio): pipeline + `pappa.SelfTest` |
| `rust/` | Rust (cargo, **no crates**, offline build): pipeline + `cargo test` |
| `pascal/` | Free Pascal (FPC 3.2, RTL only): pipeline + `selftest` |
| `fortran/` | Fortran 2018 (gfortran, **no external libraries**: own JSON/CSV/statistics): pipeline + `bin/selftest.exe` |
| `swift/` | Swift (SwiftPM, no packages; on Windows `SDKROOT` is required): pipeline + `swift test` |
| `julia/` | Julia (the `Pappa` package, stdlib only, offline): pipeline + `test/runtests.jl` |
| `r/` | R (**base R only**, no packages: own JSON/CSV/statistics): pipeline + `tests/runtests.R` |
| `csharp/` | C# (.NET 10, **no NuGet packages**: own JSON/CSV/statistics): one exe with the commands `conformance` / `selftest` / `pipeline` |
| `fsharp/` | F# (.NET 10, **no NuGet packages**: own JSON/CSV/statistics): the same exe with `conformance` / `selftest` / `pipeline`; builds both via PowerShell (`build_fsharp.ps1`) and via POSIX shell (`build_fsharp.sh`) |
| `octave/` | GNU Octave (**core only**, no `io`/`statistics` packages: own JSON/CSV/statistics): pipeline + `bin/selftest.m` |
| `vba/` | VBA 7 (Microsoft Excel 2016+, **no add-ins and no COM objects**: own JSON/CSV/statistics, a single Win32 call for UTC): `.bas` modules imported into a workbook via COM, `build_vba.ps1` with the modes `-Vectors` / `-Test` / `-Pipeline` |
| `legacy/` | Legacy methods (detector v3, manual cleaner) — only to reproduce older measurements |
| `verify_all.ps1` | One command: the gates of every implementation (vectors, tests, pipeline, comparison) |
| `tools/` | `verify_all.py` — the same gates without PowerShell (Linux/macOS/Git Bash): the same port table, commands chosen by OS; see `tools/README.md` |

## Porting to a new language

The order that has been exercised on 16 implementations:

1. read [`docs/method.md`](docs/method.md) — §11 lists the pitfalls real ports
   tripped over (half rounding, residual sign, indexing, coefficient order,
   percentiles, ring windows, number formatting);
2. compare the document structure against `spec/pappa.schema.json` and validate it
   with `python spec/check_schema.py <port folder>`;
3. pass `spec/conformance` (4 vectors: a model without pits, a model with pits,
   the detector, cleaning) — your own `conformance` utility, code 0/1/2;
4. implement the pipeline (`--input/--out-dir/--name`) and compare the sample
   folder against the reference: `python python/studies/verify_port.py`;
5. add your own tests/`selftest` and a `build_<language>.ps1` with the modes
   `-Vectors`, `-Test`, `-Pipeline` — then `verify_all.ps1` picks the port up (one
   row in the port table).

## Citation

The file [`CITATION.cff`](CITATION.cff) — GitHub will show the “Cite this
repository” link automatically.

## Documentation languages

English is the canonical language: `README.md`, `docs/method.md`. Translations
live next to their original with a language suffix — `README.ru.md`,
`docs/method.ru.md` (`<name>.<lang>.md`, ISO 639-1). Every localized file starts
with a language switcher line and must keep the section structure of the original;
`python tools/check_docs_i18n.py` checks exactly that. Adding a language means
adding `README.<lang>.md` and (optionally) `docs/method.<lang>.md` — nothing else
in the repository changes.

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
