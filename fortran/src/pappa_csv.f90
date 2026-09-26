! PAPPA Fortran port -- чтение CSV по заголовку и посекционный расчёт
! (соответствие pascal/src/pappa_csv.pas и go/pappa/csv.go).
!
! Здесь же живут типы пайплайна: строка CSV, опции прогона и готовая секция
! (модель + счётчики + время обучения). Документ пишет модуль pappa_document.
module pappa_csv
  use pappa_kinds, only: dp, ip
  use pappa_json, only: json_read_text
  use pappa_cleaner, only: cleaner_options, cleaner_result, cln_clean_iqr
  use pappa_detector, only: detector_options, det_pits
  use pappa_mdl, only: pappa_options, pappa_model, mdl_new, mdl_fit
  implicit none
  private

  ! Предел длины строки/поля CSV (см. комментарий у csv_split_line).
  integer(ip), parameter :: CSV_LINE_MAX = 1024
  public :: CSV_LINE_MAX

  ! Строка CSV (колонки ищутся по заголовку, лишние игнорируются).
  type :: csv_row
    integer(ip) :: section_id = 0
    real(dp) :: height_mm = 0.0_dp
    real(dp) :: angle_deg = 0.0_dp
    real(dp) :: radius_mm = 0.0_dp
  end type csv_row

  ! Опции всего прогона: модель + очистка + детектор + два переключателя.
  type :: pipe_options
    type(pappa_options) :: model
    type(cleaner_options) :: cleaner
    type(detector_options) :: detector
    logical :: pits = .true.
    logical :: verbose = .true.
  end type pipe_options

  ! Готовая секция: модель и то, что нужно документу.
  type :: section_model
    integer(ip) :: section_id = 0
    real(dp) :: height_mm = 0.0_dp
    type(pappa_model) :: model
    integer(ip) :: n_points_total = 0
    integer(ip) :: n_outliers = 0
    integer(ip) :: n_used = 0
    real(dp) :: fit_time_ms = 0.0_dp
    character(len=:), allocatable :: description
    real(dp), allocatable :: pits(:)
  end type section_model

  public :: csv_row, pipe_options, section_model
  public :: pipe_default_options, csv_split_line, csv_load, csv_process

contains

  ! Значения по умолчанию: как в остальных портах (N=7, фаза 24.75, ямы включены).
  function pipe_default_options() result(o)
    type(pipe_options) :: o
    o%model = pappa_options()
    o%cleaner = cleaner_options()
    o%detector = detector_options()
    o%pits = .true.
    o%verbose = .true.
  end function pipe_default_options

  pure function is_sep(c) result(tf)
    character(len=1), intent(in) :: c
    logical :: tf
    tf = (c == achar(10)) .or. (c == achar(13))
  end function is_sep

  ! Разбор строки по запятым с обрезкой пробелов у полей (как SplitComma).
  ! Длина поля -- ФИКСИРОВАННАЯ (CSV_LINE_MAX): `allocate` массива строк с
  ! отложенной длиной требует type-spec, поэтому поля и строки ограничены
  ! сверху, а не растут сами. Для CSV с числами 1024 байта -- с большим запасом.
  function csv_split_line(s) result(parts)
    character(len=*), intent(in) :: s
    character(len=CSV_LINE_MAX), allocatable :: parts(:)
    integer(ip) :: i, k, n, st
    n = 1
    do i = 1, len(s)
      if (s(i:i) == ',') n = n + 1
    end do
    allocate(parts(n))
    parts = ''
    k = 0
    st = 1
    ! Условие "конец строки ИЛИ запятая" разложено на ветви намеренно: Fortran
    ! не обязан считать .or. слева направо, и s(st:i-1) при i = len(s)+1
    ! вычислялось бы с выходом за границу строки.
    do i = 1, len(s) + 1
      if (i > len(s)) then
        parts(k + 1) = trim(adjustl(s(st:i - 1)))
        k = k + 1
      else if (s(i:i) == ',') then
        parts(k + 1) = trim(adjustl(s(st:i - 1)))
        k = k + 1
        st = i + 1
      end if
    end do
  end function csv_split_line

  ! Следующая непустая строка текста: ST -- позиция продолжения, OK=.false. --
  ! строк больше нет. Разделителями считаются и #10, и #13, поэтому CRLF и LF
  ! обрабатываются одинаково (как в остальных портах).
  subroutine csv_next_line(txt, st, line, ok)
    character(len=*), intent(in) :: txt
    integer(ip), intent(inout) :: st
    character(len=:), allocatable, intent(out) :: line
    logical, intent(out) :: ok
    integer(ip) :: i
    line = ''
    ok = .false.
    do while (st <= len(txt))
      do while (st <= len(txt))
        if (.not. is_sep(txt(st:st))) exit
        st = st + 1
      end do
      if (st > len(txt)) return
      i = st
      do while (i <= len(txt))
        if (is_sep(txt(i:i))) exit
        i = i + 1
      end do
      line = trim(txt(st:i - 1))
      st = i
      if (len(line) > 0) then
        ok = .true.
        return
      end if
    end do
  end subroutine csv_next_line

  ! Номер колонки по имени заголовка (0 -- колонки нет).
  function csv_col_index(head, name) result(k)
    character(len=*), intent(in) :: head(:)
    character(len=*), intent(in) :: name
    integer(ip) :: k, i
    k = 0
    do i = 1, size(head)
      if (head(i) == name) then
        k = i
        return
      end if
    end do
  end function csv_col_index

  function csv_to_int(s, who) result(v)
    character(len=*), intent(in) :: s, who
    integer(ip) :: v, ios
    read(s, *, iostat=ios) v
    if (ios /= 0) error stop 'csv: поле '//who//' не целое: "'//trim(s)//'"'
  end function csv_to_int

  function csv_to_double(s, who) result(v)
    character(len=*), intent(in) :: s, who
    real(dp) :: v
    integer(ip) :: ios
    read(s, *, iostat=ios) v
    if (ios /= 0) error stop 'csv: поле '//who//' не число: "'//trim(s)//'"'
  end function csv_to_double

  ! Чтение CSV: колонки section_id, height_mm, angle_deg, radius_mm (по заголовку).
  ! Два прохода по тексту: первый считает строки с данными (массив под них
  ! распределяется сразу нужного размера), второй их разбирает.
  function csv_load(path) result(rows)
    character(len=*), intent(in) :: path
    type(csv_row), allocatable :: rows(:)
    type(csv_row), allocatable :: tmp(:)
    character(len=:), allocatable :: txt, line
    character(len=CSV_LINE_MAX), allocatable :: head(:), f(:)
    integer(ip) :: st, no, nrow, isec, ih, ia, ir, need
    logical :: ok

    txt = json_read_text(path)     ! файл целиком: тот же приём, что в json-модуле
    st = 1
    call csv_next_line(txt, st, line, ok)
    if (.not. ok) error stop 'csv: пустой файл: '//path
    head = csv_split_line(line)
    isec = csv_col_index(head, 'section_id')
    ih = csv_col_index(head, 'height_mm')
    ia = csv_col_index(head, 'angle_deg')
    ir = csv_col_index(head, 'radius_mm')
    if (isec == 0) error stop 'csv: нет колонки section_id'
    if (ih == 0) error stop 'csv: нет колонки height_mm'
    if (ia == 0) error stop 'csv: нет колонки angle_deg'
    if (ir == 0) error stop 'csv: нет колонки radius_mm'
    need = max(max(isec, ih), max(ia, ir))

    nrow = 0
    do
      call csv_next_line(txt, st, line, ok)
      if (.not. ok) exit
      nrow = nrow + 1
    end do
    if (nrow == 0) error stop 'csv: нет строк с данными'

    allocate(rows(nrow))
    st = 1
    call csv_next_line(txt, st, line, ok)      ! повторно пропускаем заголовок
    no = 0
    do
      call csv_next_line(txt, st, line, ok)
      if (.not. ok) exit
      f = csv_split_line(line)
      if (size(f) < need) cycle                ! строка без нужных колонок
      no = no + 1
      rows(no)%section_id = csv_to_int(f(isec), 'section_id')
      rows(no)%height_mm = csv_to_double(f(ih), 'height_mm')
      rows(no)%angle_deg = csv_to_double(f(ia), 'angle_deg')
      rows(no)%radius_mm = csv_to_double(f(ir), 'radius_mm')
    end do
    if (no < nrow) then
      allocate(tmp(no))
      tmp = rows(1:no)
      call move_alloc(tmp, rows)
    end if
  end function csv_load

  ! Посекционный расчёт: точки по возрастанию угла -> очистка -> ямы -> обучение.
  function csv_process(rows, o) result(secs)
    type(csv_row), intent(in) :: rows(:)
    type(pipe_options), intent(in) :: o
    type(section_model), allocatable :: secs(:)
    type(section_model), allocatable :: stmp(:)
    type(csv_row), allocatable :: group(:)
    type(csv_row) :: keyrow
    type(cleaner_result) :: cr
    type(pappa_model) :: m
    type(section_model) :: sec = section_model()
    integer(ip), allocatable :: idtmp(:), ids(:)
    real(dp), allocatable :: ang(:), rad(:), ac(:), rc(:), pc(:)
    real(dp), allocatable :: atmp(:), rtmp(:)
    character(len=64) :: buf
    real(dp) :: h0, ms
    integer(ip) :: i, j, k, n, cnt, sid, rate, t0, t1
    logical :: found

    ! Уникальные идентификаторы сечений, затем по возрастанию.
    allocate(idtmp(max(size(rows), 1)))
    n = 0
    do i = 1, size(rows)
      found = .false.
      do j = 1, n
        if (idtmp(j) == rows(i)%section_id) found = .true.
      end do
      if (.not. found) then
        n = n + 1
        idtmp(n) = rows(i)%section_id
      end if
    end do
    allocate(ids(n))
    ids = idtmp(1:n)
    do i = 2, n
      k = i - 1
      do while (k >= 1)
        if (ids(k) <= ids(k + 1)) exit
        j = ids(k)
        ids(k) = ids(k + 1)
        ids(k + 1) = j
        k = k - 1
      end do
    end do

    allocate(secs(0))
    do i = 1, n
      sid = ids(i)
      allocate(group(size(rows)))
      cnt = 0
      do j = 1, size(rows)
        if (rows(j)%section_id == sid) then
          cnt = cnt + 1
          group(cnt) = rows(j)
        end if
      end do
      ! Сортировка точек сечения по углу (вставками, с обменом).
      do j = 2, cnt
        k = j - 1
        do while (k >= 1)
          if (group(k)%angle_deg <= group(k + 1)%angle_deg) exit
          keyrow = group(k)
          group(k) = group(k + 1)
          group(k + 1) = keyrow
          k = k - 1
        end do
      end do
      h0 = group(1)%height_mm

      allocate(ang(cnt))
      allocate(rad(cnt))
      do j = 1, cnt
        ang(j) = group(j)%angle_deg
        rad(j) = group(j)%radius_mm
      end do

      cr = cln_clean_iqr(ang, rad, o%cleaner)     ! window == 0: очистка выключена
      allocate(ac(cnt))
      allocate(rc(cnt))
      k = 0
      do j = 1, cnt
        if (.not. cr%mask(j)) then
          k = k + 1
          ac(k) = ang(j)
          rc(k) = rad(j)
        end if
      end do
      allocate(atmp(k))
      allocate(rtmp(k))
      atmp = ac(1:k)
      rtmp = rc(1:k)
      call move_alloc(atmp, ac)
      call move_alloc(rtmp, rc)

      if (o%pits) then
        pc = det_pits(ac, rc, o%detector)
      else
        allocate(pc(0))
      end if
      call mdl_new(m, o%model, pc)
      call system_clock(t0, rate)
      call mdl_fit(m, ac, rc)
      call system_clock(t1)
      ms = 1000.0_dp * real(t1 - t0, dp) / real(rate, dp)

      ! Формат описания взят у референса: pascal/src/pappa_csv.pas
      ! (Format('сечение %d, h=%.0f мм', ...)) и cpp/main.cpp.
      write(buf, '(a,i0,a,i0,a)') 'сечение ', sid, ', h=', nint(h0), ' мм'
      sec%section_id = sid
      sec%height_mm = h0
      sec%model = m
      sec%n_points_total = cnt
      sec%n_outliers = cr%n_outliers
      sec%n_used = k
      sec%pits = pc
      sec%fit_time_ms = ms
      sec%description = trim(buf)
      ! Рост массива секций: move_alloc освобождает старый массив сам.
      allocate(stmp(size(secs) + 1))
      if (size(secs) > 0) stmp(1:size(secs)) = secs
      stmp(size(stmp)) = sec
      call move_alloc(stmp, secs)

      if (o%verbose) then
        ! Строка -- как в pascal/src/pappa_csv.pas: '  секция %d (h=%.0f мм):
        ! точек %d, выброшено %d, ям найдено %d, обучение %.0f мс'.
        write(*, '(a,i0,a,i0,a,i0,a,i0,a,i0,a,i0,a)') &
          '  секция ', sid, ' (h=', nint(h0), ' мм): точек ', cnt, &
          ', выброшено ', cr%n_outliers, ', ям найдено ', size(pc), &
          ', обучение ', nint(ms), ' мс'
      end if

      deallocate(group, ang, rad, ac, rc, pc)
    end do
  end function csv_process

end module pappa_csv
