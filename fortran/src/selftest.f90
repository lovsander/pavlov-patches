! PAPPA Fortran port -- самопроверка: конформанс-векторы + дымовой тест
! пайплайна (ровно то же, что pascal/src/selftest.lpr).
!
!   selftest.exe [каталог-с-векторами]
!
! Код возврата: 0 -- всё прошло, иначе -- число провалов.
program selftest
  use pappa_kinds, only: dp, ip
  use pappa_csv, only: csv_row, csv_load
  use pappa_mdl, only: pappa_model, mdl_new, mdl_fit, mdl_eval
  use pappa_conformance, only: conf_vector, conf_outcome
  use pappa_conformance, only: conf_load_vectors, conf_check_vector, f_e
  implicit none
  character(len=1024) :: dir
  character(len=256) :: buf
  character(len=:), allocatable :: err_msg, path
  type(conf_vector), allocatable :: vectors(:)
  type(conf_outcome) :: res
  type(csv_row), allocatable :: rows(:)
  type(pappa_model) :: m
  real(dp), allocatable :: angles(:), radii(:), curve(:)
  real(dp) :: maxerr, pi
  integer(ip) :: i, u, failures

  failures = 0
  pi = 4.0_dp*atan(1.0_dp)

  if (command_argument_count() >= 1) then
    call get_command_argument(1, dir)
  else
    dir = '../spec/conformance/vectors'
  end if
  write(*, '(a)') 'Fortran SelfTest: '//trim(dir)

  !------------------------- конформанс-векторы -----------------------------
  call conf_load_vectors(trim(dir), vectors, err_msg)
  write(buf, '(a,i0,a)') 'векторы конформанса (', size(vectors), '):'
  write(*, '(a)') trim(buf)
  if (len(err_msg) > 0) call check(.false., trim(err_msg))
  call check(size(vectors) >= 4, 'не меньше 4 векторов')
  do i = 1, size(vectors)
    res = conf_check_vector(vectors(i))
    call check(res%ok, trim(vectors(i)%file_name)//' -- '//res%detail)
    ! Замечания печатаем сразу под строкой вектора: иначе в отчёте
    ! самопроверки видно только «FAIL», а причину пришлось бы искать
    ! повторным запуском conformance.exe.
    if (.not. res%ok) call print_notes(res)
  end do

  !--------------------- дымовой тест пайплайна (CSV -> модель) -------------
  write(*, '(a)') 'дымовой тест пайплайна (гладкая синусоида, 360 точек):'
  path = temp_file('pappa_fortran_smoke.csv')
  open(newunit=u, file=trim(path), status='replace', action='write')
  write(u, '(a)') 'section_id,height_mm,angle_deg,radius_mm'
  do i = 0, 359
    write(u, '(a,i0,a,f0.6)') '0,0,', i, ',', &
      50.0_dp + 0.4_dp*sin(real(i, dp)*pi/180.0_dp)
  end do
  close(u)

  rows = csv_load(trim(path))
  open(newunit=u, file=trim(path), status='old')
  close(u, status='delete')
  write(buf, '(a,i0,a)') 'разбор CSV: ', size(rows), ' точек (нужно 360)'
  call check(size(rows) == 360, trim(buf))

  allocate(angles(size(rows)), radii(size(rows)))
  do i = 1, size(rows)
    angles(i) = rows(i)%angle_deg
    radii(i) = rows(i)%radius_mm
  end do

  call mdl_new(m)                      ! без ям: как TModel.Create(..., nil)
  call mdl_fit(m, angles, radii)
  write(buf, '(a,i0)') 'патчей ', size(m%patches)
  call check(size(m%patches) == 7, trim(buf))

  curve = mdl_eval(m, angles)
  maxerr = 0.0_dp
  do i = 1, size(curve)
    maxerr = max(maxerr, abs(curve(i) - radii(i)))
  end do
  write(buf, '(a,a,a)') 'контур гладкой синусоиды: max|Δ| = ', f_e(maxerr), ' мм'
  call check(maxerr < 1.0e-6_dp, trim(buf))

  !------------------------------- итог -------------------------------------
  if (failures == 0) then
    write(*, '(a)') 'ВЫВОД: SelfTest пройден'
    ! Без кода: gfortran печатает "STOP 0" в stderr, а build_fortran.ps1 считает
    ! любой вывод в stderr ошибкой сборки.
    stop
  end if
  write(*, '(a,i0)') 'ВЫВОД: провалов ', failures
  stop failures

contains

  subroutine check(ok, what)
    logical, intent(in) :: ok
    character(len=*), intent(in) :: what
    if (ok) then
      write(*, '(a)') '  [ok] '//what
    else
      write(*, '(a)') '  [FAIL] '//what
      failures = failures + 1
    end if
  end subroutine check

  subroutine print_notes(r)
    type(conf_outcome), intent(in) :: r
    integer(ip) :: k
    if (.not. allocated(r%notes)) return
    do k = 1, size(r%notes)
      write(*, '(a)') '         '//trim(r%notes(k))
    end do
  end subroutine print_notes

  ! Временный файл в %TEMP% (в стандартном Фортране нет функции каталога
  ! временных файлов; тот же приём, что в pappa_json).
  function temp_file(name) result(p)
    character(len=*), intent(in) :: name
    character(len=:), allocatable :: p
    character(len=1024) :: tmp
    call get_environment_variable('TEMP', tmp)
    if (len_trim(tmp) == 0) call get_environment_variable('TMP', tmp)
    if (len_trim(tmp) == 0) tmp = '.'
    p = trim(tmp)//'\'//trim(name)
  end function temp_file

end program selftest
