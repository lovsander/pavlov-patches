"""
open_shapes.py — РАЗОМКНУТЫЕ ФОРМЫ на патчах Павлова: что остаётся от метода без кольца.

ВОПРОС (на него отвечает скрипт, а не рассуждения в чате):
  1) ломается ли сам метод, если у формы есть ДВА СВОБОДНЫХ КОНЦА (нет замыкания
     по кругу): перекрытие, smoothstep-блендинг, правило «локтя», выбор степени?
  2) что происходит на концах — насколько модель «убегает» от данных и где это
     видно в мм (крайние 5% длины)?
  3) какие привязки концов это лечат и сколько они стоят (max|Δ|, RMSE)?
  4) остаётся ли смысл в «павловости» (адаптивная степень + обучение шире
     применения + осмысленные швы) на разомкнутых формах, или то же самое дают
     глобальный полином / LPR / сплайн / Фурье?

ЧТО ИМЕННО ТЕРЯЕТСЯ ПРИ ПЕРЕХОДЕ «КОЛЬЦО -> РАЗОМКНУТАЯ ФОРМА»
  * окружность -> параметр t = нормированная длина по ХОРДЕ (0..1) вдоль скана;
    полярный угол больше не нужен — «градусы» уходят вместе с кольцом;
  * звезда (лучи-центры из центра тела) -> цепочка патчей ВДОЛЬ кривой: центр
    патча = точка на кривой, локальная координата x = (t - центр)/half_train
    в каноне [-1,1] — тот же канон, что и в PatchApproximator;
  * phase_deg (поворот сетки на 24.75°) -> сдвиг сетки ВДОЛЬ длины: роль та же
    (увести швы от дефектов), но сетку у разомкнутой формы не «повернуть» —
    её начало нужно к чему-то привязать (gauge);
  * ЗАМЫКАНИЕ КОЛЬЦА — главная потеря. В замкнутом случае каждый шов окружён
    точками с двух сторон (полином на краю сектора «видит» соседний сектор) и
    доезжает по данным. У разомкнутой формы у крайних патчей окно ОБРЕЗАНО
    доменом, а применяются они за его пределами -> классический boundary bias
    локальной регрессии, то самое «концы убегают от графика».

ЧЕМ ПРИВЯЗЫВАЮТ КОНЦЫ (варианты, которые тут замеряются):
  free         ничего: крайний патч учится на обрезанном окне (baseline-провал);
  margin       «скан шире модели»: сетка строится на внутренней части длины, все
               окна обучения целиком лежат на данных (обобщение принципа
               «обучение шире применения» на концы);
  mirror_even  зеркало данных за край (чётное продолжение): значение на краю
               сохраняется, производная обнуляется (край «полочкой»);
  mirror_odd   зеркало с отражением знака производной (нечётное продолжение):
               сохраняются и значение, и наклон;
  clamp_v      связь по крайнему патчу: p(край) = r(край) — МНК с ограничениями
               (множители Лагранжа), как «зажатый» конец у сплайна;
  clamp_vd     то же + связь по производной (аналог G1 на краю);
  deg_bonus    локальное повышение степени крайних патчей на +2 (известное
               лечение boundary bias: на границе порядок смещения хуже на
               единицу, запас степени его возвращает).

ЭТАЛОН И ЧЕСТНОСТЬ: данные — тот же синтетический CSV, что и в остальных
исследованиях (истина `radius_ideal_mm` от генератора), выбросы убирает тот же
авто-очиститель (iqr). Сравнение всегда идёт по ИСТИНЕ генератора на равномерной
сетке 0.05° внутри открытого участка, а не по точкам скана.

РЕЗУЛЬТАТ (числа — из вывода скрипта; см. также python/research/README.md):
  * МЕТОД НЕ ЛОМАЕТСЯ. Перекрытие, smoothstep-блендинг и правило «локтя» работают
    без кольца: на участке A (240°, трещина внутри) разомкнутая модель при привязке
    clamp_vd даёт RMSE 0.0177 / max 0.0673 мм против 0.0235 / 0.0851 у той же
    модели на полном круге (окна у кольца шире — сравнивать по порядку величины).
  * ЛОМАЕТСЯ РОВНО КРАЙ. Привязка free: RMSE 0.015-0.019, а на крайних 5% длины
    ошибка вырастает в 2-3 раза (RMSE хвост 0.011-0.027, max хвост 0.030-0.081),
    причём ошибка прижата к резу: |Δr| на краю 0.023 / 0.033 / 0.028 мм для A / B / C.
    Это и есть boundary bias локальной регрессии: окно крайнего патча обрезано
    доменом, а применяется он за его пределами.
  * ЛУЧШЕЕ ЛЕЧЕНИЕ — margin («скан шире модели»), и оно же самое дешёвое: домен
    сжимается на m с каждой стороны, зато все окна обучения целиком лежат на
    данных. margin 6% на B: RMSE 0.0191 -> 0.0153, max хвост 0.0808 -> 0.0520,
    край R 0.0548 -> 0.0196; на A край L 0.0233 -> 0.0058; на C край L 0.0277 ->
    0.0126. В О5б лучшая комбинация — free + margin 4-6% (RMSE 0.0151-0.0155,
    max хвост 0.0157-0.0177 при домене 0.92-0.88 длины скана). Цена: крайние
    4-6% длины модель вообще не описывает.
  * clamp_v / clamp_vd — для случая «домен нужен целиком» (домен 1.00): связь по
    крайнему патчу через множители Лагранжа превращает «убегание» 0.033-0.055 мм
    в ошибку датума, т.е. в ~0.02 мм (B: край R 0.0548 -> 0.0201; A: край L 0.0233
    -> 0.0129-0.0218). Добавка связи по производной (clamp_vd) сама по себе не
    помогает, но в паре с deg_bonus даёт лучший вариант с доменом 1.00 (B: 0.0174 /
    0.0739 против 0.0222 / 0.0871 у чистого clamp_vd). Потолок привязки — точность
    датума: О5в показывает |Δ| датума 0.020-0.028 мм при шуме измерений p50 = 0.067 мм,
    то есть привязка точнее датума быть не может.
  * ЗЕРКАЛО ВРЕДНО: mirror_even на правом резе B даёт край R 0.1849 против 0.0548
    у free (край «полочкой» противоречит данным), mirror_odd ≈ free. НЕ СТАВИТЬ
    margin и clamp одновременно: clamp внутри данных борется с уже обученным
    полиномом (О5б: free+margin 4% = 0.0155 / 0.0157, а clamp_vd+margin 4% =
    0.0170 / 0.0310).
  * «ПАВЛОВОСТЬ» ВЫЖИВАЕТ: адаптивная степень (правило локтя, 48 коэффициентов)
    даёт ту же точность, что фиксированная 8 (63 коэффициента) — 0.0177 против
    0.0179, то есть выигрыш в компактности, а не в RMSE; обучение шире применения
    имеет тот же оптимум, что у кольца (overlap_train 0.3-0.58; без перекрытия max
    растёт с 0.0586 до 0.1299); очистка выбросов обязательна (0.0177 против 0.0393).
    Против базовых линий: патчи ≈ сглаживающий сплайн (0.0177 / 0.0673 против
    0.0172 / 0.0755) и лучше LPR deg=8 по хвосту (max 0.0673 против 0.0923);
    глобальный полином бесполезен (0.125-0.189), а «Фурье, замкнутый на длину
    участка» проваливается именно на резах (край L/R 0.25 / 0.21) — это и есть цена
    забытого замыкания.
  * РЕКОМЕНДАЦИЯ: разомкнутая форма -> boundary="free" + margin 0.04-0.06, если
    края детали допускается не описывать; если домен нужен целиком — boundary=
    "clamp_vd" + deg_bonus (краевая ошибка ~0.02 мм, ошибка «уходит» с обоих концов).
    Роль phase_deg (поворот сетки) на разомкнутой форме заменяется сдвигом сетки
    вдоль длины, и он работает как ручка ПОКРЫТИЯ: shift +0.2..+0.4 убирает дребезг
    левого края (0.025 -> 0.009 у free), но сетка перестаёт доезжать до реза.

Запуск: <python> research/open_shapes.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import math

import numpy as np

from pappa.core.patch_approximator import PatchApproximator
from pappa.io.dataset import load_sections
from pappa.paths import resolve_path, resolve_plot

# --- конфигурация -----------------------------------------------------------
CSV = "synthetic_data.csv"
IDEAL_COLUMN = "radius_ideal_mm"
CLEANER = {"mode": "auto", "auto": {"method": "iqr"}}

# Секции и открытые участки (градусы скана). A — «трещина в середине длины»,
# B — «трещина в 20° от реза» (жёсткий случай: крайний патч обязан описать
# половину ямы), C — 180° (совсем короткая разомкнутая форма).
SECTIONS = [0, 2, 5, 9]
SPANS = {
    "A 240° трещина внутри": (40.0, 280.0),
    "B 240° трещина у края": (70.0, 310.0),
    "C 180° короткая": (40.0, 220.0),
}

# Модель: те же константы, что в MODEL_DEFAULTS (core/pit_feature.py), только
# перекрытия заданы В ДОЛЯХ ПОЛУСЕКТОРА — так относительная геометрия окон не
# зависит от того, кольцо это или открытая длина:
#   кольцо: N=7, half_sector = 360/14 = 25.71°, overlap_train = 15° -> 0.583,
#           overlap_use = 5° -> 0.195.
N_PATCHES = 7
DEG_MIN, DEG_MAX = 4, 14
DEG_ELBOW_TOL = 0.05
OVERLAP_TRAIN = 0.583
OVERLAP_USE = 0.195

# Доля длины, по которой оценивается датум края (значение/наклон на резе).
EDGE_BAND = 0.03


# --- данные: открытый участок скана ----------------------------------------

def open_interp(a, y, grid):
    """Интерполяция НЕзамкнутого профиля на сетку (без заворота через 360°)."""
    a = np.asarray(a, dtype=float)
    y = np.asarray(y, dtype=float)
    order = np.argsort(a)
    return np.interp(np.asarray(grid, dtype=float), a[order], y[order])


def arc_length_param(a, r):
    """
    Параметр разомкнутой формы: нормированная длина по ХОРДЕ вдоль скана.

    Для каждой измеренной точки считается накопленная длина ломаной
    (r·cosθ, r·sinθ) от начала участка, результат нормируется на [0, 1]. Это то,
    что остаётся от «угла» у произвольной открытой кривой: монотонная нумерация
    точек вдоль тела. Возвращает (t, theta_to_t) — саму параметризацию и
    функцию пересчёта «угол скана -> t» (та же монотонная связь, чтобы эталон на
    угловой сетке сравнивался в тех же физических точках).
    """
    a = np.asarray(a, dtype=float)
    r = np.asarray(r, dtype=float)
    x = r * np.cos(np.radians(a))
    y = r * np.sin(np.radians(a))
    d = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    t = d / d[-1]
    return t, lambda angle: np.interp(np.asarray(angle, dtype=float), a, t)


def error_stats(t, model, truth):
    """
    Метрики модели против истины генератора.

    rmse / max        — по всему участку;
    rmse_end/max_end  — только в крайних 5% длины (там, где «убегают» концы);
    drift_lo/drift_hi — |Δ| в самих крайних точках (цена привязки концов).
    """
    model = np.asarray(model, dtype=float)
    truth = np.asarray(truth, dtype=float)
    t = np.asarray(t, dtype=float)
    d = model - truth
    end = (t <= 0.05) | (t >= 0.95)
    return {
        "rmse": float(np.sqrt(np.mean(d ** 2))),
        "max": float(np.max(np.abs(d))),
        "rmse_end": float(np.sqrt(np.mean(d[end] ** 2))) if end.any() else float("nan"),
        "max_end": float(np.max(np.abs(d[end]))) if end.any() else float("nan"),
        "drift_lo": float(abs(d[0])),
        "drift_hi": float(abs(d[-1])),
    }


def prepare(section, a0, a1, grid_step=0.05, cleaned=True):
    """
    Сечение -> открытый участок [a0, a1] °: точки (после очистки, если
    cleaned=True), параметр t, равномерная угловая сетка и истина генератора.
    """
    a, r, ideal = section["angles"], section["radii"], section["ideal"]
    if cleaned:
        a, r = section["angles_clean"], section["radii_clean"]
    inside = (a >= a0) & (a <= a1)
    a_in, r_in = a[inside], r[inside]
    t_in, theta_to_t = arc_length_param(a_in, r_in)

    grid_a = np.arange(a0, a1 + 1e-9, grid_step)
    grid_t = theta_to_t(grid_a)
    truth = open_interp(section["angles"], ideal, grid_a)
    return {
        "a": a_in, "r": r_in, "t": t_in,
        "grid_a": grid_a, "grid_t": grid_t, "truth": truth,
        "span_deg": a1 - a0, "t_to_a": lambda tt: np.interp(tt, t_in, a_in),
    }


def load_data():
    """Все сечения из CSV с той же очисткой, что и в остальных исследованиях."""
    return load_sections(resolve_path(CSV), IDEAL_COLUMN, CLEANER)


# --- модель: патчи Павлова на разомкнутой форме -----------------------------

def _smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _robust_edge_fit(u, r, u_edge, deg=2, n_iter=2):
    """
    Значение и наклон профиля В КРАЙНЕЙ ТОЧКЕ (u_edge) по полосе у края.

    Квадратичный МНК с двумя проходами отбраковки выбросов (median ± 3·MAD):
    одиночные вылеты у реза не должны утаскивать датум. Возвращает (r(u_edge),
    dr/du(u_edge)).
    """
    x = np.asarray(u, float) - float(u_edge)
    r = np.asarray(r, float)
    coefs = np.polyfit(x, r, deg)
    for _ in range(n_iter):
        resid = r - np.polyval(coefs, x)
        mad = float(np.median(np.abs(resid - np.median(resid)))) * 1.4826
        if mad <= 0:
            break
        keep = np.abs(resid) <= 3.0 * mad
        if keep.sum() < deg + 1:
            break
        coefs = np.polyfit(x[keep], r[keep], deg)
    return float(np.polyval(coefs, 0.0)), float(np.polyder(coefs)[-1])


def polyfit_constrained(x, y, deg, cons):
    """
    МНК со связями: min ||A·c - y||² при C·c = d (множители Лагранжа).

    cons — список (порядок производной, точка, значение): порядок 0 — значение
    полинома (Дирихле), 1 — наклон (Нейман). Так крайний патч «привязывается» к
    краю — это то же, что «зажатые» концы у сплайнов, только локально и без
    глобальной системы.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if not cons:
        return np.polyfit(x, y, deg)
    A = np.vander(x, deg + 1)                  # столбцы x^deg ... x^0

    C = np.zeros((len(cons), deg + 1))
    d = np.zeros(len(cons))
    for i, (order, x0, value) in enumerate(cons):
        for j in range(deg + 1):
            power = deg - j
            if power < order:
                continue
            factor = math.factorial(power) / math.factorial(power - order)
            C[i, j] = factor * (x0 ** (power - order))
        d[i] = value

    n, k = deg + 1, len(cons)
    M = np.zeros((n + k, n + k))
    rhs = np.zeros(n + k)
    M[:n, :n] = A.T @ A
    M[:n, n:] = C.T
    M[n:, :n] = C
    rhs[:n] = A.T @ y
    rhs[n:] = d
    return np.linalg.lstsq(M, rhs, rcond=None)[0][:n]


class OpenPatches:
    """
    Разомкнутая версия PatchApproximator.

    Патчи — цепочка вдоль длины: центры c_j = (j + 0.5 + shift)/N, локальная
    координата x = (u - c)/half_train в каноне [-1, 1], веса — тот же smoothstep
    (в своём секторе 1, в зоне перекрытия плавно к 0), степень — то же правило
    «локтя» по остаткам на обучающем окне. Отличий от замкнутой версии ровно
    два: нет заворота через 360° и есть РЕЖИМ ПРИВЯЗКИ КОНЦОВ (boundary).

    u — нормированная длина вдоль МОДЕЛИРУЕМОЙ части (0..1). Скан может быть
    длиннее модели (margin > 0): тогда окна обучения крайних патчей целиком
    лежат на данных и boundary bias у концов не возникает.
    """

    def __init__(self, n_patches=N_PATCHES, deg_min=DEG_MIN, deg_max=DEG_MAX,
                 deg_elbow_tol=DEG_ELBOW_TOL, overlap_train=OVERLAP_TRAIN,
                 overlap_use=OVERLAP_USE, boundary="free", boundary_ext=1.0,
                 deg_bonus=0, margin=0.0, shift=0.0):
        if deg_min % 2:
            deg_min += 1
        if deg_max % 2:
            deg_max += 1
        if boundary not in ("free", "mirror_even", "mirror_odd",
                            "clamp_v", "clamp_vd"):
            raise ValueError(f"boundary: неизвестный режим привязки {boundary!r}")
        self.n_patches = int(n_patches)
        self.deg_min, self.deg_max = int(deg_min), int(deg_max)
        self.deg_elbow_tol = float(deg_elbow_tol)
        self.overlap_train = float(overlap_train)
        self.overlap_use = float(overlap_use)
        self.boundary = boundary
        self.boundary_ext = float(boundary_ext)
        self.deg_bonus = int(deg_bonus)
        self.margin = float(margin)
        self.shift = float(shift)
        self.patches_ = []
        self.degrees_ = []

    def _edge_datums(self, u, r):
        """
        Что известно про край: значение и наклон (датум).

        Датум берётся не «средним по полосе», а квадратичным фитом по крайней
        полосе EDGE_BAND длины с отбраковкой выбросов (median ± 3·MAD), и
        значение берётся В САМОЙ КРАЙНЕЙ ТОЧКЕ (u = 0 или u = 1). Это честная
        модель «инженерного датума»: он всё равно измерен по шумным данным (и
        может попасть на стенку ямы у реза), поэтому точность края после
        привязки равна точности датума — см. О5в.
        """
        band = max(5, int(round(EDGE_BAND * len(u))))
        u = np.asarray(u, dtype=float)
        r = np.asarray(r, dtype=float)

        def _nearest(target: float) -> np.ndarray:
            # band ближайших к краю домена точек: при margin>0 полоса сама захватывает
            # данные за краем, при margin=0 совпадает с полосой внутрь домена
            return np.argsort(np.abs(u - target), kind="stable")[:band]

        lo_idx, hi_idx = _nearest(0.0), _nearest(1.0)
        lo_r, lo_s = _robust_edge_fit(u[lo_idx], r[lo_idx], 0.0)
        hi_r, hi_s = _robust_edge_fit(u[hi_idx], r[hi_idx], 1.0)
        return {"r_lo": lo_r, "slope_lo": lo_s, "r_hi": hi_r, "slope_hi": hi_s}

    def _mirror(self, u, r):
        """Виртуальные точки за краем домена (чётное/нечётное продолжение)."""
        ext = self.boundary_ext * self.half_train_
        odd = self.boundary == "mirror_odd"
        lo, hi = u < ext, u > 1.0 - ext
        r0, r1 = self.edge_["r_lo"], self.edge_["r_hi"]
        u_lo, r_lo = -u[lo][::-1], (2.0 * r0 - r[lo][::-1]) if odd else r[lo][::-1]
        u_hi, r_hi = 2.0 - u[hi], (2.0 * r1 - r[hi]) if odd else r[hi]
        u_ext = np.concatenate([u_lo, u, u_hi])
        r_ext = np.concatenate([r_lo, r, r_hi])
        order = np.argsort(u_ext)
        return u_ext[order], r_ext[order]

    def _constraints(self, c):
        """Связи крайнего патча: значение (и наклон) на границе домена."""
        if self.boundary not in ("clamp_v", "clamp_vd"):
            return []
        cons = []
        for x_edge, r_edge, slope in (
                ((0.0 - c) / self.half_train_, self.edge_["r_lo"],
                 self.edge_["slope_lo"]),
                ((1.0 - c) / self.half_train_, self.edge_["r_hi"],
                 self.edge_["slope_hi"])):
            if abs(x_edge) > 1.0:
                continue                        # патч до этого края не достаёт
            cons.append((0, x_edge, r_edge))
            if self.boundary == "clamp_vd":
                cons.append((1, x_edge, slope * self.half_train_))
        return cons

    def _estimate_degree(self, u, r, c):
        """Правило «локтя» по остаткам на РЕАЛЬНЫХ точках обучающего окна."""
        x = (u - c) / self.half_train_
        if len(x) < 5:
            return self.deg_min
        results = []
        for deg in range(self.deg_min, self.deg_max + 1, 2):
            coefs = np.polyfit(x, r, deg)
            rmse = float(np.sqrt(np.mean((np.polyval(coefs, x) - r) ** 2)))
            results.append((deg, rmse))
        limit = min(e for _, e in results) * (1.0 + self.deg_elbow_tol)
        return int(next(d for d, e in results if e <= limit))

    # --- обучение -----------------------------------------------------------
    def fit(self, t, r):
        t = np.asarray(t, dtype=float)
        r = np.asarray(r, dtype=float)
        order = np.argsort(t)
        t, r = t[order], r[order]

        lo, hi = self.margin, 1.0 - self.margin
        self.span_ = hi - lo
        self.half_sector_ = 0.5 / self.n_patches
        self.half_train_ = self.half_sector_ * (1.0 + self.overlap_train)
        self.half_use_ = self.half_sector_ * (1.0 + self.overlap_use)
        u = (t - lo) / self.span_
        # в режиме margin скан длиннее домена: u < 0 и u > 1 — это данные за
        # краем модели, они нужны как обучающий запас
        keep = (u >= -0.05) & (u <= 1.05)
        u, r = u[keep], r[keep]
        self.centers_ = np.array([(j + 0.5 + self.shift) / self.n_patches
                                  for j in range(self.n_patches)])
        self.edge_ = self._edge_datums(u, r)

        if self.boundary.startswith("mirror"):
            u_ext, r_ext = self._mirror(u, r)
        else:
            u_ext, r_ext = u, r

        self.patches_, self.degrees_ = [], []
        for j, c in enumerate(self.centers_):
            m_real = np.abs(u - c) <= self.half_train_
            deg = self._estimate_degree(u[m_real], r[m_real], c)
            if self.deg_bonus and j in (0, self.n_patches - 1):
                deg = min(deg + 2 * self.deg_bonus, self.deg_max + 2)
            m_all = np.abs(u_ext - c) <= self.half_train_
            x = (u_ext[m_all] - c) / self.half_train_
            cons = self._constraints(c)
            coefs = polyfit_constrained(x, r_ext[m_all], deg, cons)
            self.patches_.append({"center": float(c), "degree": int(deg),
                                  "coefs": coefs, "n_points": int(m_all.sum()),
                                  "n_real": int(m_real.sum()),
                                  "constrained": bool(cons)})
            self.degrees_.append(int(deg))
        self.coef_budget_ = int(sum(p["degree"] + 1 for p in self.patches_))
        return self

    # --- расчёт -------------------------------------------------------------
    def eval(self, u):
        """Значение модели в точках u (нормированная длина домена, 0..1)."""
        u = np.asarray(u, dtype=float)
        vals = np.zeros((len(u), self.n_patches))
        wts = np.zeros_like(vals)
        for j, p in enumerate(self.patches_):
            d = np.abs(u - p["center"])
            w = np.zeros(len(u))
            w[d <= self.half_sector_] = 1.0
            blend = (d > self.half_sector_) & (d <= self.half_use_)
            if blend.any():
                ramp = 1.0 - (d[blend] - self.half_sector_) / \
                    (self.half_use_ - self.half_sector_)
                w[blend] = _smoothstep(ramp)
            vals[:, j] = np.polyval(p["coefs"], (u - p["center"]) / self.half_train_)
            wts[:, j] = w
        sw = wts.sum(axis=1)
        out = np.full(len(u), np.nan)
        ok = sw > 1e-12                        # конец, до которого сетка не дошла
        out[ok] = (vals[ok] * wts[ok]).sum(axis=1) / sw[ok]
        return out

    def predict(self, t):
        """Значение модели в точках t (та же нормировка длины, что у fit)."""
        t = np.asarray(t, dtype=float)
        return self.eval((t - self.margin) / self.span_)


# --- базовые линии (то, «как это делают без патчей») -----------------------

def baseline_global(t, r, t_grid, deg):
    """Один глобальный полином на всю разомкнутую длину."""
    return np.polyval(np.polyfit(t, r, deg), t_grid)


def baseline_lpr(t, r, t_grid, deg, window):
    """
    LPR: локальная полиномиальная регрессия фиксированной степени с фиксированным
    окном (uniform-веса, без блендинга) — «то же самое, но без павловости».
    """
    t = np.asarray(t, dtype=float)
    r = np.asarray(r, dtype=float)
    out = np.empty(len(t_grid))
    for i, q in enumerate(np.asarray(t_grid, dtype=float)):
        m = (t >= q - window) & (t <= q + window)
        if m.sum() < deg + 1:
            out[i] = np.nan
            continue
        out[i] = np.polyval(np.polyfit(t[m] - q, r[m], deg), 0.0)
    return out


def baseline_spline(t, r, t_grid, s=None):
    """Сглаживающий кубический сплайн (scipy) — глобально, без окна."""
    from scipy.interpolate import UnivariateSpline
    spl = UnivariateSpline(np.asarray(t, float), np.asarray(r, float), k=3, s=s)
    return spl(np.asarray(t_grid, float))


def baseline_fourier(t, r, t_grid, n_harm=24):
    """
    Фурье по разомкнутому участку: модель ЗАМКНУТА на длину участка, то есть
    r(0) = r(1) по построению. Ровно та ошибка, которую даёт «забытая»
    окружность: на резах получается сшивка, которой у детали нет.
    """
    t = np.asarray(t, dtype=float)
    r = np.asarray(r, dtype=float)
    cols = [np.ones_like(t)]
    for k in range(1, n_harm + 1):
        cols += [np.cos(2 * np.pi * k * t), np.sin(2 * np.pi * k * t)]
    A = np.column_stack(cols)
    coefs = np.linalg.lstsq(A, r, rcond=None)[0]
    tg = np.asarray(t_grid, dtype=float)
    cols_g = [np.ones_like(tg)]
    for k in range(1, n_harm + 1):
        cols_g += [np.cos(2 * np.pi * k * tg), np.sin(2 * np.pi * k * tg)]
    return np.column_stack(cols_g) @ coefs


def closed_reference(data, sid):
    """Обученная ЗАМКНУТАЯ модель сечения (для ориентира «если бы кольцо было»)."""
    ap = PatchApproximator(n_patches=N_PATCHES, deg_min=DEG_MIN, deg_max=DEG_MAX,
                           overlap_train=15.0, overlap_use=5.0, phase_deg=24.75,
                           deg_elbow_tol=DEG_ELBOW_TOL)
    ap.fit(data[sid]["angles_clean"], data[sid]["radii_clean"])
    return ap


# --- варианты привязки концов ----------------------------------------------

VARIANTS = {
    "free":           dict(boundary="free"),
    "margin 3%":      dict(boundary="free", margin=0.03),
    "margin 6%":      dict(boundary="free", margin=0.06),
    "mirror_even":    dict(boundary="mirror_even"),
    "mirror_odd":     dict(boundary="mirror_odd"),
    "clamp_v":        dict(boundary="clamp_v"),
    "clamp_vd":       dict(boundary="clamp_vd"),
    "deg+2 на краях": dict(boundary="free", deg_bonus=1),
    "clamp_vd+deg+2": dict(boundary="clamp_vd", deg_bonus=1),
}


def metrics_for(case, ap):
    """
    Метрики модели против истины на её собственном домене.

    Для режима margin домен — внутренняя часть длины, поэтому t нормируется
    внутри домена (иначе «крайние 5%» убежали бы вместе с доменом).
    """
    t = case["grid_t"]
    model = ap.predict(t)
    lo, hi = ap.margin, 1.0 - ap.margin
    dom = (t >= lo - 1e-9) & (t <= hi + 1e-9) & np.isfinite(model)
    t_rel = (t[dom] - lo) / (hi - lo)
    st = error_stats(t_rel, model[dom], case["truth"][dom])
    st["domain_frac"] = float(hi - lo)
    st["coef_budget"] = int(ap.coef_budget_)
    st["degrees"] = list(ap.degrees_)
    return st, model


def aggregate(rows):
    """Средние метрики по сечениям (для сводных таблиц)."""
    keys = ("rmse", "max", "rmse_end", "max_end", "drift_lo", "drift_hi")
    out = {k: float(np.mean([r[k] for r in rows])) for k in keys}
    out["domain_frac"] = float(np.mean([r.get("domain_frac", 1.0) for r in rows]))
    out["coef_budget"] = float(np.mean([r.get("coef_budget", np.nan) for r in rows]))
    return out


def print_table(title, headers, rows):
    """Печать таблицы: числовые столбцы — по правому краю, текстовые — по левому."""
    print(f"\n{title}")
    if not rows:
        print("  (нет строк)")
        return
    cells = [[("" if c is None else str(c)) for c in row] for row in rows]

    def is_num(col):
        vals = [r[col] for r in cells if r[col] not in ("", "-")]
        if not vals:
            return False
        try:
            for v in vals:
                float(v)
            return True
        except ValueError:
            return False

    num = [is_num(i) for i in range(len(headers))]
    w = [max(len(headers[i]), *(len(r[i]) for r in cells))
         for i in range(len(headers))]
    head = "  ".join((h.rjust(w[i]) if num[i] else h.ljust(w[i]))
                     for i, h in enumerate(headers))
    print("  " + head)
    print("  " + "-" * len(head))
    for r in cells:
        print("  " + "  ".join((c.rjust(w[i]) if num[i] else c.ljust(w[i]))
                               for i, c in enumerate(r)))


def fmt_agg(agg, label):
    """Строка сводной таблицы (средние по сечениям)."""
    coef = agg.get("coef_budget")
    coef_s = "-" if coef is None or np.isnan(coef) else "%d" % coef
    return [label, "%.4f" % agg["rmse"], "%.4f" % agg["max"],
            "%.4f" % agg["rmse_end"], "%.4f" % agg["max_end"],
            "%.4f" % agg["drift_lo"], "%.4f" % agg["drift_hi"],
            "%.2f" % agg["domain_frac"], coef_s]


HEAD_END = ["вариант", "RMSE", "max", "RMSE хвост", "max хвост",
            "край L", "край R", "домен", "коэф."]


# --- эксперименты -----------------------------------------------------------

def cases_for(data, span_name):
    """Открытые участки по всем секциям для выбранного спана."""
    a0, a1 = SPANS[span_name]
    return {sid: prepare(data[sid], a0, a1) for sid in SECTIONS}


def closed_stats(data, cases):
    """Метрики замкнутой модели на том же участке (ориентир «кольцо было бы»)."""
    sts = []
    for sid, case in cases.items():
        ap = closed_reference(data, sid)
        st = error_stats(case["grid_t"], ap.eval(case["grid_a"]), case["truth"])
        st["domain_frac"] = 1.0
        st["coef_budget"] = int(sum(d + 1 for d in ap.get_degrees()))
        sts.append(st)
    return sts


def eval_variants(cases, variants):
    """Прогон набора вариантов привязки по всем сечениям: label -> [метрики]."""
    out = {}
    for label, kw in variants.items():
        sts = []
        for case in cases.values():
            ap = OpenPatches(**kw).fit(case["t"], case["r"])
            st, _ = metrics_for(case, ap)
            sts.append(st)
        out[label] = sts
    return out


def report_end_variants(title, data, cases, variants=VARIANTS):
    """О1-О2: сравнение вариантов привязки концов на одном открытом участке."""
    res = eval_variants(cases, variants)
    rows = [fmt_agg(aggregate(closed_stats(data, cases)), "кольцо (замкнутая)")]
    rows += [fmt_agg(aggregate(res[label]), label) for label in variants]
    print_table(title, HEAD_END, rows)
    print("  «кольцо (замкнутая)» — ориентир: та же модель на полном круге, но её окна "
          "заданы в градусах круга\n  (half_train = 40.7°), а у разомкнутой формы окна "
          "относительные (0.113 длины = 27.1° на участке 240°),\n  поэтому сравнивать "
          "строки надо по порядку величины, а не до третьего знака.")
    return res


def crack_deficit(case, model, half_deg=3.0):
    """
    Недобор глубины ближайшего к краю дефекта, мм: min(модель) - min(истина)
    в окне ±half_deg вокруг дна дефекта (отрицательное = яма недокопана).
    """
    truth = case["truth"]
    k = int(np.argmin(truth))
    a_k = case["grid_a"][k]
    w = np.abs(case["grid_a"] - a_k) <= half_deg
    seg_m, seg_t = np.asarray(model)[w], truth[w]
    ok = np.isfinite(seg_m)
    if not np.any(ok):
        # домен модели (margin) не доезжает до дна дефекта: сравнивать нечего
        return float("nan"), float(a_k)
    return float(np.min(seg_m[ok]) - np.min(seg_t[ok])), float(a_k)


def fmt_deficit(defs):
    """Среднее по сечениям + пометка, если часть сечений вне домена модели."""
    arr = np.asarray(defs, dtype=float)
    ok = np.isfinite(arr)
    if not np.any(ok):
        return "вне домена"
    s = "%+.4f" % float(np.mean(arr[ok]))
    return s if bool(ok.all()) else s + " (%d/%d сеч.)" % (int(ok.sum()), arr.size)


def report_feature_at_edge(data, span_name):
    """
    О3: дефект рядом с РЕЗОМ (участок B). Показывает, чем платят варианты: либо
    модель «убегает» у края, либо подрезает яму, потому что крайний патч тянут
    связями/зеркалом.
    """
    cases = cases_for(data, span_name)
    res = eval_variants(cases, VARIANTS)
    rows = []
    for label in VARIANTS:
        defs = []
        for case in cases.values():
            ap = OpenPatches(**VARIANTS[label]).fit(case["t"], case["r"])
            _, model = metrics_for(case, ap)
            d, _ = crack_deficit(case, model)
            defs.append(d)
        rows.append(fmt_agg(aggregate(res[label]), label) + [fmt_deficit(defs)])
    head = HEAD_END + ["яма у края"]
    # у замкнутой модели дефицит тоже полезен как точка отсчёта
    closed_defs = []
    for sid, case in cases.items():
        ap = closed_reference(data, sid)
        d, _ = crack_deficit(case, ap.eval(case["grid_a"]))
        closed_defs.append(d)
    rows.insert(0, fmt_agg(aggregate(closed_stats(data, cases)), "кольцо (замкнутая)")
                + [fmt_deficit(closed_defs)])
    print_table(f"О3. Дефект около реза ({span_name})", head, rows)
    print("  «яма у края» = min(модель)-min(истина) в ±3° вокруг дна ближайшего к резу дефекта, мм:")
    print("  минус = яма НЕДОКОПАНА, плюс = модель ушла ниже истины. Считается только по точкам")
    print("  внутри домена модели; пометка «(k/n сеч.)» — если часть сечений дефект не покрывает.")
    bottoms = ["%d->%.2f°" % (sid, crack_deficit(case, case["truth"])[1])
               for sid, case in cases.items()]
    print("  где дно ближайшего к левому резу дефекта:", ", ".join(bottoms))
    return res


# --- О4: «павловость» против базовых линий ---------------------------------

def baseline_rows(cases):
    """Базовые линии на том же открытом участке (по истине генератора)."""
    rows = []
    for deg in (8, 14):
        sts = []
        for case in cases.values():
            model = baseline_global(case["t"], case["r"], case["grid_t"], deg)
            sts.append(error_stats(case["grid_t"], model, case["truth"]))
        rows.append((f"глобальный полином {deg}", sts))
    for deg in (4, 8):
        sts = []
        for case in cases.values():
            window = 0.5 / N_PATCHES * (1.0 + OVERLAP_TRAIN)
            model = baseline_lpr(case["t"], case["r"], case["grid_t"], deg, window)
            ok = np.isfinite(model)
            sts.append(error_stats(case["grid_t"][ok], model[ok], case["truth"][ok]))
        rows.append((f"LPR deg={deg} (окно как у патча)", sts))
    # сплайн: сначала «честный» s = n·σ², потом лучший по сетке s (щедро к baseline)
    sts_def, sts_best = [], []
    for case in cases.values():
        n = len(case["r"])
        d = np.abs(np.diff(case["r"]))
        sigma = float(np.median(d) * 1.4826 / np.sqrt(2.0))
        sts_def.append(error_stats(
            case["grid_t"],
            baseline_spline(case["t"], case["r"], case["grid_t"], s=n * sigma ** 2),
            case["truth"]))
        best = None
        for s in (n * sigma ** 2) * np.logspace(-1.5, 1.5, 13):
            model = baseline_spline(case["t"], case["r"], case["grid_t"], s=float(s))
            st = error_stats(case["grid_t"], model, case["truth"])
            if best is None or st["rmse"] < best["rmse"]:
                best = st
        sts_best.append(best)
    rows.append(("сглаж. сплайн s=n·σ²", sts_def))
    rows.append(("сглаж. сплайн (лучший s)", sts_best))
    sts = []
    for case in cases.values():
        model = baseline_fourier(case["t"], case["r"], case["grid_t"], n_harm=24)
        sts.append(error_stats(case["grid_t"], model, case["truth"]))
    rows.append(("Фурье 24 гармоники (замкнут на длину участка)", sts))
    return rows


def report_pavlovness(data, span_name, base=None):
    """
    О4: что из «павловости» реально работает на разомкнутой форме, а что даёт то
    же самое без патчей. База — привязка clamp_vd при margin=0: домен модели
    совпадает с участком данных, поэтому сравнение с базовыми линиями честное
    (в О5б лучшей оказывается пара free + margin 4-6%, но там домен уже урезан).
    """
    base = dict(base or {"boundary": "clamp_vd"})
    cases = cases_for(data, span_name)
    print(f"\n=== О4. «Павловость» на разомкнутой форме ({span_name}), "
          f"привязка {base.get('boundary')} ===")
    res = eval_variants(cases, {f"N={n}": dict(base, n_patches=n)
                                for n in (4, 6, 8, 10, 12)})
    rows = [fmt_agg(aggregate(res["N=%d" % n]), "N=%d патчей" % n)
            for n in (4, 6, 8, 10, 12)]
    print_table("О4а. Число патчей (степень и окна адаптивные)", HEAD_END, rows)

    res = eval_variants(cases, {f"d={d}": dict(base, deg_min=d, deg_max=d)
                                for d in (4, 8, 14)})
    rows = [fmt_agg(aggregate(res["d=%d" % d]), "фикс. степень %d" % d)
            for d in (4, 8, 14)]
    res_ad = eval_variants(cases, {"ad": dict(base)})
    rows.append(fmt_agg(aggregate(res_ad["ad"]), "адаптивная степень (локоть)"))
    print_table("О4б. Степень: фиксированная против адаптивной", HEAD_END, rows)

    res = eval_variants(cases, {f"o={ov}": dict(base, overlap_train=ov)
                                for ov in (0.0, 0.3, 0.583, 1.0)})
    rows = [fmt_agg(aggregate(res["o=%s" % ov]), "overlap_train %.3f" % ov)
            for ov in (0.0, 0.3, 0.583, 1.0)]
    print_table("О4в. Обучать шире, чем применять (доля полусектора)", HEAD_END, rows)

    cases_raw = {sid: prepare(data[sid], *SPANS[span_name], cleaned=False)
                 for sid in SECTIONS}
    res_raw = eval_variants(cases_raw, {"raw": dict(base)})
    rows = [fmt_agg(aggregate(res_ad["ad"]), "выбросы вычищены (iqr)"),
            fmt_agg(aggregate(res_raw["raw"]), "без очистки")]
    print_table("О4г. Очистка выбросов до обучения", HEAD_END, rows)

    rows = [fmt_agg(aggregate(sts), label) for label, sts in baseline_rows(cases)]
    rows.insert(0, fmt_agg(aggregate(res_ad["ad"]), "патчи + clamp_vd"))
    print_table("О4д. Базовые линии на том же участке", HEAD_END, rows)
    return res_ad


# --- О5: привязка параметра (gauge) ----------------------------------------

def report_gauge(data, span_name):
    """
    О5: у кольца роль gauge играл phase_deg — сетку патчей поворачивали, чтобы
    швы ушли от дефектов. У разомкнутой формы «поворачивать» нечего: сетка
    сдвигается ВДОЛЬ длины, и сдвиг сразу виден на краях (первый патч либо не
    доезжает до реза, либо уходит за него и тянет полином наружу).
    """
    cases = cases_for(data, span_name)
    print(f"\n=== О5. Куда привязать начало параметра ({span_name}) ===")
    rows = []
    for label, kw in (("free", dict(boundary="free")),
                      ("clamp_vd", dict(boundary="clamp_vd"))):
        for shift in (-0.4, -0.2, 0.0, 0.2, 0.4):
            sts, cov_lo, cov_hi = [], [], []
            for case in cases.values():
                ap = OpenPatches(shift=shift, **kw).fit(case["t"], case["r"])
                st, model = metrics_for(case, ap)
                ok = np.isfinite(model)
                inside = (case["grid_t"] >= ap.margin) & (case["grid_t"] <= 1 - ap.margin)
                cov = inside & ok
                sts.append(st)
                cov_lo.append(float(case["grid_t"][cov][0]))
                cov_hi.append(float(case["grid_t"][cov][-1]))
            agg = aggregate(sts)
            rows.append([label, "%+.1f" % shift, "%.3f" % np.mean(cov_lo),
                         "%.3f" % np.mean(cov_hi), "%.4f" % agg["rmse"],
                         "%.4f" % agg["max_end"], "%.4f" % agg["drift_lo"],
                         "%.4f" % agg["drift_hi"]])
    print_table("О5а. Сдвиг сетки вдоль длины (в долях сектора): покрытие и ошибки",
                ["привязка", "сдвиг", "покрыт с", "покрыт до", "RMSE",
                 "max хвост", "край L", "край R"], rows)

    rows = []
    for m in (0.0, 0.01, 0.02, 0.04, 0.06):
        for label, kw in (("free", dict(boundary="free")),
                          ("clamp_vd", dict(boundary="clamp_vd"))):
            sts = []
            for case in cases.values():
                ap = OpenPatches(margin=m, **kw).fit(case["t"], case["r"])
                st, _ = metrics_for(case, ap)
                sts.append(st)
            agg = aggregate(sts)
            rows.append([label, "%.0f%%" % (100 * m), "%.2f" % agg["domain_frac"],
                         "%.4f" % agg["rmse"], "%.4f" % agg["max_end"],
                         "%.4f" % agg["drift_lo"], "%.4f" % agg["drift_hi"]])
    print_table("О5б. «Скан шире модели»: чем платим (домен) и что получаем",
                ["привязка", "margin", "домен", "RMSE", "max хвост",
                 "край L", "край R"], rows)


def report_datums(data, span_name):
    """
    О5в: сколько стоит САМ ДАТУМ. Привязка к краю не может быть точнее датума, а
    датум измерен по шумным данным и может попасть на стенку ямы у реза.
    """
    cases = cases_for(data, span_name)
    noise = []
    for sid in cases:
        d = data[sid]["radii_clean"] - np.interp(data[sid]["angles_clean"],
                                                 data[sid]["angles"], data[sid]["ideal"])
        noise.append(np.abs(d))
    noise = np.concatenate(noise)
    rows, dlo, dhi = [], [], []
    for sid, case in cases.items():
        ap = OpenPatches(boundary="clamp_vd").fit(case["t"], case["r"])
        e_lo = ap.edge_["r_lo"] - case["truth"][0]
        e_hi = ap.edge_["r_hi"] - case["truth"][-1]
        dlo.append(abs(e_lo))
        dhi.append(abs(e_hi))
        rows.append([f"сеч {sid}", "%.4f" % ap.edge_["r_lo"],
                     "%.4f" % case["truth"][0], "%+.4f" % e_lo,
                     "%.4f" % ap.edge_["r_hi"], "%.4f" % case["truth"][-1],
                     "%+.4f" % e_hi])
    rows.append(["среднее |Δ|", "-", "-", "%.4f" % float(np.mean(dlo)),
                 "-", "-", "%.4f" % float(np.mean(dhi))])
    print_table(f"О5в. Чему равен датум края и насколько он врёт ({span_name})",
                ["сечение", "датум L", "истина L", "Δ L",
                 "датум R", "истина R", "Δ R"], rows)
    print("  шум измерений в этих данных: |Δr| p50 = %.3f мм, p90 = %.3f мм. "
          "Привязка точнее датума быть не может,\n  а сам датум — функция полосы "
          "EDGE_BAND = %.0f%% длины: шире полоса -> меньше шума, но сильнее "
          "сглаживается форма у реза."
          % (float(np.percentile(noise, 50)), float(np.percentile(noise, 90)),
             100 * EDGE_BAND))


# --- рисунок ----------------------------------------------------------------

def plot_ends(data, span_name="B 240° трещина у края", sid=0,
              out="open_shapes_ends.png"):
    """
    Три панели: что видно глазом у реза; где живёт ошибка по длине; сколько
    стоит каждый вариант привязки (max хвост).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    case = prepare(data[sid], *SPANS[span_name])
    a0, a1 = SPANS[span_name]
    zoom = case["grid_a"] <= a0 + 0.25 * (a1 - a0)
    variants = {"free": dict(boundary="free"),
                "clamp_vd": dict(boundary="clamp_vd"),
                "mirror_odd": dict(boundary="mirror_odd")}
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))

    ax = axes[0]
    ax.plot(case["grid_a"], case["truth"], color="0.25", lw=2.4,
            label="истина генератора")
    for label, kw in variants.items():
        ap = OpenPatches(**kw).fit(case["t"], case["r"])
        model = ap.predict(case["grid_t"])
        ax.plot(case["grid_a"][zoom], model[zoom], lw=1.4, label=label)
    ax.axvline(a0, color="crimson", ls="--", lw=1.0, label="рез (край скана)")
    ax.set_xlabel("угол скана, °")
    ax.set_ylabel("r, мм")
    ax.set_title(f"у левого реза, сечение {sid}\n({span_name})")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    ax = axes[1]
    for label, kw in variants.items():
        ap = OpenPatches(**kw).fit(case["t"], case["r"])
        model = ap.predict(case["grid_t"])
        ax.plot(case["grid_t"], np.abs(model - case["truth"]), lw=1.3, label=label)
    ax.axvspan(0.0, 0.05, color="crimson", alpha=0.12)
    ax.axvspan(0.95, 1.0, color="crimson", alpha=0.12)
    ax.set_xlabel("нормированная длина t")
    ax.set_ylabel("|Δr|, мм")
    ax.set_title("где живёт ошибка по длине\n(красное — крайние 5% длины)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    ax = axes[2]
    cases = cases_for(data, span_name)
    labels, vals = [], []
    for label, kw in VARIANTS.items():
        sts = []
        for c in cases.values():
            ap = OpenPatches(**kw).fit(c["t"], c["r"])
            st, _ = metrics_for(c, ap)
            sts.append(st)
        labels.append(label)
        vals.append(aggregate(sts)["max_end"])
    y = np.arange(len(labels))
    ax.barh(y, vals, color=["#c44" if v > 0.05 else "#4a7" for v in vals])
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0.05, color="0.3", ls=":", lw=1.0, label="0.05 мм")
    ax.set_xlabel("max |Δr| в крайних 5% длины, мм")
    ax.set_title("цена варианта привязки\n(среднее по 4 сечениям)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25, axis="x")

    fig.tight_layout()
    path = resolve_plot(out)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    print(f"\nРисунок: {path}")


# --- main -------------------------------------------------------------------

def main():
    data = load_data()
    print("РАЗОМКНУТЫЕ ФОРМЫ на патчах Павлова")
    print(f"сечения: {SECTIONS}; участки: " +
          ", ".join(f"{k} [{v[0]:g}°, {v[1]:g}°]" for k, v in SPANS.items()))
    print(f"модель: N={N_PATCHES}, степень {DEG_MIN}..{DEG_MAX} по «локтю» "
          f"(tol={DEG_ELBOW_TOL}), overlap_train={OVERLAP_TRAIN} "
          f"полусектора, overlap_use={OVERLAP_USE}")
    for span_name in SPANS:
        cases = cases_for(data, span_name)
        report_end_variants(f"\n=== О1-О2. Привязка концов: {span_name} ===",
                            data, cases)
    report_feature_at_edge(data, "B 240° трещина у края")
    report_pavlovness(data, "A 240° трещина внутри")
    report_gauge(data, "A 240° трещина внутри")
    report_datums(data, "B 240° трещина у края")
    plot_ends(data)


if __name__ == "__main__":
    main()
