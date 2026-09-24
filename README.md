# pavlov-patches

**Adaptive Poly-Patch Approximation (APPA)** — *aka “Pavlov patches”.*

A compact, parametric method for approximating closed (periodic) or open 1-D
profiles as a set of **overlapping local polynomial patches** with **adaptive
per-patch degree** and **smooth (C¹) blending**.

> Status: **work in progress.** The repository is being restructured; the
> reference implementation lives in `python/`, ports follow.

---

## Idea in one paragraph

Divide the domain into `N` overlapping sectors. Fit an independent low-order
polynomial over each sector; the sector “complexity” (normalised amplitude,
RMSE vs. noise floor, …) picks its degree. Reconstruct the profile as a
smoothstep-weighted blend of the patches, so the result is continuous and
locally faithful without global ringing.

Distinctive features:

- **Local** — error is bounded per sector, no global Gibbs-type ringing;
- **Adaptive** — busy sectors get more degrees, smooth ones fewer;
- **Compact / deterministic** — a fixed, small set of coefficients per model;
- **Portable** — model is a plain JSON document (`spec/`), reproducible in any language.

## Repository layout

| Path | Purpose |
|------|---------|
| `python/` | Reference implementation: package `appa/` (`core`, `io`, `analysis`, `viz`, `report`), runnable entry points in `studies/`, `demos/`, `generator/`, and the `deprecated/` archive |
| `cpp/`  | C++17 port (CMake) |
| `go/`   | Go port |
| `docs/` | Method description & presentation assets |
| `spec/` | Model file schema + conformance vectors |

## License

See [LICENSE](LICENSE).
