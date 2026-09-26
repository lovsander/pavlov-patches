! PAPPA Fortran port -- запись папки образца.
! Тот же контракт, что у остальных портов репозитория:
!   <out_dir>/sample.json              манифест (format pappa-sample v1.0)
!   <out_dir>/sections/NN.pappa.json   документ сечения (pappa v2.0)
! Ключи и порядок повторяют pascal/src/pappa_document.pas и cpp/sample_writer.cpp:
! папки от разных портов сравниваются численно (python/studies/verify_port.py).
!
! Отличие от Pascal ровно одно: ПУСТОЙ массив печатается как `[]` (в Pascal
! ArrStart/ArrEnd всегда вставляют перевод строки, и получается «[\n   \n]»).
! Так делают остальные порты и эталонные файлы samples/*/sections/*.pappa.json,
! а сравниваются документы всё равно через разбор JSON, не побайтно.
module pappa_document
  use pappa_kinds, only: dp, ip, pappa_version, pappa_language
  use pappa_json, only: text_buf, tb_init, tb_add, tb_text
  use pappa_json, only: json_esc, json_num_text, json_write_text
  use pappa_mdl, only: pappa_options, pappa_model, pappa_patch
  use pappa_mdl, only: mdl_has_pits, mdl_half_train, mdl_half_use
  use pappa_cleaner, only: cleaner_options
  use pappa_detector, only: detector_options
  use pappa_csv, only: section_model
  implicit none
  private

  character(len=1), parameter :: NL = achar(10)

  ! Опции папки образца (совпадают с TSampleOptions из Pascal).
  type :: sample_options
    character(len=:), allocatable :: input_csv
    logical :: pits = .true.
    character(len=:), allocatable :: description
    type(cleaner_options) :: cleaner
    type(detector_options) :: detector
  end type sample_options

  ! Писатель документа: текстовый буфер + глубина вложенности.
  type :: doc_writer
    type(text_buf) :: b
    integer(ip) :: depth = 0
  end type doc_writer

  public :: sample_options, doc_default_sample, doc_iso_utc_now
  public :: doc_save_section, doc_save_sample

contains

  function doc_default_sample() result(o)
    type(sample_options) :: o
    o%input_csv = ''
    o%pits = .true.
    o%description = 'PAPPA Fortran port'
    o%cleaner = cleaner_options()
    o%detector = detector_options()
  end function doc_default_sample

  !---------------------- дата-время (IsoUtcNow из Pascal) -------------------

  ! Текущее время в UTC как 'yyyy-mm-ddThh:mm:ssZ'.
  ! DATE_AND_TIME отдаёт МЕСТНОЕ время и смещение от UTC в минутах
  ! (values(4)); UTC = местное - смещение, поэтому возможен переход суток.
  function doc_iso_utc_now() result(s)
    integer(ip) :: v(8), y, mo, d, h, mi, tot
    character(len=32) :: buf
    character(len=:), allocatable :: s
    call date_and_time(values=v)
    tot = v(5) * 60 + v(6) - v(4)
    y = v(1)
    mo = v(2)
    d = v(3)
    do while (tot < 0)
      tot = tot + 1440
      call prev_day(y, mo, d)
    end do
    do while (tot >= 1440)
      tot = tot - 1440
      call next_day(y, mo, d)
    end do
    h = tot / 60
    mi = modulo(tot, 60)
    write(buf, '(i4.4,a,i2.2,a,i2.2,a,i2.2,a,i2.2,a)') &
      y, '-', mo, '-', d, 'T', h, ':', mi, ':'
    write(buf(len_trim(buf) + 1:), '(i2.2,a)') v(7), 'Z'
    s = trim(buf)
  end function doc_iso_utc_now

  pure function leap_year(y) result(tf)
    integer(ip), intent(in) :: y
    logical :: tf
    tf = (modulo(y, 4) == 0 .and. modulo(y, 100) /= 0) .or. (modulo(y, 400) == 0)
  end function leap_year

  pure function month_days(y, mo) result(n)
    integer(ip), intent(in) :: y, mo
    integer(ip) :: n
    integer(ip), parameter :: L(12) = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if (mo == 2 .and. leap_year(y)) then
      n = 29
    else
      n = L(mo)
    end if
  end function month_days

  subroutine next_day(y, mo, d)
    integer(ip), intent(inout) :: y, mo, d
    if (d < month_days(y, mo)) then
      d = d + 1
      return
    end if
    d = 1
    if (mo < 12) then
      mo = mo + 1
    else
      mo = 1
      y = y + 1
    end if
  end subroutine next_day

  subroutine prev_day(y, mo, d)
    integer(ip), intent(inout) :: y, mo, d
    if (d > 1) then
      d = d - 1
      return
    end if
    if (mo > 1) then
      mo = mo - 1
    else
      mo = 12
      y = y - 1
    end if
    d = month_days(y, mo)
  end subroutine prev_day

  !----------------------- писатель (TWriter из Pascal) ---------------------

  subroutine dw_reset(w)
    type(doc_writer), intent(out) :: w
    call tb_init(w%b)
    w%depth = 0
  end subroutine dw_reset

  function dw_ind(w) result(s)
    type(doc_writer), intent(in) :: w
    character(len=:), allocatable :: s
    s = repeat(' ', 2 * w%depth)
  end function dw_ind

  subroutine dw_raw(w, s)
    type(doc_writer), intent(inout) :: w
    character(len=*), intent(in) :: s
    call tb_add(w%b, s)
  end subroutine dw_raw

  subroutine dw_obj_start(w)
    type(doc_writer), intent(inout) :: w
    call tb_add(w%b, '{')
    w%depth = w%depth + 1
    call tb_add(w%b, NL // dw_ind(w))
  end subroutine dw_obj_start

  subroutine dw_obj_end(w)
    type(doc_writer), intent(inout) :: w
    w%depth = w%depth - 1
    call tb_add(w%b, NL // dw_ind(w) // '}')
  end subroutine dw_obj_end

  subroutine dw_arr_start(w)
    type(doc_writer), intent(inout) :: w
    call tb_add(w%b, '[')
    w%depth = w%depth + 1
    call tb_add(w%b, NL // dw_ind(w))
  end subroutine dw_arr_start

  subroutine dw_arr_end(w)
    type(doc_writer), intent(inout) :: w
    w%depth = w%depth - 1
    call tb_add(w%b, NL // dw_ind(w) // ']')
  end subroutine dw_arr_end

  ! Пустой массив: `[]` (см. комментарий к модулю).
  subroutine dw_arr_empty(w)
    type(doc_writer), intent(inout) :: w
    call tb_add(w%b, '[]')
  end subroutine dw_arr_empty

  subroutine dw_comma(w)
    type(doc_writer), intent(inout) :: w
    call tb_add(w%b, ',' // NL // dw_ind(w))
  end subroutine dw_comma

  ! Разделитель элементов массива: перед первым -- только перевод строки.
  subroutine dw_next(w, first)
    type(doc_writer), intent(inout) :: w
    logical, intent(in) :: first
    if (first) then
      call tb_add(w%b, NL // dw_ind(w))
    else
      call tb_add(w%b, ',' // NL // dw_ind(w))
    end if
  end subroutine dw_next

  subroutine dw_key(w, k)
    type(doc_writer), intent(inout) :: w
    character(len=*), intent(in) :: k
    call tb_add(w%b, dw_ind(w) // '"' // k // '": ')
  end subroutine dw_key

  subroutine dw_str(w, s)
    type(doc_writer), intent(inout) :: w
    character(len=*), intent(in) :: s
    ! trim ОБЯЗАТЕЛЕН: строковые поля модели -- это character фиксированной
    ! длины (например `coord_mode` = len 16), и без этого в JSON уезжали
    ! хвостовые пробелы: "normalized      ". Python-загрузчик такие значения
    ! уже не принимает (`coord_mode: ожидается 'normalized' или 'raw'`).
    call tb_add(w%b, '"' // json_esc(trim(s)) // '"')
  end subroutine dw_str

  subroutine dw_num(w, v)
    type(doc_writer), intent(inout) :: w
    real(dp), intent(in) :: v
    call tb_add(w%b, json_num_text(v))
  end subroutine dw_num

  subroutine dw_int(w, v)
    type(doc_writer), intent(inout) :: w
    integer(ip), intent(in) :: v
    character(len=32) :: buf
    write(buf, '(i0)') v
    call tb_add(w%b, trim(buf))
  end subroutine dw_int

  subroutine dw_bool(w, v)
    type(doc_writer), intent(inout) :: w
    logical, intent(in) :: v
    if (v) then
      call tb_add(w%b, 'true')
    else
      call tb_add(w%b, 'false')
    end if
  end subroutine dw_bool

  subroutine dw_kv_str(w, k, v)
    type(doc_writer), intent(inout) :: w
    character(len=*), intent(in) :: k, v
    call dw_key(w, k)
    call dw_str(w, v)
  end subroutine dw_kv_str

  subroutine dw_kv_num(w, k, v)
    type(doc_writer), intent(inout) :: w
    character(len=*), intent(in) :: k
    real(dp), intent(in) :: v
    call dw_key(w, k)
    call dw_num(w, v)
  end subroutine dw_kv_num

  subroutine dw_kv_int(w, k, v)
    type(doc_writer), intent(inout) :: w
    character(len=*), intent(in) :: k
    integer(ip), intent(in) :: v
    call dw_key(w, k)
    call dw_int(w, v)
  end subroutine dw_kv_int

  subroutine dw_kv_bool(w, k, v)
    type(doc_writer), intent(inout) :: w
    character(len=*), intent(in) :: k
    logical, intent(in) :: v
    call dw_key(w, k)
    call dw_bool(w, v)
  end subroutine dw_kv_bool

  ! Значение без кавычек: так записаны `cleaner` и `detector` в конфиге.
  subroutine dw_kv_raw(w, k, v)
    type(doc_writer), intent(inout) :: w
    character(len=*), intent(in) :: k, v
    call dw_key(w, k)
    call dw_raw(w, v)
  end subroutine dw_kv_raw

  !------------------------- документ сечения (pappa v2.0) ------------------

  ! Массив патчей: числа `coefs` и `centers_deg` идут в одну строку, как в
  ! остальных портах (в Pascal NumVal/Comma-в-строке давало тот же результат).
  subroutine write_num_list(w, vals)
    type(doc_writer), intent(inout) :: w
    real(dp), intent(in) :: vals(:)
    integer(ip) :: j
    if (size(vals) == 0) then
      call dw_arr_empty(w)
      return
    end if
    call dw_arr_start(w)
    do j = 1, size(vals)
      if (j > 1) call dw_raw(w, ', ')
      call dw_num(w, vals(j))
    end do
    call dw_arr_end(w)
  end subroutine write_num_list

  subroutine write_patches(w, m)
    type(doc_writer), intent(inout) :: w
    type(pappa_model), intent(in) :: m
    type(pappa_patch) :: p
    integer(ip) :: i, j
    call dw_key(w, 'patches')
    if (size(m%patches) == 0) then
      call dw_arr_empty(w)
      return
    end if
    call dw_arr_start(w)
    do i = 1, size(m%patches)
      p = m%patches(i)
      call dw_next(w, i == 1)
      call dw_obj_start(w)
      call dw_kv_num(w, 'center_deg', p%center_deg); call dw_comma(w)
      call dw_kv_int(w, 'degree', p%degree);         call dw_comma(w)
      call dw_kv_int(w, 'n_points', p%n_points);     call dw_comma(w)
      call dw_key(w, 'coefs')
      call write_num_list(w, p%coefs)
      call dw_comma(w)

      call dw_key(w, 'metrics')
      call dw_obj_start(w)
      call dw_kv_num(w, 'amplitude_mm', p%amplitude_mm);            call dw_comma(w)
      call dw_kv_num(w, 'mean_radius_mm', p%mean_radius_mm);        call dw_comma(w)
      call dw_kv_num(w, 'amplitude_norm', p%amplitude_norm);        call dw_comma(w)
      call dw_kv_num(w, 'deg_elbow_tol', p%deg_elbow_tol);          call dw_comma(w)
      call dw_kv_num(w, 'rmse_selected_mm', p%rmse_selected_mm);    call dw_comma(w)
      call dw_kv_num(w, 'rmse_best_mm', p%rmse_best_mm);            call dw_comma(w)
      call dw_kv_int(w, 'n_train_points', p%n_train_points)
      call dw_obj_end(w)
      call dw_comma(w)

      call dw_key(w, 'stats')
      call dw_obj_start(w)
      call dw_kv_num(w, 'rmse_mm', p%rmse_mm);          call dw_comma(w)
      call dw_kv_num(w, 'mae_mm', p%mae_mm);            call dw_comma(w)
      call dw_kv_num(w, 'max_err_mm', p%max_err_mm);    call dw_comma(w)
      call dw_kv_num(w, 'correlation', p%correlation)
      call dw_obj_end(w)

      ! Термины фичера ям -- ключ у КАЖДОГО патча, когда модель с ямами
      ! (включая пустой список): так ждёт загрузчик Python.
      if (mdl_has_pits(m)) then
        call dw_comma(w)
        call dw_key(w, 'pit_terms')
        if (size(p%pit_offsets_deg) == 0) then
          call dw_arr_empty(w)
        else
          call dw_arr_start(w)
          do j = 1, size(p%pit_offsets_deg)
            call dw_next(w, j == 1)
            call dw_obj_start(w)
            call dw_kv_num(w, 'dx_deg', p%pit_offsets_deg(j)); call dw_comma(w)
            call dw_kv_num(w, 'amp', p%pit_coefs(j))
            call dw_obj_end(w)
          end do
          call dw_arr_end(w)
        end if
      end if
      call dw_obj_end(w)
    end do
    call dw_raw(w, NL // dw_ind(w))
    call dw_arr_end(w)
  end subroutine write_patches

  function doc_save_section(path, sec) result(out_path)
    character(len=*), intent(in) :: path
    type(section_model), intent(in) :: sec
    character(len=:), allocatable :: out_path
    type(doc_writer) :: w
    real(dp) :: v
    character(len=:), allocatable :: desc
    if (.not. sec%model%is_fitted) then
      error stop 'save_section_document: модель не обучена'
    end if
    desc = ''
    if (allocated(sec%description)) desc = sec%description

    call dw_reset(w)
    call dw_obj_start(w)
    call dw_kv_str(w, 'format', 'pappa');            call dw_comma(w)
    call dw_kv_str(w, 'version', '2.0');             call dw_comma(w)
    if (mdl_has_pits(sec%model)) then
      call dw_kv_str(w, 'method', 'PitPatchApproximator')
    else
      call dw_kv_str(w, 'method', 'PatchApproximator')
    end if
    call dw_comma(w)
    call dw_kv_str(w, 'created', doc_iso_utc_now()); call dw_comma(w)

    call dw_key(w, 'software')
    call dw_obj_start(w)
    call dw_kv_str(w, 'language', pappa_language);   call dw_comma(w)
    call dw_kv_str(w, 'pappa_version', pappa_version)
    call dw_obj_end(w)
    call dw_comma(w)

    call dw_key(w, 'meta')
    call dw_obj_start(w)
    call dw_kv_int(w, 'section_id', sec%section_id); call dw_comma(w)
    call dw_kv_num(w, 'height_mm', sec%height_mm);   call dw_comma(w)
    call dw_kv_str(w, 'source', 'csv');              call dw_comma(w)
    call dw_kv_str(w, 'description', desc)
    call dw_obj_end(w)
    call dw_comma(w)

    call dw_key(w, 'global')
    call dw_obj_start(w)
    call dw_key(w, 'units')
    call dw_obj_start(w)
    call dw_kv_str(w, 'angle', 'degree'); call dw_comma(w)
    call dw_kv_str(w, 'length', 'mm')
    call dw_obj_end(w)
    call dw_comma(w)
    call dw_kv_int(w, 'n_patches', sec%model%options%n_patches);         call dw_comma(w)
    call dw_kv_num(w, 'half_sector_deg', sec%model%half_sector);         call dw_comma(w)
    call dw_kv_num(w, 'phase_deg', sec%model%options%phase_deg);         call dw_comma(w)
    v = mdl_half_train(sec%model)
    call dw_kv_num(w, 'half_train_deg', v);                              call dw_comma(w)
    v = mdl_half_use(sec%model)
    call dw_kv_num(w, 'half_use_deg', v);                                call dw_comma(w)
    call dw_kv_num(w, 'overlap_train_deg', sec%model%options%overlap_train)
    call dw_comma(w)
    call dw_kv_num(w, 'overlap_use_deg', sec%model%options%overlap_use);  call dw_comma(w)
    call dw_kv_int(w, 'deg_min', sec%model%options%deg_min);              call dw_comma(w)
    call dw_kv_int(w, 'deg_max', sec%model%options%deg_max);              call dw_comma(w)
    call dw_kv_str(w, 'coord_mode', sec%model%options%coord_mode);        call dw_comma(w)
    call dw_kv_num(w, 'deg_elbow_tol', sec%model%options%deg_elbow_tol);  call dw_comma(w)
    call dw_kv_num(w, 'amplitude_scale', sec%model%options%amplitude_scale)
    if (mdl_has_pits(sec%model)) then
      call dw_comma(w)
      call dw_key(w, 'pit')
      call dw_obj_start(w)
      call dw_kv_num(w, 'sigma_deg', sec%model%pit_shape%sigma_deg)
      call dw_comma(w)
      call dw_kv_num(w, 'core_sigma', sec%model%pit_shape%core_sigma)
      call dw_comma(w)
      call dw_kv_num(w, 'window_sigma', sec%model%pit_shape%window_sigma)
      call dw_comma(w)
      call dw_kv_num(w, 'pit_min_amp', sec%model%pit_shape%pit_min_amp)
      call dw_comma(w)
      call dw_kv_bool(w, 'tapering', sec%model%pit_shape%tapering)
      call dw_comma(w)
      call dw_key(w, 'centers_deg')
      call write_num_list(w, sec%model%pits)
      call dw_obj_end(w)
    end if
    call dw_obj_end(w)
    call dw_comma(w)

    call write_patches(w, sec%model)
    call dw_comma(w)

    call dw_key(w, 'statistics')
    call dw_obj_start(w)
    call dw_kv_int(w, 'n_points_total', sec%n_points_total); call dw_comma(w)
    call dw_kv_int(w, 'n_outliers_removed', sec%n_outliers); call dw_comma(w)
    call dw_kv_num(w, 'fit_time_ms', sec%fit_time_ms)
    call dw_obj_end(w)

    call dw_obj_end(w)
    call json_write_text(path, tb_text(w%b) // NL)
    out_path = path
  end function doc_save_section

  !------------------------ папка образца (sample.json) ---------------------

  ! Путь с разделителем в конце (IncludeTrailingPathDelimiter у Pascal).
  function with_sep(dir) result(p)
    character(len=*), intent(in) :: dir
    character(len=:), allocatable :: p
    if (len(dir) > 0) then
      if (dir(len(dir):len(dir)) == '\' .or. dir(len(dir):len(dir)) == '/') then
        p = dir
        return
      end if
    end if
    p = trim(dir) // '\'
  end function with_sep

  ! Создание каталогов. В стандартном Фортране создания каталога нет, поэтому
  ! зовём mkdir (Windows-специфично, как json_list_files); сообщения и код
  ! возврата не важны -- ошибку поймает запись файла в этот каталог.
  subroutine make_dirs(dir)
    character(len=*), intent(in) :: dir
    character(len=512) :: cmd
    write(cmd, '(a,a,a)') 'mkdir "', trim(dir), '" >nul 2>nul'
    call execute_command_line(trim(cmd))
  end subroutine make_dirs

  function doc_save_sample(out_dir, name, sections, o) result(res_dir)
    character(len=*), intent(in) :: out_dir, name
    type(section_model), intent(in) :: sections(:)
    type(sample_options), intent(in) :: o
    character(len=:), allocatable :: res_dir
    type(doc_writer) :: w
    type(pappa_options) :: opt
    integer(ip), allocatable :: ord(:)
    character(len=64) :: buf
    character(len=:), allocatable :: base, fname, secpath, cleaner_txt, created
    character(len=:), allocatable :: desc_txt, csv_txt
    integer(ip) :: i, j, k, idx

    base = with_sep(out_dir)
    call make_dirs(base // 'sections')

    ! Порядок документов -- по возрастанию section_id (сортируем индексы,
    ! чтобы не копировать модели целиком).
    allocate(ord(size(sections)))
    do i = 1, size(ord)
      ord(i) = i
    end do
    do i = 2, size(ord)
      k = i - 1
      do while (k >= 1)
        if (sections(ord(k))%section_id <= sections(ord(k + 1))%section_id) exit
        j = ord(k)
        ord(k) = ord(k + 1)
        ord(k + 1) = j
        k = k - 1
      end do
    end do

    opt = pappa_options()
    if (size(sections) > 0) opt = sections(ord(1))%model%options
    desc_txt = ''
    csv_txt = ''
    if (allocated(o%description)) desc_txt = o%description
    if (allocated(o%input_csv)) csv_txt = o%input_csv
    created = doc_iso_utc_now()
    cleaner_txt = '{"mode": "auto", "auto": {"method": "iqr", "baseline_deg": ' // &
      json_num_text(o%cleaner%baseline_deg) // ', "iqr_k": ' // &
      json_num_text(o%cleaner%iqr_k) // '}}'

    call dw_reset(w)
    call dw_obj_start(w)
    call dw_kv_str(w, 'format', 'pappa-sample'); call dw_comma(w)
    call dw_kv_str(w, 'version', '1.0');         call dw_comma(w)
    call dw_kv_str(w, 'name', name);             call dw_comma(w)
    call dw_kv_str(w, 'created', created);       call dw_comma(w)

    call dw_key(w, 'units')
    call dw_obj_start(w)
    call dw_kv_str(w, 'angle', 'degree'); call dw_comma(w)
    call dw_kv_str(w, 'length', 'mm')
    call dw_obj_end(w)
    call dw_comma(w)

    call dw_key(w, 'meta')
    call dw_obj_start(w)
    call dw_kv_str(w, 'description', desc_txt)
    call dw_obj_end(w)
    call dw_comma(w)

    if (len(csv_txt) > 0) then
      call dw_key(w, 'input')
      call dw_obj_start(w)
      call dw_kv_str(w, 'csv', csv_txt)
      call dw_obj_end(w)
      call dw_comma(w)
    end if

    call dw_key(w, 'config')
    call dw_obj_start(w)
    call dw_kv_int(w, 'n_patches', opt%n_patches);         call dw_comma(w)
    call dw_kv_num(w, 'phase_deg', opt%phase_deg);         call dw_comma(w)
    call dw_kv_int(w, 'deg_min', opt%deg_min);             call dw_comma(w)
    call dw_kv_int(w, 'deg_max', opt%deg_max);             call dw_comma(w)
    call dw_kv_num(w, 'overlap_train', opt%overlap_train); call dw_comma(w)
    call dw_kv_num(w, 'overlap_use', opt%overlap_use);     call dw_comma(w)
    call dw_kv_num(w, 'deg_elbow_tol', opt%deg_elbow_tol); call dw_comma(w)
    call dw_kv_raw(w, 'cleaner', cleaner_txt);             call dw_comma(w)
    call dw_kv_bool(w, 'pits', o%pits)
    if (o%pits .and. size(sections) > 0) then
      call dw_comma(w)
      call dw_kv_num(w, 'sigma_deg', sections(ord(1))%model%pit_shape%sigma_deg)
      call dw_comma(w)
      call dw_kv_num(w, 'pit_core_sigma', sections(ord(1))%model%pit_shape%core_sigma)
      call dw_comma(w)
      call dw_kv_num(w, 'pit_window_sigma', sections(ord(1))%model%pit_shape%window_sigma)
      call dw_comma(w)
      call dw_kv_num(w, 'pit_min_amp', sections(ord(1))%model%pit_shape%pit_min_amp)
      call dw_comma(w)
      call dw_kv_bool(w, 'tapering', sections(ord(1))%model%pit_shape%tapering)
    end if
    call dw_comma(w)
    call dw_key(w, 'detector')
    call dw_raw(w, 'null')
    call dw_obj_end(w)
    call dw_comma(w)

    call dw_key(w, 'sections')
    call dw_arr_start(w)
    do i = 1, size(ord)
      idx = ord(i)
      write(buf, '(a,i2.2,a)') 'sections/', i - 1, '.pappa.json'
      fname = trim(buf)
      secpath = base // fname
      secpath = doc_save_section(secpath, sections(idx))
      call dw_next(w, i == 1)
      call dw_obj_start(w)
      call dw_kv_int(w, 'index', i - 1);                            call dw_comma(w)
      call dw_kv_int(w, 'section_id', sections(idx)%section_id);    call dw_comma(w)
      call dw_kv_num(w, 'height_mm', sections(idx)%height_mm);      call dw_comma(w)
      call dw_kv_str(w, 'file', fname);                             call dw_comma(w)
      call dw_kv_int(w, 'n_points', sections(idx)%n_points_total);  call dw_comma(w)
      call dw_kv_int(w, 'n_outliers', sections(idx)%n_outliers)
      call dw_obj_end(w)
    end do
    if (size(ord) > 0) call dw_raw(w, NL // dw_ind(w))
    call dw_arr_end(w)

    call dw_obj_end(w)
    call json_write_text(base // 'sample.json', tb_text(w%b) // NL)
    res_dir = out_dir
  end function doc_save_sample

end module pappa_document
