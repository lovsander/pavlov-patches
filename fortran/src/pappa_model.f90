! PAPPA Fortran port -- модель: патчи с адаптивной степенью, smoothstep-смешивание
! (partition of unity) и оконный гауссов фичер ям.
!
! В Octave модель -- структура-ЗНАЧЕНИЕ; здесь это производный тип с
! intent(inout)/intent(out), поэтому обучение выглядит так же явно:
!   call mdl_fit(m, angles, radii).
!
! ВНИМАНИЕ: модуль назван pappa_mdl, а не pappa_model: gfortran запрещает
! производный тип с тем же именем, что и содержащий его модуль (тип ниже --
! pappa_model, как в остальных портах).
module pappa_mdl
  use pappa_kinds, only: dp, ip
  use pappa_signal, only: sig_circ_dist, sig_circ_local, sig_smoothstep, sig_percentile
  use pappa_linalg, only: lin_cheb_matrix, lin_lstsq, lin_polyval
  implicit none
  private

  integer(ip), parameter :: PART_TOTAL = 0, PART_POLY = 1, PART_PIT = 2

  ! Параметры модели PAPPA (как model_options в остальных портах).
  type :: pappa_options
    integer(ip) :: n_patches = 7
    real(dp) :: phase_deg = 24.75_dp
    integer(ip) :: deg_min = 4
    integer(ip) :: deg_max = 14
    real(dp) :: overlap_train = 15.0_dp
    real(dp) :: overlap_use = 5.0_dp
    real(dp) :: deg_elbow_tol = 0.05_dp
    real(dp) :: amplitude_scale = 180.0_dp
    character(len=16) :: coord_mode = 'normalized'
  end type pappa_options

  type :: pit_shape_options
    real(dp) :: sigma_deg = 3.0_dp
    real(dp) :: core_sigma = 2.0_dp
    real(dp) :: window_sigma = 3.2_dp
    real(dp) :: pit_min_amp = 3.0e-3_dp
    logical :: tapering = .true.
  end type pit_shape_options

  ! Один патч: коэффициенты, видимые ямы и статистика обучающего окна.
  type :: pappa_patch
    real(dp) :: center_deg = 0.0_dp
    integer(ip) :: degree = 0
    integer(ip) :: n_points = 0
    real(dp), allocatable :: coefs(:)
    real(dp), allocatable :: pit_offsets_deg(:)
    real(dp), allocatable :: pit_coefs(:)
    real(dp) :: amplitude_mm = 0.0_dp
    real(dp) :: mean_radius_mm = 0.0_dp
    real(dp) :: amplitude_norm = 0.0_dp
    real(dp) :: deg_elbow_tol = 0.0_dp
    real(dp) :: rmse_selected_mm = 0.0_dp
    real(dp) :: rmse_best_mm = 0.0_dp
    integer(ip) :: n_train_points = 0
    real(dp) :: rmse_mm = 0.0_dp
    real(dp) :: mae_mm = 0.0_dp
    real(dp) :: max_err_mm = 0.0_dp
    real(dp) :: correlation = 0.0_dp
  end type pappa_patch

  type :: pappa_model
    type(pappa_options) :: options
    type(pit_shape_options) :: pit_shape
    real(dp), allocatable :: pits(:)
    type(pappa_patch), allocatable :: patches(:)
    real(dp) :: half_sector = 0.0_dp
    logical :: is_fitted = .false.
  end type pappa_model

  public :: PART_TOTAL, PART_POLY, PART_PIT
  public :: pappa_options, pit_shape_options, pappa_patch, pappa_model
  public :: mdl_new, mdl_half_train, mdl_half_use, mdl_has_pits
  public :: mdl_pit_shape_deg, mdl_pit_shape_arr, mdl_pit_offsets
  public :: mdl_window_of, mdl_estimate_degree, mdl_fit
  public :: mdl_weight, mdl_eval, mdl_eval_part, mdl_degrees

contains

  ! Новая (необученная) модель; pits_deg -- центры ям в градусах.
  subroutine mdl_new(m, o, pits_deg)
    type(pappa_model), intent(out) :: m
    type(pappa_options), intent(in), optional :: o
    real(dp), intent(in), optional :: pits_deg(:)
    if (present(o)) m%options = o
    m%pit_shape = pit_shape_options()
    if (present(pits_deg)) then
      m%pits = modulo(pits_deg, 360.0_dp)
    else
      allocate(m%pits(0))
    end if
    allocate(m%patches(0))
    m%half_sector = 0.0_dp
    m%is_fitted = .false.
  end subroutine mdl_new

  ! Полуширина ОБУЧАЮЩЕГО окна патча (полсектора + overlap_train).
  function mdl_half_train(m) result(h)
    type(pappa_model), intent(in) :: m
    real(dp) :: h
    h = m%half_sector + m%options%overlap_train
  end function mdl_half_train

  ! Полуширина окна ПРИМЕНЕНИЯ патча (полсектора + overlap_use).
  function mdl_half_use(m) result(h)
    type(pappa_model), intent(in) :: m
    real(dp) :: h
    h = m%half_sector + m%options%overlap_use
  end function mdl_half_use

  ! Есть ли в модели ямные термы.
  function mdl_has_pits(m) result(tf)
    type(pappa_model), intent(in) :: m
    logical :: tf
    tf = size(m%pits) > 0
  end function mdl_has_pits

  ! Вес патча (partition of unity): 1 внутри сектора, smoothstep в перекрытии,
  ! 0 снаружи окна применения.
  function mdl_weight(m, d_deg, half_use_deg) result(w)
    type(pappa_model), intent(in) :: m
    real(dp), intent(in) :: d_deg, half_use_deg
    real(dp) :: w
    if (d_deg <= m%half_sector) then
      w = 1.0_dp
    else if (d_deg <= half_use_deg) then
      w = sig_smoothstep(1.0_dp - (d_deg - m%half_sector) / (half_use_deg - m%half_sector))
    else
      w = 0.0_dp
    end if
  end function mdl_weight

  ! Оконный гаусс ямной фичи как функция расстояния от центра ямы (градусы):
  ! exp(-d^2/2sigma^2) с опциональной smoothstep-отсечкой на границе окна.
  function mdl_pit_shape_deg(m, d_deg) result(v)
    type(pappa_model), intent(in) :: m
    real(dp), intent(in) :: d_deg
    real(dp) :: v, d, sigma, base, core, edge, t
    d = abs(d_deg)
    sigma = m%pit_shape%sigma_deg
    base = exp(-(d * d) / (2.0_dp * sigma * sigma))
    if (.not. m%pit_shape%tapering) then
      v = base
      return
    end if
    core = m%pit_shape%core_sigma * sigma
    edge = m%pit_shape%window_sigma * sigma
    if (edge <= core) then
      v = base
      return
    end if
    t = min(max((edge - d) / (edge - core), 0.0_dp), 1.0_dp)
    v = base * t * t * (3.0_dp - 2.0_dp * t)
  end function mdl_pit_shape_deg

  ! То же для массива расстояний (столбец базиса фичера ям).
  function mdl_pit_shape_arr(m, d_deg) result(v)
    type(pappa_model), intent(in) :: m
    real(dp), intent(in) :: d_deg(:)
    real(dp), allocatable :: v(:)
    integer(ip) :: i
    allocate(v(size(d_deg)))
    do i = 1, size(d_deg)
      v(i) = mdl_pit_shape_deg(m, d_deg(i))
    end do
  end function mdl_pit_shape_arr

  ! Смещения ВИДИМЫХ ям в локальной системе патча (градусы).
  function mdl_pit_offsets(m, center_deg, half_win_deg) result(dx)
    type(pappa_model), intent(in) :: m
    real(dp), intent(in) :: center_deg, half_win_deg
    real(dp), allocatable :: dx(:), tmp(:)
    real(dp) :: d
    integer(ip) :: i, k
    if (size(m%pits) == 0) then
      allocate(dx(0))
      return
    end if
    allocate(dx(size(m%pits)))
    k = 0
    do i = 1, size(m%pits)
      d = sig_circ_local(m%pits(i), center_deg)
      if (abs(d) <= half_win_deg) then
        k = k + 1
        dx(k) = d
      end if
    end do
    ! Нельзя писать dx = dx(1:k): присваивание аллокату со сменой формы
    ! сначала освобождает переменную, и такая самоприсваивающая запись --
    ! неопределённое поведение. Идём через временный массив.
    allocate(tmp(k))
    tmp = dx(1:k)
    call move_alloc(tmp, dx)
  end function mdl_pit_offsets

  ! Точки обучающего окна патча в локальной координате (нормированной или
  ! сырой). Порядок обхода -- как в остальных портах: сдвиги -360, 0, +360,
  ! внутри -- по возрастанию угла.
  subroutine mdl_window_of(m, angles, radii, center, xs, ys)
    type(pappa_model), intent(in) :: m
    real(dp), intent(in) :: angles(:), radii(:), center
    real(dp), allocatable, intent(out) :: xs(:), ys(:)
    real(dp), allocatable :: dxs(:), tmp(:)
    real(dp), parameter :: shifts(3) = [-360.0_dp, 0.0_dp, 360.0_dp]
    real(dp) :: half, dx
    integer(ip) :: ish, i, n, k
    logical :: norm
    half = mdl_half_train(m)
    norm = (m%options%coord_mode /= 'raw')
    n = int(size(angles), ip)
    allocate(dxs(n * 3), ys(n * 3))
    k = 0
    do ish = 1, 3
      do i = 1, n
        dx = angles(i) + shifts(ish) - center
        if (dx >= -half .and. dx <= half) then
          k = k + 1
          dxs(k) = dx
          ys(k) = radii(i)
        end if
      end do
    end do
    allocate(tmp(k))
    if (norm) then
      tmp = dxs(1:k) / half
    else
      tmp = dxs(1:k)
    end if
    call move_alloc(tmp, xs)
    allocate(tmp(k))
    tmp = ys(1:k)
    call move_alloc(tmp, ys)
  end subroutine mdl_window_of

  ! Правило "локтя": наименьшая ЧЁТНАЯ степень, на которой RMSE обучающего
  ! окна не хуже лучшей более чем на deg_elbow_tol. Возвращает
  ! [степень, RMSE выбранной, лучшая RMSE] в est(1:3).
  !
  ! Свип степеней -- ОДНОЙ матрицей Грама в базисе Чебышёва и RMSE по явным
  ! остаткам (в нормированном режиме); в режиме coord_mode == "raw" базис
  ! Чебышёва неприменим (x вне [-1, 1]) -- там прямой полиномиальный МНК.
  subroutine mdl_estimate_degree(m, xs, ys, est)
    type(pappa_model), intent(in) :: m
    real(dp), intent(in) :: xs(:), ys(:)
    real(dp), intent(out) :: est(3)
    real(dp), allocatable :: degs(:), rmses(:), a(:, :), co(:), tt(:, :), yc(:)
    real(dp), allocatable :: gram(:, :), rhs(:)
    real(dp) :: r, best, limit, yref
    integer(ip) :: n, deg, pw, nd, dmax, p, k, l, nn, sel, best_deg

    n = int(size(xs), ip)
    if (n < 5) then
      est = [real(m%options%deg_min, dp), 0.0_dp, 0.0_dp]
      return
    end if

    allocate(degs((m%options%deg_max - m%options%deg_min) / 2 + 1))
    allocate(rmses(size(degs)))
    nd = 0
    best_deg = m%options%deg_min
    best = huge(1.0_dp)

    if (m%options%coord_mode == 'raw') then
      do deg = m%options%deg_min, m%options%deg_max, 2
        allocate(a(n, deg + 1))
        do pw = 0, deg
          a(:, deg + 1 - pw) = xs ** pw
        end do
        co = lin_lstsq(a, ys)
        r = sqrt(sum((matmul(a, co) - ys) ** 2) / real(n, dp))
        nd = nd + 1
        degs(nd) = real(deg, dp)
        rmses(nd) = r
        if (r < best) then
          best = r
          best_deg = deg
        end if
        deallocate(a, co)
      end do
    else
      dmax = m%options%deg_max
      yref = sum(ys) / real(n, dp)
      tt = lin_cheb_matrix(xs, dmax)
      yc = ys - yref
      p = dmax + 1
      allocate(gram(p, p), rhs(p))
      do k = 1, p
        do l = 1, p
          gram(k, l) = sum(tt(:, k) * tt(:, l))
        end do
        rhs(k) = sum(tt(:, k) * yc)
      end do
      do deg = m%options%deg_min, dmax, 2
        nn = deg + 1
        co = lin_lstsq(gram(1:nn, 1:nn), rhs(1:nn))
        r = sqrt(sum((matmul(tt(:, 1:nn), co) - yc) ** 2) / real(n, dp))
        nd = nd + 1
        degs(nd) = real(deg, dp)
        rmses(nd) = r
        if (r < best) then
          best = r
          best_deg = deg
        end if
      end do
    end if

    limit = best * (1.0_dp + m%options%deg_elbow_tol)
    sel = best_deg
    est(2) = best
    do k = 1, nd
      if (rmses(k) <= limit) then
        sel = int(degs(k), ip)
        est(2) = rmses(k)
        exit
      end if
    end do
    est(1) = real(sel, dp)
    est(3) = best
  end subroutine mdl_estimate_degree

  ! Обучение модели: патчи с адаптивной степенью, smoothstep-смешивание и
  ! оконный гауссов фичер ям.
  !
  ! ВНИМАНИЕ: модель -- intent(inout), вызывать как call mdl_fit(m, a, r).
  subroutine mdl_fit(m, angles, radii)
    type(pappa_model), intent(inout) :: m
    real(dp), intent(in) :: angles(:), radii(:)
    real(dp), allocatable :: centers(:), xs(:), ys(:), a(:, :), co(:), shape(:)
    real(dp), allocatable :: offs(:), kept_offsets(:), kept_coefs(:), poly_coef(:)
    real(dp) :: sector, ht, est(3)
    integer(ip) :: ci, np, n, ncol, deg, pw, j, nkeep

    if (size(angles) /= size(radii)) error stop 'mdl_fit: lengths differ'
    if (size(angles) < 10) error stop 'mdl_fit: too few points'

    np = m%options%n_patches
    sector = 360.0_dp / real(np, dp)
    m%half_sector = sector / 2.0_dp
    allocate(centers(np))
    do ci = 1, np
      centers(ci) = modulo(real(ci - 1, dp) * sector + m%half_sector &
                           + m%options%phase_deg, 360.0_dp)
    end do
    ht = mdl_half_train(m)
    deallocate(m%patches)
    allocate(m%patches(0))

    do ci = 1, np
      call mdl_window_of(m, angles, radii, centers(ci), xs, ys)
      n = int(size(xs), ip)
      if (n < 5) cycle

      call mdl_estimate_degree(m, xs, ys, est)
      deg = int(est(1), ip)
      offs = mdl_pit_offsets(m, centers(ci), ht)

      ncol = deg + 1 + int(size(offs), ip)
      allocate(a(n, ncol))
      do pw = 0, deg
        a(:, deg + 1 - pw) = xs ** pw
      end do
      do j = 1, size(offs)
        a(:, deg + 1 + j) = mdl_pit_shape_arr(m, abs(xs * ht - offs(j)))
      end do
      co = lin_lstsq(a, ys)
      poly_coef = co(1:deg + 1)

      ! Отсечка ям, которые в окне патча "не видны" (pit_min_amp).
      allocate(kept_offsets(size(offs)), kept_coefs(size(offs)))
      nkeep = 0
      do j = 1, size(offs)
        shape = mdl_pit_shape_arr(m, abs(xs * ht - offs(j)))
        if (maxval(abs(co(deg + 1 + j) * shape)) >= m%pit_shape%pit_min_amp) then
          nkeep = nkeep + 1
          kept_offsets(nkeep) = offs(j)
          kept_coefs(nkeep) = co(deg + 1 + j)
        end if
      end do

      call mdl_push_patch(m, centers(ci), deg, xs, ys, poly_coef, &
                          kept_offsets(1:nkeep), kept_coefs(1:nkeep), &
                          est(2), est(3), angles, radii)
      ! shape заполняется только при непустом списке ям (size(offs) > 0).
      if (allocated(shape)) deallocate(shape)
      deallocate(a, co, poly_coef, offs, kept_offsets, kept_coefs)
    end do
    m%is_fitted = .true.
  end subroutine mdl_fit

  ! Дописать патч к модели (аналог m.patches{end+1} = ...). Массив патчей
  ! растёт через временный массив: тип содержит аллокаты, поэтому
  ! конструктор массива [...] здесь неприменим.
  subroutine mdl_push_patch(m, c0, deg, xs, ys, poly_coef, kept_offsets, &
                            kept_coefs, rmse_sel, rmse_best, angles, radii)
    type(pappa_model), intent(inout) :: m
    real(dp), intent(in) :: c0, xs(:), ys(:), poly_coef(:), kept_offsets(:)
    real(dp), intent(in) :: kept_coefs(:), rmse_sel, rmse_best, angles(:), radii(:)
    integer(ip), intent(in) :: deg
    type(pappa_patch) :: p
    type(pappa_patch), allocatable :: tmp(:)
    integer(ip) :: n_old
    call mdl_make_patch(m, c0, deg, xs, ys, poly_coef, kept_offsets, kept_coefs, &
                        rmse_sel, rmse_best, angles, radii, p)
    n_old = int(size(m%patches), ip)
    allocate(tmp(n_old + 1))
    if (n_old > 0) tmp(1:n_old) = m%patches
    tmp(n_old + 1) = p
    call move_alloc(tmp, m%patches)
  end subroutine mdl_push_patch

  ! Метрики и статистика патча по его обучающему окну (полный базис).
  subroutine mdl_make_patch(m, c0, deg, xs, ys, poly_coef, kept_offsets, &
                            kept_coefs, rmse_sel, rmse_best, angles, radii, p)
    type(pappa_model), intent(in) :: m
    real(dp), intent(in) :: c0, xs(:), ys(:), poly_coef(:), kept_offsets(:)
    real(dp), intent(in) :: kept_coefs(:), rmse_sel, rmse_best, angles(:), radii(:)
    integer(ip), intent(in) :: deg
    type(pappa_patch), intent(out) :: p
    real(dp), allocatable :: fit_vals(:), sec(:)
    real(dp) :: v, e, sse, sae, mx, mf, my, cov, vf, vy, corr
    real(dp) :: dist, amp, mean_sec, amp_norm, ht
    integer(ip) :: n, nf, i, j, nsec

    n = int(size(xs), ip)
    ht = mdl_half_train(m)
    sse = 0.0_dp
    sae = 0.0_dp
    mx = 0.0_dp
    allocate(fit_vals(n))
    do i = 1, n
      v = lin_polyval(poly_coef, xs(i))
      do j = 1, size(kept_offsets)
        v = v + kept_coefs(j) * mdl_pit_shape_deg(m, abs(xs(i) * ht - kept_offsets(j)))
      end do
      fit_vals(i) = v
      e = v - ys(i)
      sse = sse + e * e
      sae = sae + abs(e)
      mx = max(mx, abs(e))
    end do

    nf = n
    mf = sum(fit_vals) / real(nf, dp)
    my = sum(ys) / real(nf, dp)
    cov = 0.0_dp
    vf = 0.0_dp
    vy = 0.0_dp
    do i = 1, n
      cov = cov + (fit_vals(i) - mf) * (ys(i) - my)
      vf = vf + (fit_vals(i) - mf) ** 2
      vy = vy + (ys(i) - my) ** 2
    end do
    if (vf > 0.0_dp .and. vy > 0.0_dp) then
      corr = cov / sqrt(vf * vy)
    else
      corr = 0.0_dp
    end if

    ! Справочные метрики сектора: P95 - P5 и среднее по точкам сектора.
    allocate(sec(size(angles)))
    nsec = 0
    do i = 1, size(angles)
      dist = abs(modulo(angles(i) - c0 + 180.0_dp, 360.0_dp) - 180.0_dp)
      if (dist <= m%half_sector) then
        nsec = nsec + 1
        sec(nsec) = radii(i)
      end if
    end do
    amp = 0.0_dp
    mean_sec = 0.0_dp
    if (nsec >= 5) then
      amp = sig_percentile(sec(1:nsec), 95.0_dp) - sig_percentile(sec(1:nsec), 5.0_dp)
      mean_sec = sum(sec(1:nsec)) / real(nsec, dp)
    end if
    if (mean_sec > 0.0_dp) then
      amp_norm = amp / mean_sec
    else
      amp_norm = 0.0_dp
    end if

    p%center_deg = c0
    p%degree = deg
    p%n_points = n
    p%coefs = poly_coef
    p%pit_offsets_deg = kept_offsets
    p%pit_coefs = kept_coefs
    p%amplitude_mm = amp
    p%mean_radius_mm = mean_sec
    p%amplitude_norm = amp_norm
    p%deg_elbow_tol = m%options%deg_elbow_tol
    p%rmse_selected_mm = rmse_sel
    p%rmse_best_mm = rmse_best
    p%n_train_points = n
    p%rmse_mm = sqrt(sse / real(nf, dp))
    p%mae_mm = sae / real(nf, dp)
    p%max_err_mm = mx
    p%correlation = corr
  end subroutine mdl_make_patch

  ! Степени патчей по порядку (диагностика и конформанс-вектор).
  function mdl_degrees(m) result(d)
    type(pappa_model), intent(in) :: m
    integer(ip), allocatable :: d(:)
    integer(ip) :: k
    allocate(d(size(m%patches)))
    do k = 1, size(m%patches)
      d(k) = m%patches(k)%degree
    end do
  end function mdl_degrees

  ! Полный контур модели (° -> мм).
  function mdl_eval(m, angles) result(y)
    type(pappa_model), intent(in) :: m
    real(dp), intent(in) :: angles(:)
    real(dp), allocatable :: y(:)
    y = mdl_eval_part(m, angles, PART_TOTAL)
  end function mdl_eval

  ! Контур с выбором членов: PART_TOTAL | PART_POLY | PART_PIT.
  ! Нормированное smoothstep-смешивание патчей (partition of unity).
  function mdl_eval_part(m, angles, part) result(out)
    type(pappa_model), intent(in) :: m
    real(dp), intent(in) :: angles(:)
    integer(ip), intent(in) :: part
    real(dp), allocatable :: out(:)
    real(dp) :: a, w, dx, x, v, sum_wv, sum_w, hu, ht
    integer(ip) :: k, pi, j
    if (.not. m%is_fitted) error stop 'mdl_eval_part: model is not fitted'
    hu = mdl_half_use(m)
    ht = mdl_half_train(m)
    allocate(out(size(angles)))
    do k = 1, size(angles)
      a = angles(k)
      sum_wv = 0.0_dp
      sum_w = 0.0_dp
      do pi = 1, size(m%patches)
        w = mdl_weight(m, sig_circ_dist(a, m%patches(pi)%center_deg), hu)
        if (w <= 0.0_dp) cycle
        dx = sig_circ_local(a, m%patches(pi)%center_deg)
        if (m%options%coord_mode == 'raw') then
          x = dx
        else
          x = dx / ht
        end if
        v = 0.0_dp
        if (part /= PART_PIT) v = v + lin_polyval(m%patches(pi)%coefs, x)
        if (part /= PART_POLY) then
          do j = 1, size(m%patches(pi)%pit_offsets_deg)
            v = v + m%patches(pi)%pit_coefs(j) &
                * mdl_pit_shape_deg(m, abs(x * ht - m%patches(pi)%pit_offsets_deg(j)))
          end do
        end if
        sum_wv = sum_wv + w * v
        sum_w = sum_w + w
      end do
      if (sum_w > 0.0_dp) then
        out(k) = sum_wv / sum_w
      else
        out(k) = 0.0_dp
      end if
    end do
  end function mdl_eval_part

end module pappa_mdl





