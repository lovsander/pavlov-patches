! PAPPA Fortran port -- авто-очистка выбросов (метод "iqr").
!
! Снимаем форму профиля медианным фильтром по кольцу, считаем остаток и его
! робастный масштаб; порог -- усы Тьюки (k * IQR). Повторяет
! AutoOutlierCleaner референса Python (octave/src/cleaner_*.m).
module pappa_cleaner
  use pappa_kinds, only: dp, ip
  use pappa_signal, only: sig_window_points, sig_median_filter, sig_median
  use pappa_signal, only: sig_iqr2, sig_sort_asc
  implicit none
  private

  type :: cleaner_options
    real(dp) :: baseline_deg = 1.0_dp
    real(dp) :: iqr_k = 3.0_dp
    real(dp) :: max_removed_frac = 0.5_dp
    integer(ip) :: min_points = 20
  end type cleaner_options

  ! mask -- точка выброшена; window == 0 -- очистка отключена (мало точек).
  type :: cleaner_result
    logical, allocatable :: mask(:)
    integer(ip) :: n_outliers = 0
    integer(ip) :: window = 0
  end type cleaner_result

  public :: cleaner_options, cleaner_result, cln_clean_iqr

contains

  function cln_clean_iqr(angles, radii, o) result(res)
    real(dp), intent(in) :: angles(:), radii(:)
    type(cleaner_options), intent(in), optional :: o
    type(cleaner_result) :: res
    type(cleaner_options) :: opt
    real(dp), allocatable :: base(:), r(:), sev(:), kept(:)
    real(dp) :: center, spread, denom, level
    integer(ip) :: n, w, i, k, flagged, cap

    opt = cleaner_options()
    if (present(o)) opt = o

    n = int(size(radii), ip)
    allocate(res%mask(n))
    res%mask = .false.
    res%n_outliers = 0
    res%window = 0
    if (n < opt%min_points) return

    w = sig_window_points(angles, opt%baseline_deg)
    res%window = w
    base = sig_median_filter(radii, w)
    allocate(r(n))
    r = radii - base

    center = sig_median(r)
    spread = sig_iqr2(r)
    if (spread > 1.0e-12_dp) then
      denom = spread
    else
      denom = 1.0_dp        ! защита референса: при нулевом остатке порог 3 мм
    end if

    allocate(sev(n))
    do i = 1, n
      sev(i) = abs(r(i) - center) / denom
    end do
    do i = 1, n
      res%mask(i) = sev(i) > opt%iqr_k
    end do
    flagged = count(res%mask)

    ! Предохранитель: не выбрасываем больше max_removed_frac точек.
    cap = int(floor(opt%max_removed_frac * real(n, dp)), ip)
    if (cap > 0 .and. cap < n .and. flagged > cap) then
      allocate(kept(flagged))
      k = 0
      do i = 1, n
        if (res%mask(i)) then
          k = k + 1
          kept(k) = sev(i)
        end if
      end do
      call sig_sort_asc(kept)
      level = kept(size(kept) - cap + 1)
      do i = 1, n
        if (res%mask(i)) res%mask(i) = (sev(i) >= level)
      end do
      flagged = count(res%mask)
    end if
    res%n_outliers = flagged
  end function cln_clean_iqr

end module pappa_cleaner
