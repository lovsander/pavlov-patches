package pappa

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"testing"
)

// syntheticProfile — маленький аналитический профиль для тестов (без данных репозитория).
func syntheticProfile(n int) (angles, radii []float64) {
	for i := 0; i < n; i++ {
		a := 360.0 * float64(i) / float64(n)
		r := 15.0 + 0.4*math.Sin(2*a*math.Pi/180) - 1.1*math.Exp(-math.Pow((a-90.0)/2.5, 2))
		angles = append(angles, a)
		radii = append(radii, r)
	}
	return angles, radii
}

// TestSampleFolder — папка образца пишется в том же виде, что у Python/C++:
// манифест + по документу на сечение, с корректными ключами и длинами.
func TestSampleFolder(t *testing.T) {
	angles, radii := syntheticProfile(720)
	model := NewModel(DefaultModelOptions(), []float64{90.0})
	if err := model.Fit(angles, radii); err != nil {
		t.Fatal(err)
	}
	secs := []SectionModel{{
		SectionID: 0, HeightMM: 0, Model: model,
		NPointsTotal: len(angles), Source: "test",
	}}
	dir := filepath.Join(t.TempDir(), "sample_go")
	root, err := SaveSample(dir, "sample_go", secs, SampleOptions{
		Name: "sample_go", Pits: true, Cleaner: DefaultCleanerOptions(),
		Detector: DefaultDetectorOptions(),
	})
	if err != nil {
		t.Fatal(err)
	}

	// манифест
	raw, err := os.ReadFile(filepath.Join(root, "sample.json"))
	if err != nil {
		t.Fatal(err)
	}
	var manifest map[string]any
	if err := json.Unmarshal(raw, &manifest); err != nil {
		t.Fatalf("манифест не разбирается как JSON: %v", err)
	}
	if manifest["format"] != "pappa-sample" || manifest["version"] != "1.0" {
		t.Errorf("манифест: format=%v version=%v", manifest["format"], manifest["version"])
	}
	sections, ok := manifest["sections"].([]any)
	if !ok || len(sections) != 1 {
		t.Fatalf("в манифесте ожидалось 1 сечение, получено %v", manifest["sections"])
	}

	// документ сечения
	docPath := filepath.Join(root, "sections", "00.pappa.json")
	rawDoc, err := os.ReadFile(docPath)
	if err != nil {
		t.Fatal(err)
	}
	var doc struct {
		Format  string `json:"format"`
		Version string `json:"version"`
		Method  string `json:"method"`
		Global  struct {
			NPatches  int     `json:"n_patches"`
			CoordMode string  `json:"coord_mode"`
			PhaseDeg  float64 `json:"phase_deg"`
			Pit       *struct {
				CentersDeg []float64 `json:"centers_deg"`
			} `json:"pit"`
		} `json:"global"`
		Patches []struct {
			Degree   int       `json:"degree"`
			Coefs    []float64 `json:"coefs"`
			PitTerms []struct {
				DxDeg float64 `json:"dx_deg"`
				Amp   float64 `json:"amp"`
			} `json:"pit_terms"`
		} `json:"patches"`
	}
	if err := json.Unmarshal(rawDoc, &doc); err != nil {
		t.Fatalf("документ не разбирается как JSON: %v", err)
	}
	if doc.Format != DocumentFormat || doc.Version != DocumentVersion {
		t.Errorf("документ: format=%q version=%q", doc.Format, doc.Version)
	}
	if doc.Method != "PitPatchApproximator" {
		t.Errorf("метод с ямами: %q", doc.Method)
	}
	if doc.Global.CoordMode != "normalized" {
		t.Errorf("coord_mode: %q", doc.Global.CoordMode)
	}
	if doc.Global.Pit == nil || len(doc.Global.Pit.CentersDeg) != 1 {
		t.Errorf("блок pit: %+v", doc.Global.Pit)
	}
	if len(doc.Patches) != model.Opt.NPatches {
		t.Fatalf("патчей: %d, ожидалось %d", len(doc.Patches), model.Opt.NPatches)
	}
	for i, p := range doc.Patches {
		if len(p.Coefs) != p.Degree+1 {
			t.Errorf("патч %d: коэффициентов %d != degree+1 %d", i, len(p.Coefs), p.Degree+1)
		}
		if p.PitTerms == nil {
			t.Errorf("патч %d: нет ключа pit_terms (у модели с ямами он обязателен)", i)
		}
	}
}

// TestDocumentRoundTrip — документ читается обратно тем же json-тегом (проверка,
// что формат самодостаточен: коэффициенты и термины фичера восстанавливаются).
func TestDocumentRoundTrip(t *testing.T) {
	angles, radii := syntheticProfile(360)
	model := NewModel(DefaultModelOptions(), nil)
	if err := model.Fit(angles, radii); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "sec.pappa.json")
	if err := SaveDocument(path, SectionModel{SectionID: 3, Model: model,
		NPointsTotal: len(angles)}); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var doc struct {
		Meta struct {
			SectionID int `json:"section_id"`
		} `json:"meta"`
		Patches []struct {
			Degree int       `json:"degree"`
			Coefs  []float64 `json:"coefs"`
		} `json:"patches"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	if doc.Meta.SectionID != 3 {
		t.Errorf("section_id: %d", doc.Meta.SectionID)
	}
	if len(doc.Patches) != len(model.Patches) {
		t.Fatalf("патчей %d != %d", len(doc.Patches), len(model.Patches))
	}
	for i := range doc.Patches {
		if doc.Patches[i].Degree != model.Patches[i].Degree {
			t.Errorf("патч %d: степень %d != %d", i, doc.Patches[i].Degree,
				model.Patches[i].Degree)
		}
		for k, c := range doc.Patches[i].Coefs {
			if math.Abs(c-model.Patches[i].Coefs[k]) > 1e-15 {
				t.Errorf("патч %d: коэффициент %d потерял точность: %g", i, k, c)
			}
		}
	}
}
