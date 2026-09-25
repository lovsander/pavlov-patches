package pappa

import (
	"fmt"
	"math"
)

// Polyval — значение полинома по схеме Горнера (coefs[0] — старшая степень).
func Polyval(coefs []float64, x float64) float64 {
	result := 0.0
	for _, c := range coefs {
		result = result*x + c
	}
	return result
}

// LstsqQR — решение переопределённой системы A x = b методом наименьших
// квадратов (отражения Хаусхолдера + обратная подстановка), m >= n.
// QR, а не нормальные уравнения: numpy считает np.polyfit/lstsq через SVD/QR,
// и чтобы коэффициенты совпадали с референсом, нужен столь же устойчивый путь.
func LstsqQR(a [][]float64, b []float64) ([]float64, error) {
	m := len(a)
	if m == 0 {
		return nil, fmt.Errorf("lstsq: пустая матрица")
	}
	n := len(a[0])
	if len(b) != m {
		return nil, fmt.Errorf("lstsq: длины A (%d) и b (%d) не совпадают", m, len(b))
	}
	if m < n {
		return nil, fmt.Errorf("lstsq: нужно m >= n")
	}

	// A и b копируем: работа идёт «на месте»
	mat := make([][]float64, m)
	for i := range mat {
		mat[i] = make([]float64, n)
		copy(mat[i], a[i])
	}
	rhs := make([]float64, m)
	copy(rhs, b)

	for k := 0; k < n; k++ {
		norm := 0.0
		for i := k; i < m; i++ {
			norm += mat[i][k] * mat[i][k]
		}
		norm = math.Sqrt(norm)
		if norm < 1e-300 {
			continue
		}
		alpha := norm
		if mat[k][k] > 0 {
			alpha = -norm
		}
		v := make([]float64, m)
		for i := k; i < m; i++ {
			v[i] = mat[i][k]
		}
		v[k] -= alpha
		vnorm2 := 0.0
		for i := k; i < m; i++ {
			vnorm2 += v[i] * v[i]
		}
		if vnorm2 < 1e-300 {
			continue
		}
		for j := k; j < n; j++ {
			s := 0.0
			for i := k; i < m; i++ {
				s += v[i] * mat[i][j]
			}
			c := 2 * s / vnorm2
			for i := k; i < m; i++ {
				mat[i][j] -= c * v[i]
			}
		}
		sb := 0.0
		for i := k; i < m; i++ {
			sb += v[i] * rhs[i]
		}
		cb := 2 * sb / vnorm2
		for i := k; i < m; i++ {
			rhs[i] -= cb * v[i]
		}
	}

	x := make([]float64, n)
	for i := n - 1; i >= 0; i-- {
		s := rhs[i]
		for j := i + 1; j < n; j++ {
			s -= mat[i][j] * x[j]
		}
		if math.Abs(mat[i][i]) < 1e-300 {
			return nil, fmt.Errorf("lstsq: вырожденная система")
		}
		x[i] = s / mat[i][i]
	}
	return x, nil
}

// Polyfit — МНК-подгонка полинома степени deg по НОРМИРОВАННОЙ координате
// x ∈ [-1, 1]. Возвращает коэффициенты от старшей степени к младшей (как np.polyfit).
func Polyfit(xNorm, y []float64, deg int) ([]float64, error) {
	if len(xNorm) != len(y) {
		return nil, fmt.Errorf("polyfit: длины не совпадают")
	}
	m := len(xNorm)
	n := deg + 1
	a := make([][]float64, m)
	for i := 0; i < m; i++ {
		a[i] = make([]float64, n)
		p := 1.0
		for j := 0; j < n; j++ { // a[i][j] = x^(deg-j)
			a[i][n-1-j] = p
			p *= xNorm[i]
		}
	}
	return LstsqQR(a, y)
}

// CircDist — кратчайшее расстояние по кольцу (градусы).
func CircDist(a, b float64) float64 {
	d := math.Mod(a-b+180.0, 360.0)
	if d < 0 {
		d += 360.0
	}
	return math.Abs(d - 180.0)
}

// CircLocal — смещение по кольцу в (-180, 180].
func CircLocal(a, b float64) float64 {
	d := math.Mod(a-b+180.0, 360.0)
	if d < 0 {
		d += 360.0
	}
	return d - 180.0
}

func smoothstep(t float64) float64 {
	if t < 0 {
		return 0
	}
	if t > 1 {
		return 1
	}
	return t * t * (3 - 2*t)
}

// ChebRow — значения T_0(x)..T_degMax(x) в срез T (базис Чебышёва, x ∈ [-1, 1]).
//
// Зачем он в порту: свип степеней раньше стоил 6 факторизаций QR на патч (это
// 85 % времени обучения). У базиса Чебышёва есть префиксное свойство: нормальная
// матрица степени d — ведущая подматрица матрицы DegMax, поэтому достаточно
// ОДНОГО накопления Грама, чтобы получить решения всех степеней сразу.
func ChebRow(x float64, degMax int, T []float64) {
	T[0] = 1.0
	if degMax >= 1 {
		T[1] = x
	}
	for k := 2; k <= degMax; k++ {
		T[k] = 2*x*T[k-1] - T[k-2]
	}
}

// ChebSum — Σ_{k=0}^{deg} coefs[k]·T_k(x) по схеме Кленшоу (устойчиво, без
// построения самих T_k).
func ChebSum(coefs []float64, deg int, x float64) float64 {
	b1, b2 := 0.0, 0.0
	for k := deg; k >= 1; k-- {
		b0 := 2*x*b1 - b2 + coefs[k]
		b2 = b1
		b1 = b0
	}
	return x*b1 - b2 + coefs[0]
}
