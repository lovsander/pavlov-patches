// Package pappa — порт PAPPA (Piecewise Adaptive Poly-Patch Approximation) на Go.
//
// Порт проверяется по КОНФОРМАНС-ВЕКТОРАМ из spec/conformance/vectors (см.
// pappa.CheckVectorFile и cmd/conformance): те же файлы, что читает порт C++,
// поэтому «правильность» порта не зависит от языка, на котором написан референс.
//
// Числа обязаны совпадать с референсом на Python, поэтому здесь повторены даже
// тонкости numpy: медиана (среднее двух центральных при чётном n), перцентиль с
// линейной интерполяцией, «банковское» округление в window_points (Python
// round(2.5) == 2, а math.Round(2.5) == 3 — поэтому RoundToEven), круговые окна
// и фильтры.
package pappa

import (
	"math"
	"sort"
)

// Median — медиана как np.median: при чётном n среднее двух центральных.
func Median(values []float64) float64 {
	n := len(values)
	if n == 0 {
		return 0
	}
	v := make([]float64, n)
	copy(v, values)
	sort.Float64s(v)
	if n%2 == 1 {
		return v[n/2]
	}
	return 0.5 * (v[n/2-1] + v[n/2])
}

// PercentileLinear — перцентиль с линейной интерполяцией (как np.percentile).
func PercentileLinear(values []float64, q float64) float64 {
	n := len(values)
	if n == 0 {
		return 0
	}
	v := make([]float64, n)
	copy(v, values)
	sort.Float64s(v)

	pos := (q / 100.0) * float64(n-1)
	lo := int(math.Floor(pos))
	frac := pos - float64(lo)
	hi := lo + 1
	if hi > n-1 {
		hi = n - 1
	}
	return v[lo] + frac*(v[hi]-v[lo])
}

// Mad — MAD = median(|x - median(x)|).
func Mad(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	m := Median(values)
	dev := make([]float64, len(values))
	for i, v := range values {
		dev[i] = math.Abs(v - m)
	}
	return Median(dev)
}

// RobustSigma — робастная sigma = 1.4826 * MAD.
func RobustSigma(values []float64) float64 { return 1.4826 * Mad(values) }

// IQR — межквартильный размах Q75 - Q25 (как np.percentile).
func IQR(values []float64) float64 {
	return PercentileLinear(values, 75) - PercentileLinear(values, 25)
}

// AngularStep — медианный шаг по углу, ° (перевод окон из градусов в точки).
func AngularStep(angles []float64) float64 {
	if len(angles) < 2 {
		return 1.0
	}
	diffs := make([]float64, 0, len(angles)-1)
	for i := 1; i < len(angles); i++ {
		if d := angles[i] - angles[i-1]; d > 0 {
			diffs = append(diffs, d)
		}
	}
	if len(diffs) == 0 {
		return 1.0
	}
	return Median(diffs)
}

// WindowPoints — нечётное число точек, ближайшее к spanDeg (>=3, <= длины).
func WindowPoints(angles []float64, spanDeg float64) int {
	n := len(angles)
	if n < 3 {
		if n < 1 {
			return 1
		}
		return n
	}
	// Python: int(round(span / step)) — округление «к чётному»
	w := int(math.RoundToEven(spanDeg / AngularStep(angles)))
	w = max(3, w|1)
	if w > n {
		if n%2 == 1 {
			w = n
		} else {
			w = n - 1
		}
	}
	if w < 3 {
		w = 3
	}
	return w
}

// MedianFilterWrap — скользящая медиана по КОЛЬЦУ (профиль 0..360 замкнут).
func MedianFilterWrap(x []float64, window int) []float64 {
	n := len(x)
	w := max(3, window|1)
	if w > n {
		if n%2 == 1 {
			w = n
		} else {
			w = n - 1
		}
	}
	if w < 3 || n < 3 {
		out := make([]float64, n)
		m := Median(x)
		for i := range out {
			out[i] = m
		}
		return out
	}
	out := make([]float64, n)
	win := make([]float64, w)
	h := w / 2
	for i := 0; i < n; i++ {
		for k := 0; k < w; k++ {
			idx := ((i-h+k)%n + n) % n // замыкание кольца
			win[k] = x[idx]
		}
		out[i] = Median(win)
	}
	return out
}

// SmoothWrap — скользящее среднее по кольцу (как np.convolve в zones.py).
func SmoothWrap(x []float64, window int) []float64 {
	n := len(x)
	w := max(3, window|1)
	if n < 3 || w > n {
		if n%2 == 1 {
			w = n
		} else {
			w = max(1, n-1)
		}
	}
	if w < 3 {
		out := make([]float64, len(x))
		copy(out, x)
		return out
	}
	out := make([]float64, n)
	h := w / 2
	for i := 0; i < n; i++ {
		sum := 0.0
		for k := -h; k <= h; k++ {
			sum += x[((i+k)%n+n)%n]
		}
		out[i] = sum / float64(w)
	}
	return out
}

// WrapDiffAbs — |первая разность по кольцу| (последняя точка -> первая).
func WrapDiffAbs(x []float64) []float64 {
	n := len(x)
	out := make([]float64, n)
	for i := 0; i < n; i++ {
		out[i] = math.Abs(x[(i+1)%n] - x[i])
	}
	return out
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func maxF(a, b float64) float64 {
	if a > b {
		return a
	}
	return b
}

func abs(x float64) float64 { return math.Abs(x) }
