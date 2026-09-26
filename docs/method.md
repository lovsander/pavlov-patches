# The PAPPA method — formal description

**English** · [Русский](method.ru.md)

PAPPA (**P**iecewise **A**daptive **P**oly-**P**atch **A**pproximation, aka “Pavlov
patches”) is a compact parametric model of a one-dimensional signal: a closed
(periodic) profile `r(φ)` is described by a set of **overlapping local polynomial
patches** with an **adaptive degree**, blended by a **normalized smoothstep
partition of unity** (continuous, C¹ — no derivative jump at the seams), in a
**normalized local coordinate** `x = Δ/half_train ∈ [-1, 1]`. Narrow deep defects
(pits, cracks) can be carried by **additional basis terms** — tapered Gaussians —
instead of a forced rise of the polynomial degree.

This description is documented in `docs/README.md`; the serialization contract is
`spec/`, the numerical expectations are `spec/conformance/`, the language
implementations are in the port folders.

---

## 1. Notation

| Symbol | Meaning |
|--------|---------|
| `φ` | angle along the closed profile, ° (one turn 0…360, `φ = 360 ≡ 0`) |
| `r(φ)` | measured radius (mm) — the input of the method |
| `N` | number of patches (default `7`) |
| `i` | patch index, `0 … N-1` |
| `sector = 360 / N` | angular width of a sector, ° |
| `half_sector = sector / 2` | half a sector, ° |
| `c_i` | patch centre, ° |
| `half_train = half_sector + overlap_train` | half-window of TRAINING, ° (default `overlap_train = 15`) |
| `half_use = half_sector + overlap_use` | half-window of USE (blending), ° (default `overlap_use = 5`) |
| `d = |Δ|` | angular distance to the patch centre along the ring, ° |
| `x = Δ / half_train` | local patch coordinate, `[-1, 1]` (`coord_mode = normalized`) |

The key point: **training is wider than use** (`half_train > half_use`). A patch
sees more data than it is “allowed” to draw, so at the edge of its use zone it
rests on data rather than on extrapolation.

## 2. Patch layout

```
sector     = 360 / N
half_sector= sector / 2
c_i        = (i * sector + half_sector + phase_deg) mod 360      (i = 0 … N-1)
```

`phase_deg` (default `24.75`) rotates the whole grid: the nodes (the seams between
sectors) are moved away from the zones where the measurement is known to be hard
(from cracks, for instance: a seam is the only place where the model rests on no
fresh patch centre). `phase_deg = 0` is the historical behaviour “the first sector
starts at zero”. The layout is ONE for the whole body (not a private phase per
pit) — that is simpler and more reproducible, and fitting the phase buys nothing.

A check on synthetic data (10 sections, the `band` detector — §8): the minimum
“pit centre → nearest seam” clearance over all sections is **+9.92°** at
`phase_deg = 24.75°` and **+0.19°** at `phase_deg = 0`, where the seam comes within
2° of a crack in 5 sections out of 10 (inside the crack itself — never). That is
the whole point of the shift: the seam is not “rescued” from a crack, it is given
margin. The figure and the per-section table are in §14,
`docs/assets/method_star.png`.

The angular distance is computed along the ring:

```
Δ(φ, c) = wrap180(φ - c)        wrap180(u) = ((u + 180) mod 360) - 180
d       = |Δ|
```

The training mask of patch `i`: the points for which `d ≤ half_train` (the ring is
unwrapped to ±360°, so the window crosses 0°/360° correctly).

## 3. The patch basis

1. **Polynomial** in the normalized local coordinate:

   ```
   p_i(x) = Σ_{k=0..deg_i} a_ik · x^k
   ```

   `deg_i` is an **even** degree (`deg_min … deg_max`, default `4 … 14`). The
   normalization `x = Δ/half_train` is not cosmetics: at `deg = 14` in raw degrees
   the least-squares matrix is poorly conditioned, in `[-1, 1]` it is fine.

2. **Pit feature terms** (optional, §5): `Σ_j amp_ij · g(|Δ - dx_ij|)` — a tapered
   Gaussian centred at `dx_ij` (the pit angle minus the patch centre).

The coefficients `a_ik` are stored in the document **in descending order of degree**
(`coefs[0]` is the `x^deg` term, `coefs[deg]` is the free term; evaluation is
Horner from left to right). This is the order of `numpy.polyfit`/`polyval` — every
implementation must read the array exactly like that (in the C port it is
`pp_polyval`).

The legendary `amplitude_scale` field (`180.0`) is kept for format compatibility
only: in the past the degree was chosen from it, now it does NOT affect the degree
choice (it remains a reference metric in the document).

## 4. Choosing the degree of a patch: the RMSE “elbow” rule

The degree is chosen **from the residuals on the training window** (not from the
amplitude spread: that measure reflects size, not shape complexity, so it
underestimated narrow deep pits and overestimated wide shallow sectors).

```
input: angles, radii, center c_i, half_train
mask   = d ≤ half_train                                  # ring, ±360°
x      = wrap180(angles - c_i)[mask] / half_train        # ∈ [-1, 1]
y      = radii[mask]
if |x| < 5:  degree = deg_min; RMSE metrics = 0

for deg = deg_min, deg_min+2, …, deg_max:                # EVEN degrees only
    a_deg   = argmin ‖V(x)·a - y‖₂                       # least squares (numpy.polyfit)
    rmse_deg= sqrt(mean((V(x)·a_deg - y)²))
rmse_best = min rmse_deg;  best = the corresponding degree

limit    = rmse_best · (1 + deg_elbow_tol)               # deg_elbow_tol = 0.05
deg_i    = the smallest even deg with rmse_deg ≤ limit
           (safety net: if there is none — best)
```

The idea: take the **cheapest** degree that is already nearly as good as the best
available one (within 5 %). That is why “busy” sectors (a pit near the edge, an
inflection) take 10–14 and smooth ones take 4–6, and the decision is made locally,
inside the patch's own window, not globally over the profile.

The decision metrics go into the document: `metrics.rmse_selected_mm`,
`metrics.rmse_best_mm`, `metrics.n_train_points`, `metrics.deg_elbow_tol`.

**The document is checkable** (`validate_model`): the degree must be even and
inside `deg_min … deg_max`, and `rmse_selected_mm ≤ rmse_best_mm · (1 + tol)` —
that is, the document proves by itself that the degree followed the rule rather
than an eyeball.

What the rule gives in practice (section 0, the patch window is ≈ 1337 points out
of 5882, the noise level in the window is ≈ 0.12 mm): smooth patches take
`deg_min = 4`, “busy” ones take 8, 10 and 12; the RMSE(deg) curves, the
`best·(1.05)` thresholds and the price of the choice are in §14 and in
`docs/assets/method_degrees.png`. The limits matter: the rule optimizes the
**budget**, not absolute accuracy — a uniform `deg = 14` on all patches gives a
smaller error, but for 109 coefficients instead of 65 and with a least-squares fit
on `x^14` in every window.

## 5. The pit feature: a tapered Gaussian in the patch basis

Purpose: a narrow deep pit 1–6° wide needs a high polynomial degree if a polynomial
has to carry it. Instead it is described by a **separate basis term** — a Gaussian
whose shape is fixed explicitly.

Parameters (defaults): `sigma_deg = 3.0`, `core_sigma = 2.0`, `window_sigma = 3.2`,
`pit_min_amp = 3e-3` mm, `tapering = true`.

The shape as a function of the angular distance to the pit centre `d` (°):

```
core   = core_sigma  · sigma_deg = 6.0°      (inside — weight 1: the bottom stays exact)
window = window_sigma· sigma_deg = 9.6°      (at the boundary — exactly 0)

g(d) = 1                                    , d ≤ core
     = s(t),  t = (window - d)/(window - core), s(t) = t²(3 - 2t)
                                            , core < d < window
     = 0                                    , d ≥ window
```

The core is the same Gaussian `exp(-d²/(2σ²))`, while the “tails” are replaced by a
smoothstep descent: it gives a **zero derivative at both ends**, so when the term
reaches zero the basis does not kink (without it there are visible steps at 3.2σ).
Inside the core (≤ 2σ) the shape coincides with a pure Gaussian, so the pit bottom
is described exactly.

How a term enters a patch:

```
for every common pit j with centre m_j:
    if |wrap180(m_j - c_i)| ≤ window_sigma · sigma_deg:      # window 9.6°
        add a basis column:  g(|Δ - (m_j - c_i)|)
```

(in normalized patch units that is `sigma_norm = sigma_deg / half_train`,
`dx_norm = dx_deg / half_train`; model evaluation uses the same.) The least-squares
problem is solved on the extended basis `[polynomial with deg+1 columns | Gaussian
columns]`.

**Cut-off of invisible pits:** after the solve a Gaussian is dropped if
`max |amp_j · g|` over the patch training window is below
`pit_min_amp = 3e-3` mm — otherwise every touch of the window would spend a
parameter and spoil the conditioning.

The pit layout is shared by the whole body (one phase), pit centres live in
`global.pit.centers_deg`; a patch stores only `{dx_deg, amp}` in
`patches[i].pit_terms`.

## 6. Blending: a normalized smoothstep partition of unity

The model is not a “pick the nearest patch” but a **weighted average** of
overlapping patches with weights that form a partition of unity:

```
w_i(φ) = 1                                          , d ≤ half_sector
       = s(t), t = 1 - (d - half_sector)/(half_use - half_sector)
                                                    , half_sector < d ≤ half_use
       = 0                                          , d > half_use

r̂(φ) = Σ_i w_i(φ) · v_i(φ) / Σ_i w_i(φ)
```

where `v_i` is the value of the patch (polynomial + its Gaussian terms) at `φ`.

The properties that decided in favour of smoothstep:

* **partition of unity** — the sum of the weights is normalized, so a constant is
  reproduced exactly and the seams do not “settle” (no error accumulation around
  the ring);
* **C¹** — `s(t) = t²(3-2t)` has a zero derivative at both ends, so at every
  boundary of the use zone (`d = half_sector`) and at the outer edge
  (`d = half_use`) the weight arrives and leaves smoothly — there is no derivative
  jump;
* **locality** — far from a patch centre its contribution is strictly zero, so an
  outlier in one sector does not pull the profile in its neighbours.

Because `half_train > half_use`, at the edge of the use zone a patch rests on
training data rather than on extrapolation — that is the reason for “training wider
than use”.

## 7. Preprocessing 1: automatic outlier cleaning (iqr)

The order in the pipeline is **cleaning first, then the pit detector and the
model** (otherwise outliers eat both the degree choice and the pit amplitudes).

```
baseline = moving MEDIAN along the ring, window = window_points(baseline_deg = 1.0)
res      = radii - baseline                     # residual: the shape is removed
center   = median(res)
spread   = IQR(res) = P75(res) - P25(res)
denom    = spread if spread > 1e-12 else 1.0                 # in mm (!)
severity = |res - center| / denom
mask     = severity > iqr_k                                  # iqr_k = 3.0 (Tukey fences)

safety net: if more than cap = floor(0.5 · n) points are flagged, keep the
            cap “heaviest” ones (by severity), the rest are not outliers
```

The median runs along the **ring** (the profile is closed: a window sticking out
past 360° wraps to 0°), and the window is an odd number of points (§11). The `iqr`
method is the standard one; the reference also has others (`gmm`, `hampel`, a
manual legacy cleaner), kept for research and comparisons.

A known property (deliberate): on perfectly smooth data `IQR(res) → 0`, `denom`
hits its `1.0 mm` floor, and the cleaner effectively switches itself off (a 3 mm
threshold). For noisy data that does not get in the way, for “sterile” data it does
(see `spec/conformance/README.md`).

The price of skipping the cleaning (section 0, 2 % injected outliers): `iqr`
removes 118 points out of 6000 (1.97 %, threshold 0.3902 mm at
`IQR(residual) = 0.1301 mm`), after which the model takes the degrees
`[8, 10, 4, 12, 4, 12, 4]` and gives max|Δr| 0.0542 mm / RMSE 0.0151 mm. The same
model **on dirty points**: the degrees “drift” to `[6, 8, 4, 8, 4, 8, 4]`,
max|Δr| 0.124 mm, RMSE 0.0313 mm — 2.3 and 2.1 times worse. The figure is in §14,
`docs/assets/method_cleaning.png`.

## 8. Preprocessing 2: the pit detector (band, two-scale median)

The idea: a pit is a structure that a narrow median “sees” and a wide one does not.

```
narrow = median along the ring, window = window_points(1.0°)    # narrow
wide   = median along the ring, window = window_points(10.0°)   # wide
band   = |narrow - wide|
band   = moving MEAN along the ring, window = window_points(2.0°)   # smoothing
s      = robust_sigma(band) = 1.4826 · MAD(band)
ind    = band / s if s > 1e-12 else 0                     # dimensionless, “in MADs”
```

Zones and centres:

```
mask  = ind > k                                            # k = 5.5
zones = consecutive runs of mask, boundaries angles[i] ∓ step/2,
        where step = the median grid step; the ring closes (a zone reaching
        360° and starting at 0° is ONE zone);
        zones shorter than min_zone_deg = 2° are dropped
pit centres = the middles of the zones
```

The centres found are `global.pit.centers_deg` — the input of the feature (§5).

## 9. The “sample folder” pipeline

The full path from a measurement to a document (implemented in the reference and in
every port):

```
CSV (section_id, height_mm, angle_deg, radius_mm [, radius_ideal_mm])
  │
  ├─ for every section:
  │    1. outlier cleaning           (auto iqr, §7)        → y_clean, n_outliers
  │    2. pit detector on y_clean    (band, §8)            → pit centres, zones
  │    3. model: layout (§2) + degrees (§4) + feature (§5) → patches
  │    4. control RMSE on a uniform grid of 6000 points against the
  │       ideal profile (radius_ideal_mm) — a report metric, not a training one
  │
  └─ output: samples/<name>/sample.json + sections/<NN>.pappa.json
```

Default parameters (single source — `python/pappa/core/pit_feature.py`:
`MODEL_DEFAULTS`, `PIT_DEFAULTS`, `DETECTOR_DEFAULTS`):

| Parameter | Value |
|----------|----------|
| `n_patches` | 7 |
| `phase_deg` | 24.75 |
| `deg_min … deg_max` | 4 … 14 (even) |
| `deg_elbow_tol` | 0.05 |
| `overlap_train` / `overlap_use` | 15° / 5° |
| `coord_mode` | `normalized` |
| `sigma_deg`, `core_sigma`, `window_sigma` | 3.0°, 2.0, 3.2 |
| `pit_min_amp`, `tapering` | 3e-3 mm, `true` |
| cleaning | `auto` / `iqr`, `baseline_deg = 1.0`, `iqr_k = 3.0` |
| detector | `band`, windows 1° / 10° / 2°, `k = 5.5`, `min_zone_deg = 2°` |

## 10. Serialization and what it guarantees

* **`sections/<NN>.pappa.json`** (format `pappa v2.0`) — one document per section:
  `global` (units, layout, degree policy, the `pit` block) + `patches[]`
  (`center_deg`, `degree`, `coefs`, `metrics`, `stats`, `pit_terms`) +
  `statistics`. Schema: `spec/pappa.schema.json`.
* **`sample.json`** (format `pappa-sample v1.0`) — the sample manifest: units,
  `config` (every parameter of the method), the list of sections with relative
  paths, `input.csv` + `sha256` (the trace of the data it was trained on).
* **`report/verify.json`** — the numeric report of the port-versus-reference check.

A document is not “a set of points” but a description of the method: any language
reproduces the contour from `coefs` + `pit_terms` + the layout, without access to
the original measurements.

## 11. The numerical side: tolerances and parity pitfalls

**Tolerances** (a single contract, `spec/conformance/README.md`):

| What | Tolerance |
|-----|--------|
| contour `r̂(φ)` | `1e-6` mm — the main criterion (that IS the method) |
| patch coefficients | `|Δc| ≤ max(1e-8, 1e-9·|c|)` — an absolute `1e-9` is wrong: different correct least-squares solvers (SVD in numpy, Householder QR in the ports) diverge by ~1e-9 |
| detector, cleaning | the fraction of points (`frac = 0.02`) — a zone right at the threshold may wobble by one point |
| pit centres | `1e-6°` |

**Pitfalls when porting to a new language** (collected from 16 ports; check them, not
“similar-looking code”):

1. **Indexing.** Arrays in the document are 0-based; in 1-based languages the window
   boundary breaks (`≤ n` versus `< n`) — check it on the CSV, not on a small vector.
2. **Halfway rounding.** “To even” (banker's): Python 3, R, VBA `Round`, Julia
   `round`, F# `round`, C# `Math.Round`, `Math.rint` in the JVM ports,
   `math.RoundToEven` in Go. “Away from zero”: C/C++ `round`, Fortran `nint`,
   Octave `round(2.5) == 3`, Go `math.Round`, Rust `f64::round`, Swift
   `.rounded()`; “towards +∞” — JS `Math.round`. In FPC `Round` is documented as
   banker's, but the port does not rely on it (its own `RoundTiesEven`), and in
   Octave JSON integers are written via `printf('%.0f')`, which rounds a half TO
   EVEN (the port has a dedicated test for that). It affects the number of window
   points (`window_points`) and the degree choice.
   On the .NET myth: `Math.Round(x)` without a second argument already sends a half
   TO EVEN (`Math.Round(2.5) == 2`, `round 2.5 = 2` in F# — verified), so
   `MidpointRounding.ToEven` is written there for readability, while the opposite
   cases have to be emulated (`f64::round` in Rust, `math.Round` in Go, `round` in
   C). In Octave `round(2.5) == 3`, but `printf('%.0f')` rounds a half TO EVEN —
   that is what writes the JSON integers (a dedicated test in the port).
3. **Sign of the remainder.** In Python `%` is never negative (floor division), in
   C/C#/JS it takes the sign of the dividend. Ring differences (`wrap180`, `d`)
   need floor semantics. Octave has two operators: `mod` (floor, like Python) and
   `rem` (dividend sign) — only `mod` is usable.
4. **Order of coefficients** — DESCENDING degree (`coefs[0]` is the `x^deg` term,
   Horner from left to right).
5. **Median and percentiles.** The median of an even set is the mean of the two
   middle ones; `P25/P75` is linear interpolation (`numpy.percentile`, “type 7”),
   not “the nearest ranked element”.
6. **Window in terms of the angle.** `w = int(round(span_deg / step))`, then odd
   (`| 1`), minimum 3, maximum `n` (`n-1` when `n` is even); the step is the median
   of the positive angle differences.
7. **Closure.** Every filter runs along the ring; a window sticking out past the
   boundary must wrap, not be clipped.
8. **`Σw` and NaN.** If the sum of the weights is zero (a degenerate layout) — that
   is `NaN`, not 0.
9. **Number format in JSON.** The shortest round-tripping representation is needed
   (the R port has a search for it, Python uses `repr`). `%.17g` also passes the
   comparison, but documents become unreadable and “dirty” in diffs.
10. **CSV.** BOM, CRLF, spaces; the “are there enough columns” check must be
    `count < needed` (in 1-based languages it is easy to be off by one).
11. **JSON key order.** It must match the reference (a byte-wise diff of the
    documents is a convenient first test); `null` (for instance
    `"detector": null`) must survive writing — in R `x[[k]] <- NULL` deletes the
    element, `x[k] <- list(v)` is required.
12. **Machine locale.** Numbers in documents and CSVs must use a dot: on the JVM
    `Locale.setDefault(Locale.ROOT)` helps, in .NET
    `<InvariantGlobalization>true</InvariantGlobalization>` in the `.csproj` plus
    `CultureInfo.InvariantCulture` in parsers and formatters, otherwise `ru-RU`
    yields “8,73e-11” and a comma as the decimal separator.
13. **Booleans in JSON.** `true`/`false` — lowercase only, while
    `StringBuilder.Append(bool)` in C# prints `True`/`False` (in JS `String(true)`
    is fine, in Pascal there is a custom `BooleanToString`). The error is caught by
    `python spec/check_schema.py`: values are compared against the schema.
14. **A filter window is not only its width, it is also its alignment.** In 1-based
    languages the ring window is written as `mod(i − h − 1 + (0:w−1), n) + 1`: a
    lost “−1” shifts the median filter and the smoother by one point each, two in
    total. The detector vector catches it: the zones land 2° earlier than the
    reference (in the Octave port it also healed 5 “lost” cleaning outliers out
    of 9).
15. **Implicit expansion (Octave/MATLAB).** `1×k .* k×1` is not a shape error but a
    `k×k` matrix: in the back-substitution of the fit `sum(a(i, k:n) .* x(k:n))`
    silently returns a vector, and the assignment into a scalar blows up far from
    the actual mistake. Write `row * column` (or explicit shapes), not `.*` with
    mixed orientation.
16. **Value versus reference.** Where R was saved by its environment (pass by
    reference) and Julia by `mutable struct`, an Octave struct is COPIED:
    “mutators” must return the object (`m = model_fit(m, ...)`), and so must test
    counters (`[passed, failed] = check(...)`). A forgotten assignment breaks
    nothing visibly — the old state is simply used.
17. **An empty struct field.** `struct('f', {})` in Octave/MATLAB creates a 0×0
    ARRAY of structs (not a struct with an empty field), and touching the field
    fails with “Invalid call to numel”. An empty list in a field is
    `struct('f', {{}})`.
18. **A FIXED-length string travels into JSON with trailing spaces.** In languages
    with such strings (Fortran `character(len=N)`, Pascal `string[N]`) writing a
    field without `trim` gives `"coord_mode": "normalized      "`. A numeric
    comparison and a visual review of the document do not see it — only the strict
    loader fails (`coord_mode: expected 'normalized' or 'raw'`). Same place:
    padding a string with spaces IN A LOOP never terminates — for a fixed-length
    string `pad = trim(pad)//' '` does not grow `len_trim`, so the padding has to
    be built in a variable-length string (`repeat`).
19. **Path existence and hidden directories (VBA).** `Dir(path, vbDirectory)` does
    not return hidden directories (`C:\Users\<user>\AppData` is hidden), so the
    “does the directory exist?” check lied and `MkDir` was called on an existing
    directory — error 75 “Path/File access error”. Same place: for `Dir` with
    attributes a path with a trailing `\` gives error 52, while
    `Dir(path, vbDirectory)` also counts a plain file as a match. Existence is
    checked with `GetAttr` (the `vbDirectory` bit), absence — with errors 53/76.
    Separately: **Excel's working directory is `Documents`**, not the launch
    directory, so relative paths must be made absolute (otherwise the sample
    folder appears in “Documents”).
20. **Numbers and files in VBA.** `Format$`/`Str` print at most 15 significant
    digits (`1/3` gives `.333333333333333`), so a byte-wise round-trip of the
    document is unreachable; compare with a relative tolerance of `1e-14`;
    `NaN`/`Inf` do not exist in the language (`0/0` is error 11, overflow is error
    6), so a zero denominator is branched explicitly (in the port a zero sum of
    weights yields 0, as in C); `Open ... For Output` writes the file in ANSI
    (cp1251) — the port prints ASCII only, and non-ASCII strings go out as
    `\uXXXX`; in a Russian locale `Format$` emits a comma and `CDbl` on the string
    `1.5` gives error 13, so numbers are parsed via `Val`.
21. **Compilation order is part of the language (F#).** In F# a file sees only what
    is declared ABOVE it: no cyclic references between files, no forward
    declarations inside a file, types must precede the class that uses them.
    Therefore the `<Compile>` list in `.fsproj` is explicit
    (`EnableDefaultCompileItems=false`) — otherwise the SDK adds `*.fs`
    alphabetically and the build fails with “not defined”. Same place: F# has no
    `break`/`continue`/early `return` (loops are rewritten with flags: CLI argument
    parsing, the RMSE-elbow search), no auto-properties (`let mutable` +
    `member … with get() and set()`), and class members see each other only through
    the self-identifier (`member this.X`, not `member _.X`).
22. **`sprintf` and `ToString` look in different directions in .NET (F#).** In F#
    printf formats are culture-invariant (`sprintf "%f" 1.5` → `1.500000` even
    under `ru-RU`), while `ToString()`/`Parse()` are not (`1,5`). In C# it is
    exactly the opposite. Bottom line: `CultureInfo.InvariantCulture` is mandatory
    in every `ToString`/`Parse`, but not in `sprintf`. Separately:
    `sprintf "%.2e"` prints in the C style, with a THREE-DIGIT exponent
    (`8.73e-011`), whereas numpy/Python give `8.73e-11`; diagnostics comparable
    with the neighbouring ports need a custom format (`"0.00e+00"`).
    Same place (PowerShell, not F#): a function like `& $app …; return
    $LASTEXITCODE` captures the WHOLE application output into its own output, and
    the return-code check lies — it is more reliable to assemble the command in an
    array and read `$LASTEXITCODE` directly.

Acceptance of a port: all `spec/conformance` vectors inside the tolerances **and**
the sample folder matching the reference numerically (`verify_port.py`), plus your
own tests/`selftest`.

## 12. How it is checked with one command

```powershell
powershell -File verify_all.ps1            # build + vectors + tests of every port
powershell -File verify_all.ps1 -Full      # + every port's pipeline and numeric comparison
powershell -File verify_all.ps1 -List      # what exactly is launched
```

The same without PowerShell (Linux/macOS/Git Bash) — `tools/verify_all.py` on
stdlib Python 3: `python3 tools/verify_all.py --full`. It is not a “second
verifier”: it has the same port table, the same gates and the same exit codes, but
the commands are chosen by OS (`gcc-release` instead of `msvc-release`, `python3`
instead of `python`, `:` instead of `;` in the classpath, `dotnet pappa.dll`
instead of the apphost). `--os posix --dry-run` prints the POSIX commands without
running anything, `--list` prints the exact commands of the current OS. There is no
`vba` row in a POSIX run: VBA 7 lives inside Excel, and Excel is Windows-only.

Ports whose toolchain is missing on the machine are marked `SKIP` and are not
counted as failures.

## 13. Where things live (a map of the Python reference)

| File | Role |
|------|------|
| `python/pappa/core/patch_approximator.py` | layout, the “elbow” rule, least squares, blending (§2–§4, §6) |
| `python/pappa/core/pit_feature.py` | default parameters, the assembly point `build_model`, the Gaussian shape (§5) |
| `python/pappa/core/signal_tools.py` | MAD/robust sigma, IQR, ring windows, moving median and mean |
| `python/pappa/core/outlier_cleaner.py` | automatic cleaning (`iqr`/`gmm`/`hampel`) and the legacy manual mode (§7) |
| `python/pappa/analysis/zones.py` | the `band` detector and the zones (§8) |
| `python/pappa/analysis/layout.py` | `section_crack_zones` — per-section zones for the pipeline |
| `python/pappa/core/crack_detector.py` | the LEGACY v3 detector (detailed − coarse), history only |
| `python/pappa/io/model_file.py` | writing/reading/validating `.pappa.json` (§10) |
| `python/pappa/io/sample_store.py` | the sample folder: manifest, verification report |
| `python/studies/build_sample.py` | the “CSV → sample folder” pipeline (§9) |
| `python/studies/make_conformance.py` | generation of the `spec/conformance` vectors |
| `python/studies/verify_port.py` | numeric comparison of a port against the reference |
| `python/studies/make_method_figures.py` | the figures of the method (patches/weights, the “star” layout, degree selection, cleaning), the detector, the comparisons with Fourier and LPR + the numbers for this document (§14) |

## 14. Figures: the method, the layout, the degree, the cleaning, the detector and the comparisons

All the figures are built by ONE script — `python/studies/make_method_figures.py`
(only numpy + matplotlib + the reference itself). It also prints the numbers given
below, so the text and the figures cannot drift apart. Every comparison method is
trained on the same CLEANED points of the same section and evaluated on one 0.25°
grid against the generator's truth (`radius_ideal_mm`) — otherwise the comparison
would be about noise, not about the method. The script also prints two self-checks:
a local mirror of the “elbow” rule yields exactly the degrees the model chose, and
the cleaning mask matches a direct call to `build_cleaner`.

| Figure | What it shows |
|---|---|
| `docs/assets/method_star.png` | the “star” layout: radial centres, the seams at `phase_deg = 24.75°` and at `0`, the training and use windows, the detector's pits; in polar coordinates — the petals of the weights and the “star” polygon (rays = centres, valleys = seams) |
| `docs/assets/method_degrees.png` | the “elbow” rule: RMSE(deg) on each patch's window, the `best·(1 + 0.05)` threshold, the selected degree; on the right — cost versus error for a uniform degree 4…14 and for the adaptive one |
| `docs/assets/method_cleaning.png` | automatic `iqr` cleaning: kept and discarded points, the “abnormality” of points versus the threshold, and the same model trained without cleaning |
| `docs/assets/method_patches.png` | the method “from the inside”: 7 patches and their degrees, the smoothstep weights (normalized blending: Σ of weights is 1…2 in the overlap, the contour is divided by Σ), the error around the ring |
| `docs/assets/method_detector.png` | the `band` detector: the indicator in MADs, the threshold 5.5, the zones found and their middles |
| `docs/assets/method_vs_fourier.png` | PAPPA against a truncated Fourier series (4/6/12/24 harmonics) |
| `docs/assets/method_vs_lpr.png` | PAPPA against LPR with a fixed window (±2° degree 1, ±5°/±10° degree 2) |

Section 0: 5882 points after automatic cleaning, a 0.25° grid, three pits (90.30°,
200.25°, 314.79°), patch degrees `[8, 10, 4, 12, 4, 12, 4]`.

| Method | Coeff. | max\|Δ\| to truth, mm | RMSE, mm |
|---|---|---|---|
| Fourier-4 | 9 | 8.45e-01 | 2.18e-01 |
| Fourier-6 | 13 | 6.59e-01 | 1.80e-01 |
| Fourier-12 | 25 | 3.21e-01 | 7.49e-02 |
| Fourier-24 | 49 | 1.63e-01 | 2.42e-02 |
| LPR ±2°, degree 1 | 2 | 6.30e-02 | 1.56e-02 |
| LPR ±5°, degree 2 | 3 | 6.60e-02 | 1.40e-02 |
| LPR ±10°, degree 2 | 3 | 1.98e-01 | 2.70e-02 |
| **PAPPA (7 patches + pits)** | **61** | **5.42e-02** | **1.51e-02** |

An honest reading of the table (no advertising):

* **Against Fourier** the gap is not cosmetic: even 49 harmonics — as many
  coefficients as PAPPA has — give max|Δ| 0.163 mm, three times worse. A truncated
  series “rings” around the whole ring because its basis is global (see
  `method_vs_fourier`).
* **Against LPR** the picture is subtler, and that has to be said plainly: with a
  well-chosen window LPR gives COMPARABLE accuracy (RMSE 1.40e-02 versus 1.51e-02,
  max|Δ| 6.60e-02 versus 5.42e-02). The difference is not in “magical accuracy” but
  in the properties of the model:
  * the window and the degree of LPR are EXTERNAL parameters: moving the window
    from ±5° to ±10° makes max|Δ| three times worse (6.60e-02 → 1.98e-01), and they
    have to be re-tuned for another part; PAPPA picks the degree on every patch
    itself with the “elbow” rule;
  * LPR fits a least-squares problem at EVERY evaluation point (1440 fits per
    section here) and needs the original measurements to evaluate; PAPPA is 61
    numbers in a document, and evaluation needs no input data;
  * LPR describes a narrow defect either blurrily (a wide window) or noisily (a
    narrow one), and it has no pit basis term: PAPPA carries the defect exactly and
    locally.

### 14.1 Layout: the seam-to-pit clearance over all sections

The layout is one for the whole body, so “a seam is not right next to a crack” is
checked over all 10 sections of the file (the `band` detector, §8). N = 7, sector
51.43°, `half_train = 40.71°` (the training window), `half_use = 30.71°` (the use
zone) — training is 10° wider than use, the patch window holds ~1337 of the 5882
cleaned points.

| Section | Pits | Min. clearance at `phase = 24.75°` | Min. clearance at `phase = 0` |
|---|---|---|---|
| 0 | 3 | +14.12° | +5.46° |
| 1 | 4 | +15.89° | +0.62° |
| 2 | 4 | +18.23° | +0.63° |
| 3 | 4 | +20.24° | +0.81° |
| 4 | 3 | +20.79° | +0.44° |
| 5 | 4 | +16.67° | +2.00° |
| 6 | 3 | +17.34° | +0.19° |
| 7 | 5 | +13.34° | +3.07° |
| 8 | 4 | +9.92° | +5.02° |
| 9 | 3 | +10.41° | +7.03° |
| **minimum** | | **+9.92°** | **+0.19°** |

An honest reading: on this synthetic data a seam NEVER landed inside a crack (the
clearance is positive at both phases), so the phase shift does not “rescue”
anything, it buys margin: at `phase_deg = 0` a seam stood closer than 2° to a crack
in 5 sections out of 10, at `phase_deg = 24.75°` — in none, and the minimum
clearance grew from 0.19° to 9.92°. That is exactly why the layout is computed in
advance from the zones rather than picked by eye, and why it is an external
parameter of the method (brute force over N and the phase:
`python/studies/explore_star_layout.py`, a phase review:
`compare_phase_shift.py`).

### 14.2 Degree: the rule, the cost and the error

The patch degrees on section 0 are `[8, 10, 4, 12, 4, 12, 4]` (centres 50.46°,
101.89°, 153.32°, 204.75°, 256.18°, 307.61°, 359.04°); the document metrics are:

| Patch | Degree | RMSE of the selected, mm | RMSE of the best, mm | Points in the window |
|---|---|---|---|---|
| P0 | 8 | 1.004e-01 | 9.980e-02 | 1337 |
| P1 | 10 | 1.025e-01 | 9.894e-02 | 1337 |
| P2 | 4 | 9.910e-02 | 9.768e-02 | 1327 |
| P3 | 12 | 1.077e-01 | 1.048e-01 | 1322 |
| P4 | 4 | 9.967e-02 | 9.839e-02 | 1329 |
| P5 | 12 | 1.121e-01 | 1.086e-01 | 1331 |
| P6 | 4 | 1.031e-01 | 9.982e-02 | 1327 |

The RMSE in a window is ≈ 0.1 mm — that is the measurement noise level, so the
“elbow” only fires where there is structure: smooth patches take `deg_min = 4`,
patches with a pit or an inflection take 8, 10, 12. The mirror computation of the
RMSE(deg) curve in the figure yields the same degrees (the script's self-check),
while `rmse_selected ≤ rmse_best·1.05` holds by construction and is verified by
`validate_model`.

The cost of the choice (the same section, one model, but the degree is set equal for
all patches; the coefficients are as in the document):

| Variant | Coeff. | max\|Δr\|, mm | RMSE, mm |
|---|---|---|---|
| all patches deg 4 | 39 | 3.983e-01 | 8.479e-02 |
| all patches deg 6 | 53 | 2.308e-01 | 4.806e-02 |
| all patches deg 8 | 67 | 1.061e-01 | 2.440e-02 |
| all patches deg 10 | 81 | 5.885e-02 | 1.638e-02 |
| all patches deg 12 | 95 | 5.416e-02 | 1.342e-02 |
| all patches deg 14 | 109 | 4.873e-02 | 1.217e-02 |
| **PAPPA (degree per patch)** | **65** | **5.416e-02** | **1.511e-02** |

(65 = 61 polynomial coefficients + 4 pit ones; in the method comparison table above
PAPPA shows 61 — there only the polynomials were counted.)

An honest reading: an adaptive degree is a choice of **budget**, not of an absolute
accuracy maximum. At a similar budget it beats any uniform degree by a factor of two
(deg 8, 67 coefficients: max|Δr| 1.061e-01 versus 5.416e-02), in max|Δr| it is no
worse than a uniform deg 12 at 95 coefficients (both 5.416e-02, because the error
peak sits at the bottom of a pit, where the pit term works), but strictly more
accurate than the adaptive one is only deg 14 — 4.873e-02 for 109 coefficients
(1.7× the budget) and with a least-squares fit on `x^14` in every window, that is,
with worse conditioning.

### 14.3 Cleaning: what the model would look like without it

Section 0: 6000 points, `iqr` (k = 3.0) removes 118 of them (1.97 %), the residual
threshold is 0.3902 mm at `IQR(residual) = 0.1301 mm`, the ring median window is
1.0° (17 points). The outliers are spread around the whole ring, so the detector
cannot be used to “skip” them.

| Model (same detector, layout and “elbow” rule) | Degrees | max\|Δr\|, mm | RMSE, mm |
|---|---|---|---|
| trained on CLEANED points | `[8, 10, 4, 12, 4, 12, 4]` | 5.416e-02 | 1.511e-02 |
| trained on ALL points (no cleaning) | `[6, 8, 4, 8, 4, 8, 4]` | 1.240e-01 | 3.127e-02 |

Outliers eat two decisions at once: the degrees sag (8–12 → 6–8), because the
least-squares fit in a window is dragged by the outliers, and the error grows by a
factor of 2.3 in max|Δr| and 2.1 in RMSE. That is why cleaning comes FIRST in the
pipeline — before the detector, before the “elbow” rule and before the fit itself.
