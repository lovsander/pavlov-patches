! PAPPA Fortran port -- сигнальные помощники: кольцевые фильтры и робастная
! статистика. Точные соответствия Octave-порту (octave/src/signal_*.m).
module pappa_signal
  use pappa_kinds, only: dp, ip
  implicit none
  private
  public :: sig_round_even, sig_odd_window, sig_sort_asc, sig_median
  public :: sig_percentile, sig_iqr2, sig_robust_sigma, sig_angular_step
  public :: sig_window_points, sig_median_filter, sig_smooth_wrap
  public :: sig_circ_dist, sig_circ_local, sig_smoothstep

contains

  ! Round half to even (IEC 60559) -- как Python round() и C rint().
  !
  ! ЛОВУШКА: nint() в Fortran округляет половину ОТ НУЛЯ (nint(2.5) == 3,
  ! проверено), поэтому для ширин окон взят ручной ties-to-even.
  ! NaN/Inf возвращаются как есть (abs(x) < huge(x) для них ложно).
  elemental function sig_round_even(x) result(y)
    real(dp), intent(in) :: x
    real(dp) :: y, f, d
    if (abs(x) < huge(x)) then
      f = floor(x)
      d = x - f
      if (d > 0.5_dp) then
        y = f + 1.0_dp
      else if (d < 0.5_dp) then
        y = f
      else if (modulo(f, 2.0_dp) == 0.0_dp) then
        y = f              ! ничья: чётный сосед снизу
      else
        y = f + 1.0_dp     ! ничья: чётный сосед сверху
      end if
    else
      y = x
    end if
  end function sig_round_even

  ! Ширина окна в точках: нечётная, не меньше 3 и не шире массива.
  pure function sig_odd_window(window, n) result(w)
    integer(ip), intent(in) :: window, n
    integer(ip) :: w
    w = window
    if (modulo(w, 2_ip) == 0) w = w + 1
    if (w < 3) w = 3
    if (w > n) then
      if (modulo(n, 2_ip) == 1) then
        w = n
      else
        w = n - 1
      end if
    end if
  end function sig_odd_window

  ! Сортировка по возрастанию (Шелл): в Fortran встроенной нет.
  ! Алгоритм на результат не влияет -- медиане нужен порядок значений,
  ! а не устойчивость.
  subroutine sig_sort_asc(a)
    real(dp), intent(inout) :: a(:)
    integer(ip) :: n, gap, i, j
    real(dp) :: t
    n = int(size(a), ip)
    gap = n / 2
    do while (gap > 0)
      do i = gap + 1, n
        t = a(i)
        j = i
        do while (j > gap)
          if (a(j - gap) <= t) exit
          a(j) = a(j - gap)
          j = j - gap
        end do
        a(j) = t
      end do
      gap = gap / 2
    end do
  end subroutine sig_sort_asc

  ! Медиана УЖЕ отсортированного массива: для чётного n -- среднее двух
  ! центральных значений (как numpy.median).
  pure function median_sorted(v) result(m)
    real(dp), intent(in) :: v(:)
    real(dp) :: m
    integer(ip) :: n
    n = int(size(v), ip)
    if (n == 0) then
      m = 0.0_dp
    else if (modulo(n, 2_ip) == 1) then
      m = v((n + 1) / 2)
    else
      m = 0.5_dp * (v(n / 2) + v(n / 2 + 1))
    end if
  end function median_sorted

  ! Медиана как numpy.median: сортируем копию, вход не портим.
  function sig_median(values) result(m)
    real(dp), intent(in) :: values(:)
    real(dp) :: m
    real(dp), allocatable :: v(:)
    ! Явная аллокация: gfortran предупреждает (-Wuninitialized) на присваивание
    ! массива неаллоцированной локальной переменной.
    allocate(v(size(values)))
    v = values
    call sig_sort_asc(v)
    m = median_sorted(v)
  end function sig_median

  ! Перцентиль с линейной интерполяцией (numpy.percentile / тип 7 у R).
  ! Позиция 0-based, как в numpy: pos = q/100 * (n-1).
  function sig_percentile(values, q) result(p)
    real(dp), intent(in) :: values(:), q
    real(dp) :: p, pos, fr
    real(dp), allocatable :: v(:)
    integer(ip) :: n, lo, hi
    n = int(size(values), ip)
    if (n == 0) then
      p = 0.0_dp
      return
    end if
    v = values
    call sig_sort_asc(v)
    pos = (q / 100.0_dp) * real(n - 1, dp)
    lo = int(floor(pos), ip)
    fr = pos - real(lo, dp)
    hi = min(lo + 1, n - 1)
    p = v(lo + 1) + fr * (v(hi + 1) - v(lo + 1))
  end function sig_percentile

  ! Межквартильный размах (P75 - P25).
  function sig_iqr2(values) result(v)
    real(dp), intent(in) :: values(:)
    real(dp) :: v
    if (size(values) == 0) then
      v = 0.0_dp
    else
      v = sig_percentile(values, 75.0_dp) - sig_percentile(values, 25.0_dp)
    end if
  end function sig_iqr2

  ! Робастная оценка масштаба: 1.4826 * MAD.
  function sig_robust_sigma(values) result(s)
    real(dp), intent(in) :: values(:)
    real(dp) :: s, med
    if (size(values) == 0) then
      s = 0.0_dp
    else
      med = sig_median(values)
      s = 1.4826_dp * sig_median(abs(values - med))
    end if
  end function sig_robust_sigma

  ! Медианный шаг сетки по углам (медиана ПОЛОЖИТЕЛЬНЫХ разностей в том
  ! порядке, в каком они идут в массиве, иначе 1).
  function sig_angular_step(angles) result(step)
    real(dp), intent(in) :: angles(:)
    real(dp) :: step
    real(dp), allocatable :: d(:)
    integer(ip) :: n, i, k
    n = int(size(angles), ip)
    if (n < 2) then
      step = 1.0_dp
      return
    end if
    allocate(d(n - 1))
    k = 0
    do i = 1, n - 1
      if (angles(i + 1) - angles(i) > 0.0_dp) then
        k = k + 1
        d(k) = angles(i + 1) - angles(i)
      end if
    end do
    if (k == 0) then
      step = 1.0_dp
    else
      step = sig_median(d(1:k))
    end if
  end function sig_angular_step

  ! Ширина окна в точках: round(span/шаг) "половина к чётному", нечётная,
  ! не шире массива (минимум 3).
  function sig_window_points(angles, span_deg) result(w)
    real(dp), intent(in) :: angles(:), span_deg
    integer(ip) :: w, n
    n = int(size(angles), ip)
    if (n < 3) then
      w = max(1_ip, n)
      return
    end if
    w = int(sig_round_even(span_deg / sig_angular_step(angles)), ip)
    w = sig_odd_window(w, n)
    if (w < 3) w = 3
  end function sig_window_points

  ! Медианный фильтр по КОЛЬЦУ (окно в точках).
  !
  ! Формула окна для точки i: mod(i - h - 1 + (0:w-1), n) + 1. "Минус
  ! единица" здесь обязательна: без неё окно съезжает на точку вправо, а с
  ! ним и весь детектор (вектор vector_03 ловил сдвиг на 2 градуса).
  function sig_median_filter(x, window) result(out)
    real(dp), intent(in) :: x(:)
    integer(ip), intent(in) :: window
    real(dp), allocatable :: out(:), buf(:)
    integer(ip) :: n, w, h, i, j, idx
    n = int(size(x), ip)
    w = sig_odd_window(window, n)
    allocate(out(n))
    if (w < 3 .or. n < 3) then
      out = sig_median(x)
      return
    end if
    h = (w - 1) / 2
    allocate(buf(w))
    do i = 1, n
      do j = 0, w - 1
        idx = modulo(i - h - 1 + j, n) + 1
        buf(j + 1) = x(idx)
      end do
      call sig_sort_asc(buf)
      out(i) = median_sorted(buf)
    end do
  end function sig_median_filter

  ! Скользящее среднее по кольцу: сумма делится на w (не mean() -- чтобы
  ! порядок суммирования совпал с остальными портами).
  function sig_smooth_wrap(x, window) result(out)
    real(dp), intent(in) :: x(:)
    integer(ip), intent(in) :: window
    real(dp), allocatable :: out(:)
    integer(ip) :: n, w, h, i, j, idx
    real(dp) :: s
    n = int(size(x), ip)
    w = sig_odd_window(window, n)
    allocate(out(n))
    if (w < 3 .or. n < 3) then
      out = x
      return
    end if
    h = (w - 1) / 2
    do i = 1, n
      s = 0.0_dp
      do j = 0, w - 1
        idx = modulo(i - h - 1 + j, n) + 1
        s = s + x(idx)
      end do
      out(i) = s / real(w, dp)
    end do
  end function sig_smooth_wrap

  ! Расстояние по кольцу (0..180 градусов).
  !
  ! ЛОВУШКА: rem()/mod() в Fortran усекают к нулю (mod(-1,360) == -1), а
  ! референс использует питоновскую семантику % (modulo(-1,360) == 359),
  ! поэтому везде modulo, а не mod.
  elemental function sig_circ_dist(a, b) result(d)
    real(dp), intent(in) :: a, b
    real(dp) :: d
    d = abs(modulo(a - b + 180.0_dp, 360.0_dp) - 180.0_dp)
  end function sig_circ_dist

  ! Локальное смещение по кольцу (-180..180 градусов).
  elemental function sig_circ_local(a, b) result(d)
    real(dp), intent(in) :: a, b
    real(dp) :: d
    d = modulo(a - b + 180.0_dp, 360.0_dp) - 180.0_dp
  end function sig_circ_local

  ! Сглаживающая ступенька 3t^2 - 2t^3 с насыщением на краях.
  elemental function sig_smoothstep(t) result(y)
    real(dp), intent(in) :: t
    real(dp) :: y
    if (t < 0.0_dp) then
      y = 0.0_dp
    else if (t > 1.0_dp) then
      y = 1.0_dp
    else
      y = t * t * (3.0_dp - 2.0_dp * t)
    end if
  end function sig_smoothstep

end module pappa_signal

