! PAPPA Fortran port -- проверка порта по конформанс-векторам
! (spec/conformance/vectors, см. spec/conformance/README.md).
!
!   conformance.exe [каталог-с-векторами]
!
! Коды возврата (как у C++/Pascal): 0 -- всё сошлось, 1 -- расхождения,
! 2 -- нет каталога или в нём нет *.json.
program conformance
  use pappa_kinds, only: ip
  use pappa_conformance, only: conf_vector, conf_outcome
  use pappa_conformance, only: conf_load_vectors, conf_check_vector
  implicit none
  character(len=1024) :: dir
  character(len=:), allocatable :: err_msg, line
  type(conf_vector), allocatable :: vectors(:)
  type(conf_outcome) :: res
  integer(ip) :: i, j, bad, nfile

  if (command_argument_count() >= 1) then
    call get_command_argument(1, dir)
  else
    dir = '../spec/conformance/vectors'
  end if

  call conf_load_vectors(trim(dir), vectors, err_msg)
  if (len(err_msg) > 0) then
    write(*, '(a)') trim(err_msg)
    stop 2
  end if

  write(*, '(a,i0,a)') 'Конформанс-векторы PAPPA (Fortran): ', size(vectors), &
                       ' файл(ов) в '//trim(dir)
  write(*,*) ''

  bad = 0
  line = ''
  do i = 1, size(vectors)
    res = conf_check_vector(vectors(i))
    if (.not. res%ok) bad = bad + 1
    ! Имя файла -- в колонку 46 знаков, как в остальных портах.
    ! ЛОВУШКА: у строки ФИКСИРОВАННОЙ длины присваивание дополняет хвост
    ! пробелами, поэтому `pad = trim(pad)//' '` не меняет len_trim и цикл
    ! `do while (len_trim(pad) < 46)` не кончается. Строка здесь
    ! отложенной длины, и длина наращивается явно через repeat.
    nfile = len_trim(vectors(i)%file_name)
    line = vectors(i)%file_name(1:nfile)
    if (nfile < 46) line = line//repeat(' ', 46 - nfile)
    if (res%ok) then
      line = line//'OK    '//res%detail
    else
      line = line//'FAIL  '//res%detail
    end if
    write(*, '(a)') line
    if (allocated(res%notes)) then
      do j = 1, size(res%notes)
        write(*, '(a)') repeat(' ', 52)//'-> '//trim(res%notes(j))
      end do
    end if
  end do

  write(*,*) ''
  write(*, '(a,i0,a,i0,a)') 'Итог: ', size(vectors) - bad, '/', size(vectors), &
                            ' векторов пройдено'
  if (bad > 0) then
    write(*, '(a,i0)') 'ВЫВОД: расхождений ', bad
    stop 1
  end if
  write(*,*) 'ВЫВОД: Fortran порт проходит все векторы'
  ! Без кода: gfortran печатает "STOP 0" в stderr, а build_fortran.ps1 считает
  ! любой вывод в stderr ошибкой сборки (см. ЛОВУШКУ СБОРКИ в модуле).
  stop
end program conformance
