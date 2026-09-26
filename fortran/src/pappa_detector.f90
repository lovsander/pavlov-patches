! PAPPA Fortran port -- детектор ям (трещин): безразмерный индикатор band,
! зоны превышения порога и их центры (octave/src/detector_*.m).
module pappa_detector
  use pappa_kinds, only: dp, ip
  use pappa_signal, only: sig_median_filter, sig_window_points, sig_smooth_wrap
  use pappa_signal, only: sig_robust_sigma, sig_median, sig_sort_asc
  implicit none
  private

  type :: detector_options
    real(dp) :: window_deg = 1.0_dp
    real(dp) :: wide_deg = 10.0_dp
    real(dp) :: smooth_deg = 2.0_dp
    real(dp) :: k = 5.5_dp
    real(dp) :: min_zone_deg = 2.0_dp
  end type detector_options

  type :: det_zone
    real(dp) :: lo = 0.0_dp
    real(dp) :: hi = 0.0_dp
  end type det_zone

  public :: detector_options, det_zone, det_band, det_zones, det_pits

contains

  ! Безразмерный индикатор ям (в "MAD-ах"):
  !   band = |узкая медиана - широкая медиана|, сглаженный,
  !   нормированный на свою робастную sigma.
  function det_band(angles, radii, o) result(out)
    real(dp), intent(in) :: angles(:), radii(:)
    type(detector_options), intent(in), optional :: o
    real(dp), allocatable :: out(:), narrow(:), wide(:), band(:)
    type(detector_options) :: opt
    real(dp) :: s
    opt = detector_options()
    if (present(o)) opt = o
    allocate(narrow(size(radii)), wide(size(radii)), band(size(radii)))
    narrow = sig_median_filter(radii, sig_window_points(angles, opt%window_deg))
    wide = sig_median_filter(radii, sig_window_points(angles, opt%wide_deg))
    band = abs(narrow - wide)
    out = sig_smooth_wrap(band, sig_window_points(angles, opt%smooth_deg))
    s = sig_robust_sigma(out)
    if (s > 1.0e-12_dp) then
      out = out / s
    else
      out = 0.0_dp           ! гладкий профиль: индикатор без масштаба
    end if
  end function det_band

  ! Зоны, где индикатор превышает порог k.
  function det_zones(angles, values, o) result(zones)
    real(dp), intent(in) :: angles(:), values(:)
    type(detector_options), intent(in), optional :: o
    type(det_zone), allocatable :: zones(:)
    type(detector_options) :: opt
    logical, allocatable :: mask(:)
    integer(ip) :: n, i
    opt = detector_options()
    if (present(o)) opt = o
    n = int(size(values), ip)
    allocate(mask(n))
    do i = 1, n
      mask(i) = values(i) > opt%k
    end do
    zones = det_mask_to_zones(angles, mask, opt)
  end function det_zones

  ! Центры ям (градусы) по индикатору band_indicator.
  function det_pits(angles, radii, o) result(pits)
    real(dp), intent(in) :: angles(:), radii(:)
    type(detector_options), intent(in), optional :: o
    real(dp), allocatable :: pits(:)
    type(det_zone), allocatable :: zones(:)
    integer(ip) :: k
    if (present(o)) then
      zones = det_zones(angles, det_band(angles, radii, o), o)
    else
      zones = det_zones(angles, det_band(angles, radii))
    end if
    allocate(pits(size(zones)))
    do k = 1, size(zones)
      pits(k) = 0.5_dp * (zones(k)%lo + zones(k)%hi)
    end do
  end function det_pits

  ! Непрерывные зоны по маске; углы -- по возрастанию. Зона -- пара lo/hi.
  function det_mask_to_zones(angles, mask, o) result(zones)
    real(dp), intent(in) :: angles(:)
    logical, intent(in) :: mask(:)
    type(detector_options), intent(in) :: o
    type(det_zone), allocatable :: zones(:), tmp(:), kept(:), merged(:)
    real(dp), allocatable :: d(:)
    real(dp) :: step
    integer(ip) :: n, i, j, nz, k, nkeep
    logical :: any_mask

    n = int(size(angles), ip)
    allocate(zones(0))
    any_mask = .false.
    do i = 1, n
      if (mask(i)) any_mask = .true.
    end do
    if (.not. any_mask) return

    if (n <= 1) then
      step = 1.0_dp
    else
      allocate(d(n - 1))
      do i = 1, n - 1
        d(i) = angles(i + 1) - angles(i)
      end do
      step = sig_median(d)
    end if

    allocate(tmp(n))
    nz = 0
    i = 1
    do while (i <= n)
      if (.not. mask(i)) then
        i = i + 1
        cycle
      end if
      j = i
      do while (j + 1 <= n)
        if (.not. mask(j + 1)) exit
        j = j + 1
      end do
      nz = nz + 1
      tmp(nz)%lo = angles(i) - step / 2.0_dp
      tmp(nz)%hi = angles(j) + step / 2.0_dp
      i = j + 1
    end do
    zones = tmp(1:nz)

    ! Кольцо: зона, доходящая до 360 и начинающаяся с 0, -- это одна зона.
    if (nz > 1 .and. mask(1) .and. mask(n)) then
      allocate(merged(nz))
      merged(1)%lo = zones(nz)%lo - 360.0_dp
      merged(1)%hi = zones(1)%hi
      do k = 2, nz - 1
        merged(k) = zones(k)
      end do
      zones = merged(1:nz - 1)
    end if

    ! Отсечка зон уже min_zone_deg. Свой буфер (tmp уже занят маской зон).
    allocate(kept(max(1_ip, size(zones))))
    nkeep = 0
    do k = 1, size(zones)
      if ((zones(k)%hi - zones(k)%lo) >= o%min_zone_deg) then
        nkeep = nkeep + 1
        kept(nkeep) = zones(k)
      end if
    end do
    zones = kept(1:nkeep)
  end function det_mask_to_zones

end module pappa_detector
