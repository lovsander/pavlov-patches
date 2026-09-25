package pappa

import (
	"fmt"
	"math"
)

// Patch — один патч модели (полином + опциональные термины фичера ям).
type Patch struct {
	Center        float64   // °, глобальный угол центра
	HalfSector    float64   // °, плато веса = 1
	HalfTrain     float64   // °, обучающее окно
	HalfUse       float64   // °, окно применения (blend)
	Coefs         []float64 // полином, старшая степень первая
	Degree        int
	NPoints       int
	PitOffsetsDeg []float64 // смещения центров ям в локальной системе патча
	PitCoefs      []float64 // амплитуды оконных гауссов

	// Метрики (пишутся в документ .pappa.json как metrics/stats) — те же
	// определения, что в python/pappa/core/patch_approximator.py.
	AmplitudeMM    float64 // P95 - P5 по точкам своего сектора (справочная)
	MeanRadiusMM   float64
	AmplitudeNorm  float64
	RMSESelectedMM float64 // RMSE выбранной степени на обучающем окне
	RMSEBestMM     float64 // лучший RMSE по всем рассмотренным степеням
	NTrainPoints   int
	RMSEMm         float64 // статистика остатков обучающего окна
	MAEMm          float64
	MaxErrMM       float64
	Correlation    float64
}

// ModelOptions — параметры модели (значения по умолчанию = MODEL_DEFAULTS).
type ModelOptions struct {
	NPatches       int
	PhaseDeg       float64
	DegMin         int
	DegMax         int
	AmplitudeScale float64
	OverlapTrain   float64
	OverlapUse     float64
	DegElbowTol    float64
	// DegFloorMM — абсолютный пол RMSE (мм): «идеально точно» -> дальше степень
	// не наращиваем. 0 (по умолчанию) = выключен: поведение как у Python-референса.
	// Включение МЕНЯЕТ контракт (степени на гладких окнах перестают зависеть от
	// разрядности решателя) и требует той же правки в Python + перегенерации
	// spec/conformance (см. docs/embedded.md §11).
	DegFloorMM float64
	CoordMode  string
}

// DefaultModelOptions — раскладка пайплайна из CONTEXT §25 (N=7, фаза 24.75°).
func DefaultModelOptions() ModelOptions {
	return ModelOptions{
		NPatches: 7, PhaseDeg: 24.75, DegMin: 4, DegMax: 14,
		AmplitudeScale: 180.0, OverlapTrain: 15.0, OverlapUse: 5.0,
		DegElbowTol: 0.05, CoordMode: "normalized",
	}
}

// PitShape — форма оконного гаусса (PIT_DEFAULTS).
type PitShape struct {
	SigmaDeg    float64
	CoreSigma   float64
	WindowSigma float64
	MinAmp      float64
	Tapering    bool
}

// DefaultPitShape — значения из python/pappa/core/pit_feature.py.
func DefaultPitShape() PitShape {
	return PitShape{SigmaDeg: 3.0, CoreSigma: 2.0, WindowSigma: 3.2,
		MinAmp: 3e-3, Tapering: true}
}

// Model — аппроксиматор PAPPA: патчи по нормированной координате x/half_train,
// правило степени «локоть», нормированное smoothstep-смешивание (partition of
// unity), опционально оконные гауссовы ямы.
type Model struct {
	Opt      ModelOptions
	Shape    PitShape
	Pits     []float64
	Patches  []Patch
	Centers  []float64
	HalfSect float64
	Fitted   bool
}

// NewModel — модель с параметрами opt; pits — глобальные углы центров ям.
func NewModel(opt ModelOptions, pits []float64) *Model {
	if opt.DegMin%2 != 0 {
		opt.DegMin++
	}
	if opt.DegMax%2 != 0 {
		opt.DegMax++
	}
	if opt.CoordMode == "" {
		opt.CoordMode = "normalized"
	}
	m := &Model{Opt: opt, Shape: DefaultPitShape()}
	for _, p := range pits {
		v := math.Mod(p, 360.0)
		if v < 0 {
			v += 360.0
		}
		m.Pits = append(m.Pits, v)
	}
	return m
}

func (m *Model) local(dxDeg, halfTrain float64) float64 {
	if m.Opt.CoordMode == "raw" {
		return dxDeg
	}
	return dxDeg / halfTrain
}

// PitShapeDeg — оконный гаусс как функция расстояния от центра ямы.
func (m *Model) PitShapeDeg(dDeg float64) float64 {
	d := math.Abs(dDeg)
	val := math.Exp(-d * d / (2 * m.Shape.SigmaDeg * m.Shape.SigmaDeg))
	if !m.Shape.Tapering {
		return val
	}
	core := m.Shape.CoreSigma * m.Shape.SigmaDeg
	edge := m.Shape.WindowSigma * m.Shape.SigmaDeg
	if edge <= core {
		return val
	}
	t := (edge - d) / (edge - core)
	if t < 0 {
		t = 0
	}
	if t > 1 {
		t = 1
	}
	return val * t * t * (3 - 2*t)
}

func (m *Model) pitOffsets(centerDeg, halfWinDeg float64) []float64 {
	var out []float64
	for _, p := range m.Pits {
		if dx := CircLocal(p, centerDeg); math.Abs(dx) <= halfWinDeg {
			out = append(out, dx)
		}
	}
	return out
}

func (m *Model) weight(dDeg, halfUse float64) float64 {
	if dDeg <= m.HalfSect {
		return 1
	}
	if dDeg <= halfUse {
		return smoothstep(1 - (dDeg-m.HalfSect)/(halfUse-m.HalfSect))
	}
	return 0
}

// estimateDegree — правило «локтя»: наименьшая чётная степень, на которой RMSE
// обучающего окна не хуже лучшей более чем на DegElbowTol. Возвращает степень,
// число точек окна, RMSE выбранной и лучшей степени.
func (m *Model) estimateDegree(angles, radii []float64, center,
	halfTrain float64) (int, int, float64, float64) {

	var xs, ys []float64
	for _, shift := range []float64{-360, 0, 360} {
		for i := range angles {
			dx := angles[i] + shift - center
			if dx >= -halfTrain && dx <= halfTrain {
				xs = append(xs, m.local(dx, halfTrain))
				ys = append(ys, radii[i])
			}
		}
	}
	n := len(xs)
	if n < 5 {
		return m.Opt.DegMin, 0, 0, 0
	}

	bestDeg, bestRMSE := m.Opt.DegMin, math.Inf(1)
	type degRMSE struct {
		deg  int
		rmse float64
	}
	var results []degRMSE

	if m.Opt.CoordMode == "raw" {
		// Легаси-режим без нормировки: базис Чебышёва требует x ∈ [-1, 1],
		// поэтому здесь остаётся прежний путь (отдельный МНК на степень).
		for deg := m.Opt.DegMin; deg <= m.Opt.DegMax; deg += 2 {
			coefs, err := Polyfit(xs, ys, deg)
			if err != nil {
				continue
			}
			sse := 0.0
			for i := 0; i < n; i++ {
				e := Polyval(coefs, xs[i]) - ys[i]
				sse += e * e
			}
			r := math.Sqrt(sse / float64(n))
			results = append(results, degRMSE{deg, r})
			if r < bestRMSE {
				bestRMSE, bestDeg = r, deg
			}
		}
	} else {
		// ОДНО накопление Грама в базисе Чебышёва даёт сразу все степени:
		// нормальная матрица степени d — ведущая подматрица матрицы DegMax.
		// Данные центрируем (y - yref): иначе SSE = Q - cᵗb теряет разряды.
		// Замерено на эталонных данных: 2.5x быстрее на фазе обучения при тех же
		// числах (docs/embedded.md §11-13).
		yref := 0.0
		for _, v := range ys {
			yref += v
		}
		yref /= float64(n)

		dmax := m.Opt.DegMax
		p := dmax + 1
		gram := make([]float64, p*p) // верхний треугольник, симметризация ниже
		rhs := make([]float64, p)
		T := make([]float64, p)
		for i := 0; i < n; i++ {
			ChebRow(xs[i], dmax, T)
			yc := ys[i] - yref
			for a := 0; a < p; a++ {
				rhs[a] += T[a] * yc
				for c := a; c < p; c++ {
					gram[a*p+c] += T[a] * T[c]
				}
			}
		}
		for a := 0; a < p; a++ {
			for c := a + 1; c < p; c++ {
				gram[c*p+a] = gram[a*p+c]
			}
		}

		for deg := m.Opt.DegMin; deg <= dmax; deg += 2 {
			nn := deg + 1
			A := make([][]float64, nn)
			b := make([]float64, nn)
			for r := 0; r < nn; r++ {
				A[r] = make([]float64, nn)
				for c := 0; c < nn; c++ {
					A[r][c] = gram[r*p+c]
				}
				b[r] = rhs[r]
			}
			coefs, err := LstsqQR(A, b)
			if err != nil {
				continue
			}
			// RMSE — по ЯВНЫМ остаткам (Кленшоу), как и по точкам окна раньше.
			sse := 0.0
			for i := 0; i < n; i++ {
				e := ChebSum(coefs, deg, xs[i]) - (ys[i] - yref)
				sse += e * e
			}
			r := math.Sqrt(sse / float64(n))
			results = append(results, degRMSE{deg, r})
			if r < bestRMSE {
				bestRMSE, bestDeg = r, deg
			}
			// Абсолютный пол (если включён): дальше степень не наращиваем, иначе
			// на гладких окнах её выбирает разрядность решателя, а не данные.
			if m.Opt.DegFloorMM > 0 && r <= m.Opt.DegFloorMM {
				break
			}
		}
	}

	limit := bestRMSE * (1 + m.Opt.DegElbowTol)
	for _, res := range results { // строки идут по возрастанию степени
		if res.rmse <= limit {
			return res.deg, n, res.rmse, bestRMSE
		}
	}
	return bestDeg, n, bestRMSE, bestRMSE
}

// sectorMetrics — справочные метрики сектора: P95-P5 по точкам своего сектора
// (амплитудная шкала оставлена только как метрика, степень она не выбирает).
func (m *Model) sectorMetrics(angles, radii []float64, center float64) (float64, float64) {
	var sec []float64
	for i := range angles {
		if CircDist(angles[i], center) <= m.HalfSect {
			sec = append(sec, radii[i])
		}
	}
	if len(sec) < 5 {
		return 0, 0
	}
	amp := PercentileLinear(sec, 95) - PercentileLinear(sec, 5)
	mean := 0.0
	for _, v := range sec {
		mean += v
	}
	mean /= float64(len(sec))
	return amp, mean
}

// Fit — обучение модели (коэффициенты патчей и термины фичера).
func (m *Model) Fit(angles, radii []float64) error {
	if len(angles) != len(radii) {
		return fmt.Errorf("fit: длины массивов не совпадают")
	}
	if len(angles) < 10 {
		return fmt.Errorf("fit: слишком мало точек")
	}

	sector := 360.0 / float64(m.Opt.NPatches)
	m.HalfSect = sector / 2
	m.Centers = m.Centers[:0]
	for i := 0; i < m.Opt.NPatches; i++ {
		c := math.Mod(float64(i)*sector+m.HalfSect+m.Opt.PhaseDeg, 360.0)
		if c < 0 {
			c += 360.0
		}
		m.Centers = append(m.Centers, c)
	}

	anglesExt := make([]float64, 0, len(angles)*3)
	radiiExt := make([]float64, 0, len(radii)*3)
	for _, shift := range []float64{-360, 0, 360} {
		for i := range angles {
			anglesExt = append(anglesExt, angles[i]+shift)
			radiiExt = append(radiiExt, radii[i])
		}
	}

	halfTrain := m.HalfSect + m.Opt.OverlapTrain
	halfUse := m.HalfSect + m.Opt.OverlapUse

	m.Patches = m.Patches[:0]
	for _, c := range m.Centers {
		deg, nTrain, rmseSelected, rmseBest := m.estimateDegree(angles, radii, c, halfTrain)

		var xs, ys []float64
		for i := range anglesExt {
			if dx := anglesExt[i] - c; dx >= -halfTrain && dx <= halfTrain {
				xs = append(xs, m.local(dx, halfTrain))
				ys = append(ys, radiiExt[i])
			}
		}
		if len(xs) < 5 {
			continue
		}

		offsets := m.pitOffsets(c, halfTrain)
		design := make([][]float64, len(xs))
		for i := range xs {
			row := make([]float64, deg+1+len(offsets))
			p := 1.0
			for k := deg; k >= 0; k-- {
				row[k] = p
				p *= xs[i]
			}
			for j, off := range offsets {
				dDeg := math.Abs(xs[i]-off/halfTrain) * halfTrain
				row[deg+1+j] = m.PitShapeDeg(dDeg)
			}
			design[i] = row
		}
		coef, err := LstsqQR(design, ys)
		if err != nil {
			return err
		}

		polyCoef := append([]float64(nil), coef[:deg+1]...)
		pitCoef := append([]float64(nil), coef[deg+1:]...)

		// Отсечка ям, которые в окне патча «не видны» (pit_min_amp).
		var keptOffsets, keptCoefs []float64
		for j, off := range offsets {
			maxAbs := 0.0
			for i := range xs {
				dDeg := math.Abs(xs[i]-off/halfTrain) * halfTrain
				if v := math.Abs(pitCoef[j] * m.PitShapeDeg(dDeg)); v > maxAbs {
					maxAbs = v
				}
			}
			if maxAbs >= m.Shape.MinAmp {
				keptOffsets = append(keptOffsets, off)
				keptCoefs = append(keptCoefs, pitCoef[j])
			}
		}

		// Метрики и статистика остатков (как metrics/stats в документе).
		amp, meanSec := m.sectorMetrics(angles, radii, c)
		ampNorm := 0.0
		if meanSec > 0 {
			ampNorm = amp / meanSec
		}
		fitVals := make([]float64, len(xs))
		for i := range xs {
			v := Polyval(polyCoef, xs[i])
			for j, off := range keptOffsets {
				dDeg := math.Abs(xs[i]-off/halfTrain) * halfTrain
				v += keptCoefs[j] * m.PitShapeDeg(dDeg)
			}
			fitVals[i] = v
		}
		sse, sae, maxErr := 0.0, 0.0, 0.0
		for i := range xs {
			e := fitVals[i] - ys[i]
			sse += e * e
			sae += math.Abs(e)
			maxErr = math.Max(maxErr, math.Abs(e))
		}
		n := float64(len(xs))
		rmse := math.Sqrt(sse / n)
		mae := sae / n

		// корреляция модель/данные по обучающему окну
		mf, my := 0.0, 0.0
		for i := range xs {
			mf += fitVals[i]
			my += ys[i]
		}
		mf /= n
		my /= n
		cov, vf, vy := 0.0, 0.0, 0.0
		for i := range xs {
			df := fitVals[i] - mf
			dy := ys[i] - my
			cov += df * dy
			vf += df * df
			vy += dy * dy
		}
		corr := 0.0
		if vf > 0 && vy > 0 {
			corr = cov / math.Sqrt(vf*vy)
		}

		m.Patches = append(m.Patches, Patch{
			Center: c, HalfSector: m.HalfSect, HalfTrain: halfTrain, HalfUse: halfUse,
			Coefs: polyCoef, Degree: deg, NPoints: len(xs),
			PitOffsetsDeg: keptOffsets, PitCoefs: keptCoefs,
			AmplitudeMM: amp, MeanRadiusMM: meanSec, AmplitudeNorm: ampNorm,
			RMSESelectedMM: rmseSelected, RMSEBestMM: rmseBest, NTrainPoints: nTrain,
			RMSEMm: rmse, MAEMm: mae, MaxErrMM: maxErr, Correlation: corr,
		})
	}
	m.Fitted = true
	return nil
}

// EvalPart — контур модели: part = "total" | "poly" | "pit".
func (m *Model) EvalPart(angles []float64, part string) ([]float64, error) {
	if !m.Fitted {
		return nil, fmt.Errorf("eval: сначала вызовите Fit")
	}
	halfUse := m.HalfSect + m.Opt.OverlapUse
	out := make([]float64, len(angles))
	for i, a := range angles {
		sumWV, sumW := 0.0, 0.0
		for _, p := range m.Patches {
			w := m.weight(CircDist(a, p.Center), halfUse)
			if w <= 0 {
				continue
			}
			xs := m.local(CircLocal(a, p.Center), p.HalfTrain)
			v := 0.0
			if part != "pit" {
				v += Polyval(p.Coefs, xs)
			}
			if part != "poly" {
				for j, off := range p.PitOffsetsDeg {
					dDeg := math.Abs(xs-off/p.HalfTrain) * p.HalfTrain
					v += p.PitCoefs[j] * m.PitShapeDeg(dDeg)
				}
			}
			sumWV += w * v
			sumW += w
		}
		if sumW > 0 {
			out[i] = sumWV / sumW
		}
	}
	return out, nil
}

// Eval — полный контур (полином + ямы).
func (m *Model) Eval(angles []float64) ([]float64, error) { return m.EvalPart(angles, "total") }

// Degrees — степени по патчам.
func (m *Model) Degrees() []int {
	out := make([]int, 0, len(m.Patches))
	for _, p := range m.Patches {
		out = append(out, p.Degree)
	}
	return out
}

// PitTermCount — число терминов фичера в базисе (как в документах).
func (m *Model) PitTermCount() int {
	n := 0
	for _, p := range m.Patches {
		n += len(p.PitOffsetsDeg)
	}
	return n
}
