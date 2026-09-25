package pappa

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Конформанс-векторы: «золотые» пары «вход → ожидаемый выход», которые
// генерирует референс на Python (python/studies/make_conformance.py) и читают
// ВСЕ порты (C++, Go, ...). Здесь — проверка, что порт воспроизводит ожидания.
// Формат и допуски описаны в spec/conformance/README.md.

// Tolerance — допуски сравнения.
type Tolerance struct {
	CoefsRel      float64 `json:"coefs_rel"`
	CoefsAbsFloor float64 `json:"coefs_abs_floor"`
	CurveMM       float64 `json:"curve_mm"`
	Frac          float64 `json:"frac"`
}

// Result — итог проверки одного вектора.
type Result struct {
	File  string
	Kind  string
	Name  string
	OK    bool
	Notes []string
}

type vectorInput struct {
	AnglesDeg []float64 `json:"angles_deg"`
	RadiiMM   []float64 `json:"radii_mm"`
}

type modelConfig struct {
	NPatches       int       `json:"n_patches"`
	PhaseDeg       float64   `json:"phase_deg"`
	DegMin         int       `json:"deg_min"`
	DegMax         int       `json:"deg_max"`
	AmplitudeScale float64   `json:"amplitude_scale"`
	OverlapTrain   float64   `json:"overlap_train"`
	OverlapUse     float64   `json:"overlap_use"`
	DegElbowTol    float64   `json:"deg_elbow_tol"`
	CoordMode      string    `json:"coord_mode"`
	PitsDeg        []float64 `json:"pits_deg"`
	SigmaDeg       float64   `json:"sigma_deg"`
	PitCoreSigma   float64   `json:"pit_core_sigma"`
	PitWindowSigma float64   `json:"pit_window_sigma"`
	PitMinAmp      float64   `json:"pit_min_amp"`
	Tapering       *bool     `json:"tapering"`
}

type detectorConfig struct {
	WindowDeg  float64 `json:"window_deg"`
	WideDeg    float64 `json:"wide_deg"`
	SmoothDeg  float64 `json:"smooth_deg"`
	K          float64 `json:"k"`
	MinZoneDeg float64 `json:"min_zone_deg"`
}

type cleanerConfig struct {
	BaselineDeg float64 `json:"baseline_deg"`
	IQRK        float64 `json:"iqr_k"`
}

type modelExpected struct {
	Degrees  []int       `json:"degrees"`
	Coefs    [][]float64 `json:"coefs"`
	PitTerms []struct {
		DxDeg []float64 `json:"dx_deg"`
		Amp   []float64 `json:"amp"`
	} `json:"pit_terms"`
	Curve struct {
		AnglesDeg []float64 `json:"angles_deg"`
		RadiiMM   []float64 `json:"radii_mm"`
	} `json:"curve"`
}

type detectorExpected struct {
	ZonesDeg [][]float64 `json:"zones_deg"`
	PitsDeg  []float64   `json:"pits_deg"`
}

type cleanerExpected struct {
	NOutliers       int   `json:"n_outliers"`
	MaskTrueIndices []int `json:"mask_true_indices"`
	NPoints         int   `json:"n_points"`
}

type rawVector struct {
	Format    string          `json:"format"`
	Version   string          `json:"version"`
	Kind      string          `json:"kind"`
	Name      string          `json:"name"`
	Tolerance Tolerance       `json:"tolerance"`
	Config    json.RawMessage `json:"config"`
	Input     vectorInput     `json:"input"`
	Expected  json.RawMessage `json:"expected"`
}

// CheckVectorsDir — проверить все *.json в каталоге (по возрастанию имени).
func CheckVectorsDir(dir string) ([]Result, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	var files []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".json") {
			files = append(files, filepath.Join(dir, e.Name()))
		}
	}
	sort.Strings(files)
	if len(files) == 0 {
		return nil, fmt.Errorf("в каталоге нет *.json: %s", dir)
	}
	out := make([]Result, 0, len(files))
	for _, f := range files {
		r, err := CheckVectorFile(f)
		if err != nil {
			return out, err
		}
		out = append(out, r)
	}
	return out, nil
}

// CheckVectorFile — прочитать и проверить один вектор.
func CheckVectorFile(path string) (Result, error) {
	res := Result{File: filepath.Base(path)}
	data, err := os.ReadFile(path)
	if err != nil {
		return res, err
	}
	var v rawVector
	if err := json.Unmarshal(data, &v); err != nil {
		return res, fmt.Errorf("%s: %w", res.File, err)
	}
	res.Kind, res.Name = v.Kind, v.Name

	if v.Format != "pappa-conformance" {
		res.Notes = append(res.Notes,
			fmt.Sprintf("формат %q, ожидался \"pappa-conformance\"", v.Format))
		return res, nil
	}

	switch v.Kind {
	case "model":
		err = checkModel(v, &res)
	case "detector":
		err = checkDetector(v, &res)
	case "cleaner":
		err = checkCleaner(v, &res)
	default:
		res.Notes = append(res.Notes, fmt.Sprintf("неизвестный kind: %q", v.Kind))
		return res, nil
	}
	if err != nil {
		return res, err
	}
	res.OK = len(res.Notes) == 0
	return res, nil
}

func checkModel(v rawVector, res *Result) error {
	var cfg modelConfig
	if err := json.Unmarshal(v.Config, &cfg); err != nil {
		return fmt.Errorf("%s: конфиг модели: %w", res.File, err)
	}
	var want modelExpected
	if err := json.Unmarshal(v.Expected, &want); err != nil {
		return fmt.Errorf("%s: ожидания модели: %w", res.File, err)
	}

	opt := DefaultModelOptions()
	opt.NPatches, opt.PhaseDeg = cfg.NPatches, cfg.PhaseDeg
	opt.DegMin, opt.DegMax = cfg.DegMin, cfg.DegMax
	opt.OverlapTrain, opt.OverlapUse = cfg.OverlapTrain, cfg.OverlapUse
	opt.DegElbowTol, opt.CoordMode = cfg.DegElbowTol, cfg.CoordMode
	if cfg.AmplitudeScale != 0 {
		opt.AmplitudeScale = cfg.AmplitudeScale
	}

	m := NewModel(opt, cfg.PitsDeg)
	if len(cfg.PitsDeg) > 0 {
		m.Shape.SigmaDeg = cfg.SigmaDeg
		m.Shape.CoreSigma = cfg.PitCoreSigma
		m.Shape.WindowSigma = cfg.PitWindowSigma
		m.Shape.MinAmp = cfg.PitMinAmp
		if cfg.Tapering != nil {
			m.Shape.Tapering = *cfg.Tapering
		}
	}
	if err := m.Fit(v.Input.AnglesDeg, v.Input.RadiiMM); err != nil {
		return fmt.Errorf("%s: %w", res.File, err)
	}

	got := m.Degrees()
	if len(got) != len(want.Degrees) {
		res.Notes = append(res.Notes,
			fmt.Sprintf("патчей %d, ожидалось %d", len(got), len(want.Degrees)))
	} else {
		for i := range got {
			if got[i] != want.Degrees[i] {
				res.Notes = append(res.Notes,
					fmt.Sprintf("степени: получено %v, ожидалось %v", got, want.Degrees))
				break
			}
		}
	}

	worstRatio := 0.0
	for p := 0; p < len(want.Coefs) && p < len(m.Patches); p++ {
		patch := m.Patches[p]
		if len(patch.Coefs) != len(want.Coefs[p]) {
			res.Notes = append(res.Notes, fmt.Sprintf("патч %d: коэффициентов %d != %d",
				p, len(patch.Coefs), len(want.Coefs[p])))
			continue
		}
		for k := range patch.Coefs {
			delta := abs(patch.Coefs[k] - want.Coefs[p][k])
			allowed := maxF(v.Tolerance.CoefsAbsFloor,
				v.Tolerance.CoefsRel*abs(want.Coefs[p][k]))
			worstRatio = maxF(worstRatio, delta/allowed)
		}
		if p >= len(want.PitTerms) {
			continue
		}
		wt := want.PitTerms[p]
		if len(patch.PitOffsetsDeg) != len(wt.DxDeg) {
			res.Notes = append(res.Notes, fmt.Sprintf("патч %d: терминов фичера %d != %d",
				p, len(patch.PitOffsetsDeg), len(wt.DxDeg)))
			continue
		}
		for k := range patch.PitOffsetsDeg {
			if abs(patch.PitOffsetsDeg[k]-wt.DxDeg[k]) > 1e-9 {
				res.Notes = append(res.Notes, fmt.Sprintf("патч %d: dx фичера %g != %g",
					p, patch.PitOffsetsDeg[k], wt.DxDeg[k]))
			}
			if abs(patch.PitCoefs[k]-wt.Amp[k]) >
				maxF(v.Tolerance.CoefsAbsFloor, v.Tolerance.CoefsRel*abs(wt.Amp[k])) {
				res.Notes = append(res.Notes, fmt.Sprintf("патч %d: амплитуда фичера %g != %g",
					p, patch.PitCoefs[k], wt.Amp[k]))
			}
		}
	}
	if worstRatio > 1.0 {
		res.Notes = append(res.Notes, fmt.Sprintf(
			"коэффициенты: отношение расхождения к допуску %g", worstRatio))
	}

	gotY, err := m.Eval(want.Curve.AnglesDeg)
	if err != nil {
		return err
	}
	worstCurve := 0.0
	for i := range gotY {
		if i < len(want.Curve.RadiiMM) {
			worstCurve = maxF(worstCurve, abs(gotY[i]-want.Curve.RadiiMM[i]))
		}
	}
	if worstCurve > v.Tolerance.CurveMM {
		res.Notes = append(res.Notes, fmt.Sprintf(
			"контур: максимум расхождения %g > допуска %g", worstCurve, v.Tolerance.CurveMM))
	}
	return nil
}

func checkDetector(v rawVector, res *Result) error {
	var cfg detectorConfig
	if err := json.Unmarshal(v.Config, &cfg); err != nil {
		return fmt.Errorf("%s: конфиг детектора: %w", res.File, err)
	}
	var want detectorExpected
	if err := json.Unmarshal(v.Expected, &want); err != nil {
		return fmt.Errorf("%s: ожидания детектора: %w", res.File, err)
	}
	opt := DetectorOptions{BaselineDeg: cfg.WindowDeg, WideDeg: cfg.WideDeg,
		SmoothDeg: cfg.SmoothDeg, K: cfg.K, MinZoneDeg: cfg.MinZoneDeg}
	got := Pits(v.Input.AnglesDeg, v.Input.RadiiMM, opt)
	if len(got) != len(want.PitsDeg) {
		res.Notes = append(res.Notes, fmt.Sprintf("ям найдено %d, ожидалось %d",
			len(got), len(want.PitsDeg)))
	}
	for i := 0; i < len(got) && i < len(want.PitsDeg); i++ {
		if abs(got[i]-want.PitsDeg[i]) > 1e-6 {
			res.Notes = append(res.Notes, fmt.Sprintf("центр ямы %d: %g != %g",
				i, got[i], want.PitsDeg[i]))
		}
	}
	return nil
}

func checkCleaner(v rawVector, res *Result) error {
	var cfg cleanerConfig
	if err := json.Unmarshal(v.Config, &cfg); err != nil {
		return fmt.Errorf("%s: конфиг очистки: %w", res.File, err)
	}
	var want cleanerExpected
	if err := json.Unmarshal(v.Expected, &want); err != nil {
		return fmt.Errorf("%s: ожидания очистки: %w", res.File, err)
	}
	opt := DefaultCleanerOptions()
	opt.BaselineDeg, opt.IQRK = cfg.BaselineDeg, cfg.IQRK
	mask := Clean(v.Input.AnglesDeg, v.Input.RadiiMM, opt)

	var got []int
	for i, flagged := range mask {
		if flagged {
			got = append(got, i)
		}
	}
	if len(got) != len(want.MaskTrueIndices) {
		res.Notes = append(res.Notes, fmt.Sprintf("отброшено %d точек, ожидалось %d",
			len(got), len(want.MaskTrueIndices)))
	}
	shown := 0
	for i := 0; i < len(got) || i < len(want.MaskTrueIndices); i++ {
		a, b := -1, -1
		if i < len(got) {
			a = got[i]
		}
		if i < len(want.MaskTrueIndices) {
			b = want.MaskTrueIndices[i]
		}
		if a != b && shown < 5 {
			res.Notes = append(res.Notes,
				fmt.Sprintf("  позиция %d: получено %d, ожидалось %d", i, a, b))
			shown++
		}
	}
	return nil
}
