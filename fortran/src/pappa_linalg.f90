! PAPPA Fortran port -- линейная алгебра: базис Чебышёва, МНК через QR
! отражениями Хаусхолдера, полиномы. Соответствует octave/src/linalg_*.m.
module pappa_linalg
  use pappa_kinds, only: dp, ip
  implicit none
  private
  public :: lin_cheb_matrix, lin_cheb_row, lin_cheb_sum
  public :: lin_lstsq, lin_polyfit, lin_polyval

contains

  ! Столбцы T_0(x)..T_deg_max(x) -- базис Чебышёва (x в [-1, 1]).
  function lin_cheb_matrix(x, deg_max) result(t)
    real(dp), intent(in) :: x(:)
    integer(ip), intent(in) :: deg_max
    real(dp), allocatable :: t(:, :)
    integer(ip) :: n, k
    n = int(size(x), ip)
    allocate(t(n, deg_max + 1))
    t = 1.0_dp
    if (deg_max >= 1) t(:, 2) = x
    do k = 3, deg_max + 1
      t(:, k) = 2.0_dp * x * t(:, k - 1) - t(:, k - 2)
    end do
  end function lin_cheb_matrix

  ! Строка T_0(x)..T_deg_max(x) -- тот же рекуррентный ряд, что и в матрице.
  function lin_cheb_row(x, deg_max) result(t)
    real(dp), intent(in) :: x
    integer(ip), intent(in) :: deg_max
    real(dp), allocatable :: t(:)
    integer(ip) :: k
    allocate(t(deg_max + 1))
    t = 0.0_dp
    t(1) = 1.0_dp
    if (deg_max >= 1) t(2) = x
    do k = 3, deg_max + 1
      t(k) = 2.0_dp * x * t(k - 1) - t(k - 2)
    end do
  end function lin_cheb_row

  ! Сумма c_k*T_k(x) по схеме Кленшоу (устойчива к накоплению ошибки).
  function lin_cheb_sum(co, deg, x) result(s)
    real(dp), intent(in) :: co(:), x
    integer(ip), intent(in) :: deg
    real(dp) :: s, b0, b1, b2
    integer(ip) :: k
    b1 = 0.0_dp
    b2 = 0.0_dp
    do k = deg, 1, -1
      b0 = 2.0_dp * x * b1 - b2 + co(k + 1)
      b2 = b1
      b1 = b0
    end do
    s = x * b1 - b2 + co(1)
  end function lin_cheb_sum

  ! МНК A*x ~= b (A -- m x n, m >= n) через QR отражениями Хаусхолдера.
  !
  ! Почему не LAPACK: у его решателей своё упорядочивание (pivoting) и своя
  ! псевдообработка вырожденных столбцов -- коэффициенты разошлись бы с
  ! остальными портами сильнее, чем допускает вектор модели (1e-9 отн.).
  ! Вход не портится (работаем с копиями a и b).
  function lin_lstsq(a_in, b_in) result(x)
    real(dp), intent(in) :: a_in(:, :), b_in(:)
    real(dp), allocatable :: x(:), a(:, :), b(:), v(:)
    integer(ip) :: m, n, k, j, i
    real(dp) :: nrm, alpha, vnorm2, cc, cb, s, d
    m = int(size(a_in, 1), ip)
    n = int(size(a_in, 2), ip)
    if (m == 0) then
      error stop 'lin_lstsq: empty matrix'
    end if
    if (size(b_in) /= m) then
      error stop 'lin_lstsq: lengths of A and b differ'
    end if
    if (m < n) then
      error stop 'lin_lstsq: need m >= n'
    end if
    a = a_in
    allocate(b(m))
    b = b_in
    allocate(v(m))

    do k = 1, n
      nrm = sqrt(sum(a(k:m, k) * a(k:m, k)))
      if (nrm < 1.0e-300_dp) cycle
      if (a(k, k) > 0.0_dp) then
        alpha = -nrm
      else
        alpha = nrm
      end if
      v = 0.0_dp
      v(k:m) = a(k:m, k)
      v(k) = v(k) - alpha
      vnorm2 = sum(v(k:m) * v(k:m))
      if (vnorm2 < 1.0e-300_dp) cycle
      do j = k, n
        cc = 2.0_dp * sum(v(k:m) * a(k:m, j)) / vnorm2
        a(k:m, j) = a(k:m, j) - cc * v(k:m)
      end do
      cb = 2.0_dp * sum(v(k:m) * b(k:m)) / vnorm2
      b(k:m) = b(k:m) - cb * v(k:m)
    end do

    allocate(x(n))
    x = 0.0_dp
    do i = n, 1, -1
      s = b(i)
      if (i < n) then
        ! Здесь произведение ЛЮБЫХ двух массивов одной формы -- скаляр:
        ! скалярное произведение строки на столбец записано явно, потому
        ! что неявное расширение формы (как в Octave) дало бы матрицу.
        s = s - sum(a(i, i + 1:n) * x(i + 1:n))
      end if
      d = a(i, i)
      if (abs(d) < 1.0e-300_dp) then
        error stop 'lin_lstsq: singular system'
      end if
      x(i) = s / d
    end do
  end function lin_lstsq

  ! МНК-полином степени deg: коэффициенты по УБЫВАНИЮ степени (как np.polyfit).
  function lin_polyfit(xs, ys, deg) result(coefs)
    real(dp), intent(in) :: xs(:), ys(:)
    integer(ip), intent(in) :: deg
    real(dp), allocatable :: coefs(:), a(:, :)
    integer(ip) :: n, pw
    n = int(size(xs), ip)
    allocate(a(n, deg + 1))
    do pw = 0, deg
      a(:, deg + 1 - pw) = xs ** pw
    end do
    coefs = lin_lstsq(a, ys)
  end function lin_polyfit

  ! Полином по схеме Горнера; коэффициенты по УБЫВАНИЮ степени (как polyfit).
  function lin_polyval(coefs, x) result(y)
    real(dp), intent(in) :: coefs(:), x
    real(dp) :: y
    integer(ip) :: k
    y = 0.0_dp
    do k = 1, size(coefs)
      y = y * x + coefs(k)
    end do
  end function lin_polyval

end module pappa_linalg
