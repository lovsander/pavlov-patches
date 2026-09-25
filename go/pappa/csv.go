package pappa

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

// CSVRow — одна точка измерения.
type CSVRow struct {
	SectionID int
	HeightMM  float64
	AngleDeg  float64
	RadiusMM  float64
}

// LoadCSV — чтение CSV ПО ЗАГОЛОВКУ (имена колонок, а не их порядок).
// Обязательны section_id, height_mm, angle_deg, radius_mm; остальные (в т.ч.
// эталонные radius_ideal_mm и флаг is_outlier) игнорируются — пайплайну для
// работы они не нужны (как в порту C++).
func LoadCSV(path string) ([]CSVRow, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("не могу открыть CSV: %w", err)
	}
	defer f.Close()

	r := csv.NewReader(f)
	r.FieldsPerRecord = -1
	header, err := r.Read()
	if err != nil {
		return nil, fmt.Errorf("пустой CSV: %w", err)
	}
	index := map[string]int{}
	for i, h := range header {
		index[strings.TrimSpace(h)] = i
	}
	need := []string{"section_id", "height_mm", "angle_deg", "radius_mm"}
	for _, k := range need {
		if _, ok := index[k]; !ok {
			return nil, fmt.Errorf("в CSV нет колонки %q", k)
		}
	}

	var rows []CSVRow
	for {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		if len(rec) == 0 {
			continue
		}
		sec, err := strconv.Atoi(strings.TrimSpace(rec[index["section_id"]]))
		if err != nil {
			return nil, fmt.Errorf("section_id: %w", err)
		}
		h, err := strconv.ParseFloat(strings.TrimSpace(rec[index["height_mm"]]), 64)
		if err != nil {
			return nil, fmt.Errorf("height_mm: %w", err)
		}
		a, err := strconv.ParseFloat(strings.TrimSpace(rec[index["angle_deg"]]), 64)
		if err != nil {
			return nil, fmt.Errorf("angle_deg: %w", err)
		}
		rad, err := strconv.ParseFloat(strings.TrimSpace(rec[index["radius_mm"]]), 64)
		if err != nil {
			return nil, fmt.Errorf("radius_mm: %w", err)
		}
		rows = append(rows, CSVRow{SectionID: sec, HeightMM: h,
			AngleDeg: a, RadiusMM: rad})
	}
	if len(rows) == 0 {
		return nil, fmt.Errorf("в CSV нет строк с данными")
	}
	return rows, nil
}

// PipelineOptions — параметры посекционного расчёта (значения по умолчанию —
// те же, что у референса и порта C++: N=7, фаза 24.75°, авто-iqr, фичер ям).
type PipelineOptions struct {
	Model    ModelOptions
	Cleaner  CleanerOptions
	Detector DetectorOptions
	Pits     bool
	Verbose  bool
}

// DefaultPipelineOptions — штатная конфигурация пайплайна.
func DefaultPipelineOptions() PipelineOptions {
	return PipelineOptions{
		Model:    DefaultModelOptions(),
		Cleaner:  DefaultCleanerOptions(),
		Detector: DefaultDetectorOptions(),
		Pits:     true,
		Verbose:  true,
	}
}

// ProcessSections — посекционный расчёт: сортировка по углу, авто-очистка,
// детектор ям (если включён фичер), обучение модели.
func ProcessSections(rows []CSVRow, opt PipelineOptions) ([]SectionModel, error) {
	// группировка по section_id
	bySection := map[int][]CSVRow{}
	var ids []int
	for _, r := range rows {
		if _, seen := bySection[r.SectionID]; !seen {
			ids = append(ids, r.SectionID)
		}
		bySection[r.SectionID] = append(bySection[r.SectionID], r)
	}
	sortInts(ids)

	out := make([]SectionModel, 0, len(ids))
	for _, sid := range ids {
		group := bySection[sid]
		// точки сечения сортируются по углу (кольцо считается замкнутым)
		sort.SliceStable(group, func(i, j int) bool {
			return group[i].AngleDeg < group[j].AngleDeg
		})
		angles := make([]float64, len(group))
		radii := make([]float64, len(group))
		for i, g := range group {
			angles[i], radii[i] = g.AngleDeg, g.RadiusMM
		}

		mask := Clean(angles, radii, opt.Cleaner)
		aClean := make([]float64, 0, len(angles))
		rClean := make([]float64, 0, len(angles))
		nOutliers := 0
		for i := range angles {
			if mask[i] {
				nOutliers++
				continue
			}
			aClean = append(aClean, angles[i])
			rClean = append(rClean, radii[i])
		}

		var pits []float64
		if opt.Pits {
			pits = Pits(aClean, rClean, opt.Detector)
		}
		model := NewModel(opt.Model, pits)
		start := time.Now()
		if err := model.Fit(aClean, rClean); err != nil {
			return nil, fmt.Errorf("сечение %d: %w", sid, err)
		}
		fitMS := float64(time.Since(start).Microseconds()) / 1000.0

		sec := SectionModel{
			SectionID: sid, HeightMM: group[0].HeightMM, Model: model,
			NPointsTotal: len(angles), NOutliers: nOutliers, FitTimeMS: fitMS,
			Description: fmt.Sprintf("сечение %d, h=%.0f мм", sid, group[0].HeightMM),
		}
		if opt.Verbose {
			fmt.Printf("  секция %d (h=%.0f мм): точек %d, выброшено %d, "+
				"ям найдено %d, степени %v, обучение %.1f мс\n",
				sid, sec.HeightMM, sec.NPointsTotal, nOutliers, len(pits),
				model.Degrees(), fitMS)
		}
		out = append(out, sec)
	}
	return out, nil
}

func sortInts(v []int) {
	sort.Ints(v)
}
