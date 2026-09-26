! PAPPA Fortran port -- проверка порта по конформанс-векторам
! (spec/conformance/vectors, см. spec/conformance/README.md).
!
! Повторяет проверки cpp/conformance.cpp и pascal/src/pappa_conformance.pas:
! допуски те же -- контур 1e-6 мм, коэффициенты max(1e-8, 1e-9*|c|),
! отступы фичера ям 1e-9, центры ям 1e-6 градуса, очистка -- совпадение
! множества отброшенных точек.
!
! ЛОВУШКА СБОРКИ: gfortran (<= 13) выдаёт -Wmaybe-uninitialized на ДЕСКРИПТОРАХ
! локальных allocatable-переменных, которые впервые назначаются внутри цикла
! или ветви (`x = f(...)` при нераспределённом x). Предупреждение ложное, но
! build_fortran.ps1 считает любой вывод в stderr ошибкой сборки, поэтому такие
! локальные переменные явно инициализируются пустыми массивами в начале
! подпрограммы (allocate(x(0))), а строки -- пустой строкой (s = '').
module pappa_conformance
  use pappa_kinds, only: dp, ip
  use pappa_json, only: JP_PATH_LEN, json_doc, json_parse, json_read_text
  use pappa_json, only: json_list_files, jfind, jhas, jlen, jel
  use pappa_json, only: jint, jnum, jtext, jbool, jnums, jitem_nums
  use pappa_cleaner, only: cleaner_options, cleaner_result, cln_clean_iqr
  use pappa_detector, only: detector_options, det_zone, det_band, det_zones
  use pappa_mdl, only: pappa_options, pit_shape_options, pappa_model
  use pappa_mdl, only: mdl_new, mdl_fit, mdl_eval, mdl_degrees
  implicit none
  private

  ! Потолки вывода: вектор с сотнями расхождений не должен заливать консоль.
  integer(ip), parameter :: NOTE_MAX = 32
  integer(ip), parameter :: NOTE_LEN = 200

  ! Итог проверки одного вектора.
  type :: conf_outcome
    logical :: ok = .true.
    character(len=:), allocatable :: detail
    character(len=NOTE_LEN), allocatable :: notes(:)
  end type conf_outcome

  ! Вектор: имя файла (для отчёта) и разобранный документ.
  ! Арена json_doc лежит ВНУТРИ элемента массива -- тип не рекурсивный,
  ! поэтому массив таких значений безопасен (см. заметку про рекурсивный тип).
  type :: conf_vector
    character(len=256) :: file_name = ''
    type(json_doc) :: doc
  end type conf_vector

  public :: conf_outcome, conf_vector, conf_load_vectors
  public :: conf_check_vector, conf_load_vector
  ! Форматтер чисел «%.2e» (нужен самопроверке: сообщения в стиле остальных
  ! портов, в отличие от Fortran-овского 'es12.2' с «E» и 3 цифрами порядка).
  public :: f_e

contains

  !------------------------------ загрузка ----------------------------------

  ! Все *.json каталога по возрастанию имён (порядок как в остальных портах).
  ! Пустой каталог -- НЕ ошибка загрузки: err_msg заполняется, а программа
  ! решает сама (код возврата 2, как у C++/Pascal).
  subroutine conf_load_vectors(dir, vectors, err_msg)
    character(len=*), intent(in) :: dir
    type(conf_vector), allocatable, intent(out) :: vectors(:)
    character(len=:), allocatable, intent(out) :: err_msg
    character(len=JP_PATH_LEN), allocatable :: files(:)
    character(len=:), allocatable :: path, txt
    integer(ip) :: i, n

    err_msg = ''
    call json_list_files(dir, '*.json', files)
    n = int(size(files), ip)
    allocate(vectors(n))
    path = ''
    txt = ''
    do i = 1, n
      vectors(i)%file_name = trim(files(i))
      path = with_sep(dir)//trim(files(i))
      txt = json_read_text(path)
      vectors(i)%doc = json_parse(txt)
    end do
    if (n == 0) err_msg = 'нет каталога векторов: '//trim(dir)
  end subroutine conf_load_vectors

  ! Один вектор по имени файла (нужно самопроверке и ручным прогонам).
  function conf_load_vector(dir, name) result(v)
    character(len=*), intent(in) :: dir, name
    type(conf_vector) :: v
    character(len=:), allocatable :: txt
    v%file_name = trim(name)
    txt = json_read_text(with_sep(dir)//trim(name))
    v%doc = json_parse(txt)
  end function conf_load_vector

  !------------------------------ проверки ----------------------------------

  ! Диспетчер по полю kind: у каждой ступени пайплайна свой набор допусков.
  function conf_check_vector(v) result(res)
    type(conf_vector), intent(in) :: v
    type(conf_outcome) :: res
    res = conf_check_doc(v%doc)
  end function conf_check_vector

  ! Проверка разобранного документа вектора.
  function conf_check_doc(doc) result(res)
    type(json_doc), intent(in) :: doc
    type(conf_outcome) :: res
    character(len=:), allocatable :: fmt, kind, name
    integer(ip) :: root

    root = doc%root
    name = jtext(doc, root, 'name', '?')
    kind = jtext(doc, root, 'kind', '')
    fmt = jtext(doc, root, 'format', '')
    res%detail = ''
    if (fmt /= 'pappa-conformance') then
      res%ok = .false.
      res%detail = 'формат "'//fmt//'", ожидался "pappa-conformance"'
      return
    end if

    select case (kind)
    case ('model')
      res = conf_check_model(doc, root)
    case ('detector')
      res = conf_check_detector(doc, root)
    case ('cleaner')
      res = conf_check_cleaner(doc, root)
    case default
      res%ok = .false.
      res%detail = 'неизвестный kind: "'//kind//'"'
      return
    end select
    res%detail = kind//'/'//name//': '//res%detail
  end function conf_check_doc

  !------------------------------ модель ------------------------------------

  ! Модель: обучение на входе вектора и сверка степеней, коэффициентов,
  ! терминов фичера ям и контура.
  function conf_check_model(doc, root) result(res)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: root
    type(conf_outcome) :: res
    integer(ip) :: cfg, exp, tol, inp, n_coefs, n_terms, npat, p, j, bad_c, bad_pit
    type(pappa_options) :: opt
    type(pit_shape_options) :: ps
    type(pappa_model) :: m
    real(dp), allocatable :: pits_deg(:), angles(:), radii(:), grid(:)
    real(dp), allocatable :: want(:), got(:), want_dx(:), got_dx(:)
    real(dp), allocatable :: want_amp(:), got_amp(:), want_y(:), got_y(:)
    real(dp), allocatable :: want_deg_f(:)
    integer(ip), allocatable :: got_deg(:), want_deg(:)
    real(dp) :: rel, flr, tol_curve, delta, allowed, max_c, max_pit, max_r
    character(len=:), allocatable :: deg_txt
    logical :: deg_ok

    res%detail = ''
    ! Пустые дескрипторы: см. ЛОВУШКУ СБОРКИ в шапке модуля.
    allocate(pits_deg(0), angles(0), radii(0), grid(0))
    allocate(want(0), got(0), want_dx(0), got_dx(0))
    allocate(want_amp(0), got_amp(0), want_y(0), got_y(0))
    allocate(want_deg_f(0), got_deg(0))
    deg_txt = ''
    cfg = jfind(doc, root, 'config')
    exp = jfind(doc, root, 'expected')
    tol = jfind(doc, root, 'tolerance')
    inp = jfind(doc, root, 'input')
    if (cfg == 0 .or. exp == 0 .or. tol == 0 .or. inp == 0) then
      res%ok = .false.
      res%detail = 'в векторе нет config/expected/tolerance/input'
      return
    end if

    ! Параметры ступени: значения по умолчанию -- как у остальных портов.
    opt%n_patches = jint(doc, cfg, 'n_patches', 7_ip)
    opt%phase_deg = jnum(doc, cfg, 'phase_deg', 0.0_dp)
    opt%deg_min = jint(doc, cfg, 'deg_min', 4_ip)
    opt%deg_max = jint(doc, cfg, 'deg_max', 14_ip)
    opt%overlap_train = jnum(doc, cfg, 'overlap_train', 15.0_dp)
    opt%overlap_use = jnum(doc, cfg, 'overlap_use', 5.0_dp)
    opt%deg_elbow_tol = jnum(doc, cfg, 'deg_elbow_tol', 0.05_dp)
    opt%amplitude_scale = jnum(doc, cfg, 'amplitude_scale', 180.0_dp)
    opt%coord_mode = jtext(doc, cfg, 'coord_mode', 'normalized')

    pits_deg = nums_or(doc, cfg, 'pits_deg')
    ps%sigma_deg = jnum(doc, cfg, 'sigma_deg', 3.0_dp)
    ps%core_sigma = jnum(doc, cfg, 'pit_core_sigma', 2.0_dp)
    ps%window_sigma = jnum(doc, cfg, 'pit_window_sigma', 3.2_dp)
    ps%pit_min_amp = jnum(doc, cfg, 'pit_min_amp', 3.0e-3_dp)
    ps%tapering = jbool(doc, cfg, 'tapering', .true.)

    angles = jnums(doc, inp, 'angles_deg')
    radii = jnums(doc, inp, 'radii_mm')
    if (size(angles) /= size(radii)) then
      res%ok = .false.
      res%detail = 'вход: углов '//i_txt(size(angles))// &
                   ', радиусов '//i_txt(size(radii))
      return
    end if

    call mdl_new(m, opt, pits_deg)
    if (size(pits_deg) > 0) m%pit_shape = ps
    call mdl_fit(m, angles, radii)

    rel = jnum(doc, tol, 'coefs_rel', 1.0e-9_dp)
    flr = jnum(doc, tol, 'coefs_abs_floor', 1.0e-8_dp)
    tol_curve = jnum(doc, tol, 'curve_mm', 1.0e-6_dp)

    ! --- степени патчей: целые, сравниваются точно ------------------------
    want_deg_f = nums_or(doc, exp, 'degrees')
    allocate(want_deg(size(want_deg_f)))
    do j = 1, size(want_deg_f)
      want_deg(j) = nint(want_deg_f(j))
    end do
    got_deg = mdl_degrees(m)
    deg_ok = size(want_deg) == size(got_deg)
    if (deg_ok) then
      do j = 1, size(want_deg)
        if (want_deg(j) /= got_deg(j)) deg_ok = .false.
      end do
    end if
    if (.not. deg_ok) then
      call note_add(res, 'степени: получено ['//join_ints(got_deg)// &
                        '], ожидалось ['//join_ints(want_deg)//']')
    end if

    ! --- коэффициенты патчей и термины фичера ям --------------------------
    n_coefs = jlen(doc, jfind(doc, exp, 'coefs'))
    n_terms = jlen(doc, jfind(doc, exp, 'pit_terms'))
    max_c = 0.0_dp
    bad_c = 0
    max_pit = 0.0_dp
    bad_pit = 0
    npat = min(n_coefs, int(size(m%patches), ip))
    do p = 1, npat
      want = jitem_nums(doc, jfind(doc, exp, 'coefs'), p)
      got = patch_coefs(m, p)
      if (size(got) /= size(want)) then
        call note_add(res, 'патч '//i_txt(p - 1)//': коэффициентов '// &
                          i_txt(size(got))//' != '//i_txt(size(want)))
        bad_c = bad_c + 1
        cycle
      end if
      do j = 1, size(want)
        delta = abs(got(j) - want(j))
        allowed = max(flr, rel * abs(want(j)))
        if (delta > max_c) max_c = delta
        if (delta > allowed) then
          bad_c = bad_c + 1
          call note_add(res, 'патч '//i_txt(p - 1)//': коэфф. '//i_txt(j - 1)// &
                            ' = '//f_e(got(j))//' != '//f_e(want(j)))
        end if
      end do
    end do
    if (n_coefs /= int(size(m%patches), ip)) then
      call note_add(res, 'патчей '//i_txt(size(m%patches))// &
                        ', ожидалось '//i_txt(n_coefs))
    end if

    npat = min(n_terms, int(size(m%patches), ip))
    do p = 1, npat
      want_dx = jnums(doc, jel(doc, jfind(doc, exp, 'pit_terms'), p), 'dx_deg')
      want_amp = jnums(doc, jel(doc, jfind(doc, exp, 'pit_terms'), p), 'amp')
      got_dx = patch_pit_offsets(m, p)
      got_amp = patch_pit_coefs(m, p)
      if (size(got_dx) /= size(want_dx) .or. size(got_amp) /= size(want_amp)) then
        call note_add(res, 'патч '//i_txt(p - 1)//': терминов фичера '// &
                          i_txt(size(got_dx))//' != '//i_txt(size(want_dx)))
        bad_pit = bad_pit + 1
        cycle
      end if
      do j = 1, size(want_dx)
        if (abs(got_dx(j) - want_dx(j)) > max_pit) max_pit = abs(got_dx(j) - want_dx(j))
        if (abs(got_amp(j) - want_amp(j)) > max_pit) then
          max_pit = abs(got_amp(j) - want_amp(j))
        end if
        if (abs(got_dx(j) - want_dx(j)) > 1.0e-9_dp) then
          bad_pit = bad_pit + 1
          call note_add(res, 'патч '//i_txt(p - 1)//': dx фичера '// &
                            f_e(got_dx(j))//' != '//f_e(want_dx(j)))
        end if
        if (abs(got_amp(j) - want_amp(j)) > max(flr, rel * abs(want_amp(j)))) then
          bad_pit = bad_pit + 1
          call note_add(res, 'патч '//i_txt(p - 1)//': амплитуда фичера '// &
                            f_e(got_amp(j))//' != '//f_e(want_amp(j)))
        end if
      end do
    end do

    ! --- контур на сетке вектора: главный критерий ------------------------
    grid = nums_or(doc, jfind(doc, exp, 'curve'), 'angles_deg')
    want_y = nums_or(doc, jfind(doc, exp, 'curve'), 'radii_mm')
    got_y = mdl_eval(m, grid)
    max_r = 0.0_dp
    do j = 1, min(size(got_y), size(want_y))
      if (abs(got_y(j) - want_y(j)) > max_r) max_r = abs(got_y(j) - want_y(j))
    end do
    if (max_r > tol_curve) then
      call note_add(res, 'контур: максимум расхождения '//f_e(max_r)// &
                        ' > допуска '//f_e(tol_curve))
    end if

    ! Формат строки отчёта -- как у Pascal/C++ (см. pappa_conformance.pas).
    if (deg_ok) then
      deg_txt = 'совпали'
    else
      deg_txt = 'РАСХОДЯТСЯ'
    end if
    res%detail = 'степени '//deg_txt//', коэфф. max|Δ| '//f_e(max_c)// &
                 ' (плохих '//i_txt(bad_c)//'), термины ям max|Δ| '// &
                 f_e(max_pit)//' (плохих '//i_txt(bad_pit)//'), контур max|Δ| '// &
                 f_e(max_r)//' мм'
  end function conf_check_model

  !------------------------------ детектор ----------------------------------

  ! Детектор: безразмерный индикатор band, зоны по порогу и их центры.
  ! Зоны сравниваются отчётом (max|Δ|), центры ям -- допуском 1e-6 градуса.
  function conf_check_detector(doc, root) result(res)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: root
    type(conf_outcome) :: res
    integer(ip) :: cfg, exp, inp, zexp, n_zone, i
    type(detector_options) :: o
    type(det_zone), allocatable :: zones(:)
    real(dp), allocatable :: angles(:), radii(:), band(:), cent(:)
    real(dp), allocatable :: want_pits(:), want_z(:)
    real(dp) :: dev, d

    res%detail = ''
    ! Пустые дескрипторы: см. ЛОВУШКУ СБОРКИ в шапке модуля.
    allocate(zones(0), angles(0), radii(0), band(0))
    allocate(want_pits(0), want_z(0))
    cfg = jfind(doc, root, 'config')
    exp = jfind(doc, root, 'expected')
    inp = jfind(doc, root, 'input')
    if (cfg == 0 .or. exp == 0 .or. inp == 0) then
      res%ok = .false.
      res%detail = 'в векторе нет config/expected/input'
      return
    end if

    o%window_deg = jnum(doc, cfg, 'window_deg', 1.0_dp)
    o%wide_deg = jnum(doc, cfg, 'wide_deg', 10.0_dp)
    o%smooth_deg = jnum(doc, cfg, 'smooth_deg', 2.0_dp)
    o%k = jnum(doc, cfg, 'k', 5.5_dp)
    o%min_zone_deg = jnum(doc, cfg, 'min_zone_deg', 2.0_dp)

    angles = jnums(doc, inp, 'angles_deg')
    radii = jnums(doc, inp, 'radii_mm')
    band = det_band(angles, radii, o)
    zones = det_zones(angles, band, o)
    n_zone = int(size(zones), ip)
    allocate(cent(n_zone))
    do i = 1, n_zone
      cent(i) = 0.5_dp * (zones(i)%lo + zones(i)%hi)
    end do

    zexp = jfind(doc, exp, 'zones_deg')
    want_pits = nums_or(doc, exp, 'pits_deg')
    if (n_zone /= jlen(doc, zexp)) then
      call note_add(res, 'зон '//i_txt(n_zone)//' != '//i_txt(jlen(doc, zexp)))
    end if
    if (n_zone /= int(size(want_pits), ip)) then
      call note_add(res, 'ям '//i_txt(n_zone)//' != '//i_txt(size(want_pits)))
    end if

    dev = 0.0_dp
    do i = 1, min(n_zone, jlen(doc, zexp))
      want_z = jitem_nums(doc, zexp, i)
      if (size(want_z) < 2) cycle
      d = abs(zones(i)%lo - want_z(1))
      if (d > dev) dev = d
      if (d > 1.0e-6_dp) then
        call note_add(res, 'зона '//i_txt(i - 1)//': lo '//f_e(zones(i)%lo)// &
                          ' != '//f_e(want_z(1)))
      end if
      d = abs(zones(i)%hi - want_z(2))
      if (d > dev) dev = d
      if (d > 1.0e-6_dp) then
        call note_add(res, 'зона '//i_txt(i - 1)//': hi '//f_e(zones(i)%hi)// &
                          ' != '//f_e(want_z(2)))
      end if
    end do
    do i = 1, min(n_zone, int(size(want_pits), ip))
      d = abs(cent(i) - want_pits(i))
      if (d > dev) dev = d
      if (d > 1.0e-6_dp) then
        call note_add(res, 'центр ямы '//i_txt(i - 1)//': '//f_e(cent(i))// &
                          ' != '//f_e(want_pits(i)))
      end if
    end do

    res%detail = 'зон '//i_txt(n_zone)//'/'//i_txt(jlen(doc, zexp))// &
                 ', ям '//i_txt(n_zone)//'/'//i_txt(size(want_pits))// &
                 ', max|Δ| '//f_e(dev)//'°'
  end function conf_check_detector

  !------------------------------ очистка -----------------------------------

  ! Очистка: набор номеров отброшенных точек сравнивается точно, как в C++
  ! (позиция за позицией; в отчёт идут первые пять расхождений).
  function conf_check_cleaner(doc, root) result(res)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: root
    type(conf_outcome) :: res
    integer(ip) :: cfg, exp, inp, i, n, ngot, nwant, shown, a, b, extra, missing
    type(cleaner_options) :: o
    type(cleaner_result) :: cr
    real(dp), allocatable :: angles(:), radii(:), want_idx_f(:)
    integer(ip), allocatable :: got_idx(:), want_idx(:)
    logical, allocatable :: ref_mask(:)

    res%detail = ''
    cfg = jfind(doc, root, 'config')
    exp = jfind(doc, root, 'expected')
    inp = jfind(doc, root, 'input')
    if (cfg == 0 .or. exp == 0 .or. inp == 0) then
      res%ok = .false.
      res%detail = 'в векторе нет config/expected/input'
      return
    end if

    o%baseline_deg = jnum(doc, cfg, 'baseline_deg', 1.0_dp)
    o%iqr_k = jnum(doc, cfg, 'iqr_k', 3.0_dp)
    allocate(angles(0), radii(0))
    angles = jnums(doc, inp, 'angles_deg')
    radii = jnums(doc, inp, 'radii_mm')
    cr = cln_clean_iqr(angles, radii, o)

    ! Номера точек -- с нуля, как в векторах и остальных портах.
    n = int(size(radii), ip)
    allocate(got_idx(n))
    ngot = 0
    do i = 1, min(n, int(size(cr%mask), ip))
      if (cr%mask(i)) then
        ngot = ngot + 1
        got_idx(ngot) = i - 1
      end if
    end do

    want_idx_f = nums_or(doc, exp, 'mask_true_indices')
    nwant = int(size(want_idx_f), ip)
    allocate(want_idx(nwant))
    do i = 1, nwant
      want_idx(i) = nint(want_idx_f(i))
    end do

    ! Лишние/пропущенные относительно эталона -- как в Pascal (в отчёте),
    ! сам критерий строгий: совпадение списка целиком, как в C++.
    allocate(ref_mask(max(n, 1)))
    ref_mask = .false.
    do i = 1, nwant
      if (want_idx(i) >= 0 .and. want_idx(i) < n) ref_mask(want_idx(i) + 1) = .true.
    end do
    extra = 0
    missing = 0
    do i = 1, n
      if (i <= int(size(cr%mask), ip)) then
        if (cr%mask(i)) then
          if (.not. ref_mask(i)) extra = extra + 1
        else if (ref_mask(i)) then
          missing = missing + 1
        end if
      else if (ref_mask(i)) then
        missing = missing + 1
      end if
    end do

    if (ngot /= nwant) then
      call note_add(res, 'отброшено '//i_txt(ngot)//' точек, ожидалось '// &
                        i_txt(nwant))
    end if
    shown = 0
    do i = 1, max(ngot, nwant)
      if (shown >= 5) exit
      a = -1_ip
      b = -1_ip
      if (i <= ngot) a = got_idx(i)
      if (i <= nwant) b = want_idx(i)
      if (a /= b) then
        call note_add(res, '  позиция '//i_txt(i - 1)//': получено '//i_txt(a)// &
                          ', ожидалось '//i_txt(b))
        shown = shown + 1
      end if
    end do

    res%detail = 'выбросов '//i_txt(ngot)//' (эталон '//i_txt(nwant)// &
                 '), лишних '//i_txt(extra)//', пропущено '//i_txt(missing)// &
                 ', окно '//i_txt(cr%window)//' точек'
  end function conf_check_cleaner

  !------------------------------ вспомогательное ---------------------------

  ! Числа по ключу; отсутствие ключа -- пустой массив (у части векторов
  ! нет pits_deg/degrees, а jnums на отсутствующем ключе -- ошибка).
  function nums_or(doc, node, key) result(v)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: key
    real(dp), allocatable :: v(:)
    allocate(v(0))
    if (node /= 0 .and. jhas(doc, node, key)) then
      v = jnums(doc, node, key)
    end if
  end function nums_or

  ! Заметка о расхождении; любая заметка делает вектор непройденным
  ! (как в C++: ok = notes.empty()), число заметок ограничено.
  subroutine note_add(res, s)
    type(conf_outcome), intent(inout) :: res
    character(len=*), intent(in) :: s
    character(len=NOTE_LEN), allocatable :: tmp(:)
    integer(ip) :: n

    res%ok = .false.
    n = 0
    if (allocated(res%notes)) n = int(size(res%notes), ip)
    if (n >= NOTE_MAX) return
    allocate(tmp(n + 1))
    if (n > 0) tmp(1:n) = res%notes
    tmp(n + 1) = s
    call move_alloc(tmp, res%notes)
  end subroutine note_add

  ! Коэффициенты патча p (пустой массив, если патч не обучен).
  function patch_coefs(m, p) result(v)
    type(pappa_model), intent(in) :: m
    integer(ip), intent(in) :: p
    real(dp), allocatable :: v(:)
    allocate(v(0))
    if (allocated(m%patches(p)%coefs)) then
      v = m%patches(p)%coefs
    end if
  end function patch_coefs

  ! Отступы фичера ям патча p в градусах (пустой массив, если их нет).
  function patch_pit_offsets(m, p) result(v)
    type(pappa_model), intent(in) :: m
    integer(ip), intent(in) :: p
    real(dp), allocatable :: v(:)
    allocate(v(0))
    if (allocated(m%patches(p)%pit_offsets_deg)) then
      v = m%patches(p)%pit_offsets_deg
    end if
  end function patch_pit_offsets

  ! Амплитуды фичера ям патча p (пустой массив, если их нет).
  function patch_pit_coefs(m, p) result(v)
    type(pappa_model), intent(in) :: m
    integer(ip), intent(in) :: p
    real(dp), allocatable :: v(:)
    allocate(v(0))
    if (allocated(m%patches(p)%pit_coefs)) then
      v = m%patches(p)%pit_coefs
    end if
  end function patch_pit_coefs

  ! Список целых через запятую: [4,7,...] -> "4,7,...".
  function join_ints(v) result(s)
    integer(ip), intent(in) :: v(:)
    character(len=:), allocatable :: s
    integer(ip) :: i
    s = ''
    do i = 1, size(v)
      if (i > 1) s = s//','
      s = s//i_txt(v(i))
    end do
  end function join_ints

  ! Целое в текст без ведущих пробелов.
  function i_txt(k) result(s)
    integer(ip), intent(in) :: k
    character(len=16) :: buf
    character(len=:), allocatable :: s
    write(buf, '(i0)') k
    s = trim(buf)
  end function i_txt

  ! Число в стиле "%.2e" остальных портов: 1.35e-12, не 1.35E-12.
  function f_e(v) result(s)
    real(dp), intent(in) :: v
    character(len=16) :: buf
    character(len=:), allocatable :: s
    integer(ip) :: k
    write(buf, '(es12.2)') v
    s = trim(adjustl(buf))
    k = index(s, 'E')
    if (k > 0) s(k:k) = 'e'
  end function f_e

  ! Путь с разделителем в конце (IncludeTrailingPathDelimiter у Pascal).
  function with_sep(dir) result(p)
    character(len=*), intent(in) :: dir
    character(len=:), allocatable :: p
    p = trim(dir)
    if (len(p) > 0) then
      if (p(len(p):len(p)) == '\' .or. p(len(p):len(p)) == '/') return
    end if
    p = p//'\'
  end function with_sep

end module pappa_conformance
