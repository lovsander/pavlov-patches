package pappa

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"time"
)

// Документ описания сечения (.pappa.json, формат pappa v2.0) и папка образца —
// ТОТ ЖЕ контракт, что у референса Python и порта C++ (CONTEXT §27):
//
//	<dir>/sample.json                манифест (format pappa-sample v1.0)
//	<dir>/sections/00.pappa.json     документ на сечение (по порядку section_id)
//
// Поэтому папки, собранные Python-ом и любым портом, сравниваются численно
// (python/studies/verify_port.py) без договорённостей «на словах».
// Порядок полей задаётся порядком полей структур — как json.dump у Python.

// Формат документа.
const (
	DocumentFormat  = "pappa"
	DocumentVersion = "2.0"
	SampleFormat    = "pappa-sample"
	SampleVersion   = "1.0"
	// PortVersion — версия порта, видна в документе (кто записал).
	PortVersion = "0.1.0-go"
)

type unitsBlock struct {
	Angle  string `json:"angle"`
	Length string `json:"length"`
}

type softwareBlock struct {
	Language     string `json:"language"`
	PappaVersion string `json:"pappa_version"`
}

type metaBlock struct {
	SectionID   int     `json:"section_id"`
	HeightMM    float64 `json:"height_mm"`
	Source      string  `json:"source"`
	Description string  `json:"description"`
}

type pitBlock struct {
	SigmaDeg    float64   `json:"sigma_deg"`
	CoreSigma   float64   `json:"core_sigma"`
	WindowSigma float64   `json:"window_sigma"`
	MinAmp      float64   `json:"pit_min_amp"`
	Tapering    bool      `json:"tapering"`
	CentersDeg  []float64 `json:"centers_deg"`
}

type globalBlock struct {
	Units           unitsBlock `json:"units"`
	NPatches        int        `json:"n_patches"`
	HalfSectorDeg   float64    `json:"half_sector_deg"`
	PhaseDeg        float64    `json:"phase_deg"`
	HalfTrainDeg    float64    `json:"half_train_deg"`
	HalfUseDeg      float64    `json:"half_use_deg"`
	OverlapTrainDeg float64    `json:"overlap_train_deg"`
	OverlapUseDeg   float64    `json:"overlap_use_deg"`
	DegMin          int        `json:"deg_min"`
	DegMax          int        `json:"deg_max"`
	CoordMode       string     `json:"coord_mode"`
	DegElbowTol     float64    `json:"deg_elbow_tol"`
	AmplitudeScale  float64    `json:"amplitude_scale"`
	Pit             *pitBlock  `json:"pit,omitempty"`
}

type metricsBlock struct {
	AmplitudeMM    float64 `json:"amplitude_mm"`
	MeanRadiusMM   float64 `json:"mean_radius_mm"`
	AmplitudeNorm  float64 `json:"amplitude_norm"`
	DegElbowTol    float64 `json:"deg_elbow_tol"`
	RMSESelectedMM float64 `json:"rmse_selected_mm"`
	RMSEBestMM     float64 `json:"rmse_best_mm"`
	NTrainPoints   int     `json:"n_train_points"`
}

type statsBlock struct {
	RMSEMm      float64 `json:"rmse_mm"`
	MAEMm       float64 `json:"mae_mm"`
	MaxErrMM    float64 `json:"max_err_mm"`
	Correlation float64 `json:"correlation"`
}

type pitTermDoc struct {
	DxDeg float64 `json:"dx_deg"`
	Amp   float64 `json:"amp"`
}

type patchDoc struct {
	CenterDeg float64      `json:"center_deg"`
	Degree    int          `json:"degree"`
	NPoints   int          `json:"n_points"`
	Coefs     []float64    `json:"coefs"`
	Metrics   metricsBlock `json:"metrics"`
	Stats     statsBlock   `json:"stats"`
	// PitTerms: nil — модель без ям (поля нет), иначе список (в т.ч. пустой).
	PitTerms *[]pitTermDoc `json:"pit_terms,omitempty"`
}

type statisticsBlock struct {
	NPointsTotal     int     `json:"n_points_total"`
	NOutliersRemoved int     `json:"n_outliers_removed"`
	FitTimeMS        float64 `json:"fit_time_ms"`
}

type document struct {
	Format     string          `json:"format"`
	Version    string          `json:"version"`
	Method     string          `json:"method"`
	Created    string          `json:"created"`
	Software   softwareBlock   `json:"software"`
	Meta       metaBlock       `json:"meta"`
	Global     globalBlock     `json:"global"`
	Patches    []patchDoc      `json:"patches"`
	Statistics statisticsBlock `json:"statistics"`
}

// SectionModel — описание одного сечения (модель + сведения о данных).
type SectionModel struct {
	SectionID    int
	HeightMM     float64
	Model        *Model
	NPointsTotal int
	NOutliers    int
	Source       string
	Description  string
	FitTimeMS    float64
}

func nowUTC() string { return time.Now().UTC().Format("2006-01-02T15:04:05Z") }

func (m *Model) toDocument(sec SectionModel) document {
	doc := document{
		Format:   DocumentFormat,
		Version:  DocumentVersion,
		Method:   "PatchApproximator",
		Created:  nowUTC(),
		Software: softwareBlock{Language: "go", PappaVersion: PortVersion},
		Meta: metaBlock{SectionID: sec.SectionID, HeightMM: sec.HeightMM,
			Source: sec.Source, Description: sec.Description},
		Global: globalBlock{
			Units:    unitsBlock{Angle: "degree", Length: "mm"},
			NPatches: m.Opt.NPatches, HalfSectorDeg: m.HalfSect,
			PhaseDeg: m.Opt.PhaseDeg, HalfTrainDeg: m.HalfSect + m.Opt.OverlapTrain,
			HalfUseDeg:      m.HalfSect + m.Opt.OverlapUse,
			OverlapTrainDeg: m.Opt.OverlapTrain, OverlapUseDeg: m.Opt.OverlapUse,
			DegMin: m.Opt.DegMin, DegMax: m.Opt.DegMax, CoordMode: m.Opt.CoordMode,
			DegElbowTol: m.Opt.DegElbowTol, AmplitudeScale: m.Opt.AmplitudeScale,
		},
		Statistics: statisticsBlock{NPointsTotal: sec.NPointsTotal,
			NOutliersRemoved: sec.NOutliers, FitTimeMS: sec.FitTimeMS},
	}
	hasPits := len(m.Pits) > 0
	if hasPits {
		doc.Method = "PitPatchApproximator"
		doc.Global.Pit = &pitBlock{
			SigmaDeg: m.Shape.SigmaDeg, CoreSigma: m.Shape.CoreSigma,
			WindowSigma: m.Shape.WindowSigma, MinAmp: m.Shape.MinAmp,
			Tapering: m.Shape.Tapering, CentersDeg: m.Pits,
		}
	}
	for _, p := range m.Patches {
		pd := patchDoc{
			CenterDeg: p.Center, Degree: p.Degree, NPoints: p.NPoints,
			Coefs: p.Coefs,
			Metrics: metricsBlock{
				AmplitudeMM: p.AmplitudeMM, MeanRadiusMM: p.MeanRadiusMM,
				AmplitudeNorm: p.AmplitudeNorm, DegElbowTol: m.Opt.DegElbowTol,
				RMSESelectedMM: p.RMSESelectedMM, RMSEBestMM: p.RMSEBestMM,
				NTrainPoints: p.NTrainPoints,
			},
			Stats: statsBlock{RMSEMm: p.RMSEMm, MAEMm: p.MAEMm,
				MaxErrMM: p.MaxErrMM, Correlation: p.Correlation},
		}
		if hasPits {
			// список пишем ВСЕГДА (включая пустой) — так делает референс
			terms := make([]pitTermDoc, 0, len(p.PitOffsetsDeg))
			for i, off := range p.PitOffsetsDeg {
				terms = append(terms, pitTermDoc{DxDeg: off, Amp: p.PitCoefs[i]})
			}
			pd.PitTerms = &terms
		}
		doc.Patches = append(doc.Patches, pd)
	}
	return doc
}

// SaveDocument — записать документ описания одного сечения.
func SaveDocument(path string, sec SectionModel) error {
	if sec.Model == nil || !sec.Model.Fitted {
		return fmt.Errorf("save_document: модель не обучена")
	}
	data, err := json.MarshalIndent(sec.Model.toDocument(sec), "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}

type sampleSectionEntry struct {
	Index     int     `json:"index"`
	SectionID int     `json:"section_id"`
	HeightMM  float64 `json:"height_mm"`
	File      string  `json:"file"`
	NPoints   int     `json:"n_points"`
	NOutliers int     `json:"n_outliers"`
}

type cleanerAuto struct {
	Method      string  `json:"method"`
	BaselineDeg float64 `json:"baseline_deg"`
	IQRK        float64 `json:"iqr_k"`
}

type cleanerBlock struct {
	Mode string      `json:"mode"`
	Auto cleanerAuto `json:"auto"`
}

type detectorBlock struct {
	Kind       string  `json:"kind"`
	WindowDeg  float64 `json:"window_deg"`
	WideDeg    float64 `json:"wide_deg"`
	SmoothDeg  float64 `json:"smooth_deg"`
	K          float64 `json:"k"`
	MinZoneDeg float64 `json:"min_zone_deg"`
}

type sampleConfig struct {
	NPatches     int            `json:"n_patches"`
	PhaseDeg     float64        `json:"phase_deg"`
	DegMin       int            `json:"deg_min"`
	DegMax       int            `json:"deg_max"`
	OverlapTrain float64        `json:"overlap_train"`
	OverlapUse   float64        `json:"overlap_use"`
	DegElbowTol  float64        `json:"deg_elbow_tol"`
	Cleaner      cleanerBlock   `json:"cleaner"`
	Pits         bool           `json:"pits"`
	SigmaDeg     float64        `json:"sigma_deg,omitempty"`
	PitCoreSigma float64        `json:"pit_core_sigma,omitempty"`
	PitWindowSig float64        `json:"pit_window_sigma,omitempty"`
	PitMinAmp    float64        `json:"pit_min_amp,omitempty"`
	Tapering     *bool          `json:"tapering,omitempty"`
	Detector     *detectorBlock `json:"detector"`
}

type sampleManifest struct {
	Format   string               `json:"format"`
	Version  string               `json:"version"`
	Name     string               `json:"name"`
	Created  string               `json:"created"`
	Units    unitsBlock           `json:"units"`
	Meta     map[string]string    `json:"meta"`
	Input    map[string]string    `json:"input,omitempty"`
	Config   sampleConfig         `json:"config"`
	Sections []sampleSectionEntry `json:"sections"`
}

// SampleOptions — параметры записи папки образца (в манифест, для воспроизводимости).
type SampleOptions struct {
	Name        string
	InputCSV    string
	Description string
	Cleaner     CleanerOptions
	Detector    DetectorOptions
	Pits        bool
}

// SaveSample — записать папку образца (манифест + документ на каждое сечение).
func SaveSample(dir, name string, sections []SectionModel, opt SampleOptions) (string, error) {
	root := filepath.Clean(dir)
	if err := os.MkdirAll(filepath.Join(root, "sections"), 0o755); err != nil {
		return "", err
	}

	ordered := make([]SectionModel, len(sections))
	copy(ordered, sections)
	sort.SliceStable(ordered, func(i, j int) bool {
		return ordered[i].SectionID < ordered[j].SectionID
	})

	manifest := sampleManifest{
		Format: SampleFormat, Version: SampleVersion, Name: name, Created: nowUTC(),
		Units: unitsBlock{Angle: "degree", Length: "mm"},
		Meta:  map[string]string{"description": opt.Description},
	}
	if opt.InputCSV != "" {
		manifest.Input = map[string]string{"csv": opt.InputCSV}
	}
	if len(ordered) > 0 {
		m := ordered[0].Model
		manifest.Config = sampleConfig{
			NPatches: m.Opt.NPatches, PhaseDeg: m.Opt.PhaseDeg,
			DegMin: m.Opt.DegMin, DegMax: m.Opt.DegMax,
			OverlapTrain: m.Opt.OverlapTrain, OverlapUse: m.Opt.OverlapUse,
			DegElbowTol: m.Opt.DegElbowTol,
			Cleaner: cleanerBlock{Mode: "auto", Auto: cleanerAuto{
				Method: "iqr", BaselineDeg: opt.Cleaner.BaselineDeg,
				IQRK: opt.Cleaner.IQRK}},
			Pits: opt.Pits,
		}
		if opt.Pits {
			manifest.Config.SigmaDeg = m.Shape.SigmaDeg
			manifest.Config.PitCoreSigma = m.Shape.CoreSigma
			manifest.Config.PitWindowSig = m.Shape.WindowSigma
			manifest.Config.PitMinAmp = m.Shape.MinAmp
			tapering := m.Shape.Tapering
			manifest.Config.Tapering = &tapering
			manifest.Config.Detector = &detectorBlock{
				Kind: "band", WindowDeg: opt.Detector.BaselineDeg,
				WideDeg: opt.Detector.WideDeg, SmoothDeg: opt.Detector.SmoothDeg,
				K: opt.Detector.K, MinZoneDeg: opt.Detector.MinZoneDeg,
			}
		}
	}

	for i, sec := range ordered {
		file := fmt.Sprintf("sections/%02d.pappa.json", i)
		if err := SaveDocument(filepath.Join(root, file), sec); err != nil {
			return "", err
		}
		manifest.Sections = append(manifest.Sections, sampleSectionEntry{
			Index: i, SectionID: sec.SectionID, HeightMM: sec.HeightMM,
			File: file, NPoints: sec.NPointsTotal, NOutliers: sec.NOutliers,
		})
	}

	data, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(root, "sample.json"), data, 0o644); err != nil {
		return "", err
	}
	return root, nil
}
