package pappa

import (
	"math"
	"sort"
)

// DetectorOptions — параметры детектора ям (DETECTOR_DEFAULTS).
type DetectorOptions struct {
	BaselineDeg float64 // узкая медиана, °
	WideDeg     float64 // широкая медиана, °
	SmoothDeg   float64 // сглаживание индикатора, °
	K           float64 // порог в MAD-ах
	MinZoneDeg  float64 // минимальная длина зоны, °
}

// DefaultDetectorOptions — значения из pappa/core/pit_feature.py (§14).
func DefaultDetectorOptions() DetectorOptions {
	return DetectorOptions{BaselineDeg: 1.0, WideDeg: 10.0, SmoothDeg: 2.0,
		K: 5.5, MinZoneDeg: 2.0}
}

// BandIndicator — индикатор band = |узкая медиана − широкая медиана|,
// сглаженный и нормированный на собственную робастную sigma (безразмерный).
func BandIndicator(angles, radii []float64, opt DetectorOptions) []float64 {
	narrow := MedianFilterWrap(radii, WindowPoints(angles, opt.BaselineDeg))
	wide := MedianFilterWrap(radii, WindowPoints(angles, opt.WideDeg))

	band := make([]float64, len(radii))
	for i := range radii {
		band[i] = math.Abs(narrow[i] - wide[i])
	}
	band = SmoothWrap(band, WindowPoints(angles, opt.SmoothDeg))

	s := RobustSigma(band)
	if s > 1e-12 {
		for i := range band {
			band[i] /= s
		}
	} else {
		for i := range band {
			band[i] = 0
		}
	}
	return band
}

// DetectZones — непрерывные зоны (интервалы углов, °) по порогу, с склейкой
// зоны, доходящей до 360° и начинающейся с 0° (кольцо).
func DetectZones(angles, values []float64, opt DetectorOptions) [][2]float64 {
	mask := make([]bool, len(values))
	for i, v := range values {
		mask[i] = v > opt.K
	}
	return maskToZones(angles, mask, opt.MinZoneDeg)
}

func maskToZones(angles []float64, mask []bool, minZoneDeg float64) [][2]float64 {
	n := len(angles)
	if n == 0 {
		return nil
	}
	any := false
	for _, v := range mask {
		if v {
			any = true
			break
		}
	}
	if !any {
		return nil
	}

	diffs := make([]float64, 0, n-1)
	for i := 1; i < n; i++ {
		diffs = append(diffs, angles[i]-angles[i-1])
	}
	step := 1.0
	if len(diffs) > 0 {
		step = Median(diffs)
	}

	var zones [][2]float64
	for i := 0; i < n; {
		if !mask[i] {
			i++
			continue
		}
		j := i
		for j+1 < n && mask[j+1] {
			j++
		}
		zones = append(zones, [2]float64{angles[i] - step/2, angles[j] + step/2})
		i = j + 1
	}

	// Кольцо: первая и последняя зоны — одна
	if len(zones) > 1 && mask[0] && mask[n-1] {
		first := zones[0]
		last := zones[len(zones)-1]
		zones = zones[1 : len(zones)-1]
		zones = append([][2]float64{{last[0] - 360.0, first[1]}}, zones...)
	}

	var out [][2]float64
	for _, z := range zones {
		if z[1]-z[0] >= minZoneDeg {
			out = append(out, z)
		}
	}
	return out
}

// Pits — центры ям (°) по профилю (середины найденных зон).
func Pits(angles, radii []float64, opt DetectorOptions) []float64 {
	band := BandIndicator(angles, radii, opt)
	var out []float64
	for _, z := range DetectZones(angles, band, opt) {
		out = append(out, 0.5*(z[0]+z[1]))
	}
	sort.Float64s(out)
	return out
}

// CleanerOptions — параметры авто-очистки (штатный режим пайплайна).
type CleanerOptions struct {
	BaselineDeg    float64
	IQRK           float64
	MaxRemovedFrac float64
	MinPoints      int
}

// DefaultCleanerOptions — авто-iqr из pappa/core/outlier_cleaner.py.
func DefaultCleanerOptions() CleanerOptions {
	return CleanerOptions{BaselineDeg: 1.0, IQRK: 3.0, MaxRemovedFrac: 0.5, MinPoints: 20}
}

// Clean — маска выбросов: остатки к локальному медианному уровню, усы Тьюки.
func Clean(angles, radii []float64, opt CleanerOptions) []bool {
	n := len(radii)
	mask := make([]bool, n)
	if n < max(3, opt.MinPoints) {
		return mask
	}

	baseline := MedianFilterWrap(radii, WindowPoints(angles, opt.BaselineDeg))
	res := make([]float64, n)
	for i := range radii {
		res[i] = radii[i] - baseline[i]
	}
	center := Median(res)
	spread := IQR(res)
	denom := spread
	if denom <= 1e-12 {
		denom = 1.0
	}

	severity := make([]float64, n)
	for i := range res {
		severity[i] = math.Abs(res[i]-center) / denom
		mask[i] = severity[i] > opt.IQRK
	}

	// предохранитель: не отбрасываем больше MaxRemovedFrac точек
	cap := int(math.Floor(opt.MaxRemovedFrac * float64(n)))
	flagged := 0
	for _, v := range mask {
		if v {
			flagged++
		}
	}
	if cap > 0 && cap < n && flagged > cap {
		vals := make([]float64, 0, flagged)
		for i := range mask {
			if mask[i] {
				vals = append(vals, severity[i])
			}
		}
		sort.Sort(sort.Reverse(sort.Float64Slice(vals)))
		keepLevel := vals[cap-1]
		for i := range mask {
			mask[i] = mask[i] && severity[i] >= keepLevel
		}
	}
	return mask
}
