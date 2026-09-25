# Spec

Language-independent contract of **PAPPA** (Piecewise Adaptive Poly-Patch
Approximation):

- `pappa.schema.json` — JSON Schema of the serialized model document.
- `conformance/` — golden vectors (`input -> expected output`) used to verify
  every language port against the reference implementation.

A port is considered correct when it reproduces all conformance vectors within
the documented tolerance (curve 1e-6 mm; see CONTEXT §27).

A sample folder (`samples/<name>/`) is the unit of exchange: `sample.json`
manifest + one `pappa.json` document per section + `report/verify.json` with the
numeric check of the port.
