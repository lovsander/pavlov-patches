! Тест JSON-модуля порта: числа, экранирование, дерево, рендер, разбор, рост
! арены, побайтный round-trip документов Octave-порта и обход всех папок samples.
!
!   test_json.exe <корень-репозитория>
!
! Корень передаётся аргументом, чтобы тест не зависел от текущего каталога.
! Часть проверок работает с образцами (samples/ не коммитится), поэтому при их
! отсутствии она пропускается -- остальные проверки обязаны пройти всегда.
program test_json
  use pappa_kinds, only: dp, ip
  use pappa_json
  implicit none
  integer(ip) :: nbad = 0
  type(json_doc) :: doc
  integer(ip) :: root, meta, pits, arr, c, k, n
  character(len=400) :: repo
  character(len=500) :: pbuf
  character(len=:), allocatable :: txt, out
  logical :: have_samples

  call get_command_argument(1, repo)
  if (len_trim(repo) == 0) repo = '.'
  n = len_trim(repo)
  do while (n > 0)
    if (repo(n:n) /= '\' .and. repo(n:n) /= '/') exit
    n = n - 1
  end do
  repo = repo(1:n)
  write(*, '(a)') 'repo: '//trim(repo)

  call test_numbers
  call test_esc
  call test_tree
  call test_parse_access
  call test_arena_growth

  ! --- round-trip эталонных документов Octave-порта (побайтно) --------------
  inquire(file=trim(repo)//'\samples\synthetic_sphere_octave\sample.json', &
          exist=have_samples)
  if (.not. have_samples) then
    write(*, '(a)') 'samples/synthetic_sphere_octave нет: round-trip пропущен'
  else
    do k = 0, 9
      write(pbuf, '(a,i2.2,a)') &
        trim(repo)//'\samples\synthetic_sphere_octave\sections\', k, '.pappa.json'
      call rt_file(trim(pbuf))
    end do
    ! Отчёт пишет внешний скрипт (не JSON-писатель порта): он печатает целые как
    ! "0.0", порт -- как "0". Поэтому от отчёта требуем не побайтного совпадения,
    ! а корректного разбора, значений полей и УСТОЙЧИВОСТИ разбор<->рендер.
    call test_report_doc(trim(repo)// &
                         '\samples\synthetic_sphere_octave\report\verify.json')
    call test_sample_doc(trim(repo)// &
                         '\samples\synthetic_sphere_octave\sample.json')
    call scan_all_samples
  end if

  if (nbad /= 0) then
    write(*, '(a,i0)') 'FAILED: ', nbad
    stop 1
  end if
  write(*, '(a)') 'ALL OK'
contains

  subroutine eq_str(got, want, what)
    character(len=*), intent(in) :: got, want, what
    if (got /= want) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL '//what
      write(*, '(a)') '  got : ['//got//']'
      write(*, '(a)') '  want: ['//want//']'
    end if
  end subroutine eq_str

  subroutine eq_num(v, want)
    real(dp), intent(in) :: v
    character(len=*), intent(in) :: want
    character(len=40) :: buf
    write(buf, '(es28.17)') v
    call eq_str(json_num_text(v), want, 'num '//trim(buf))
  end subroutine eq_num

  ! Хвост строки: нужен там, где полный путь зависит от машины (путь к CSV
  ! внутри sample.json записан абсолютным).
  ! Разделитель пути в манифестах зависит от ОС: питон-пайплайн на Windows пишет
  ! '\', на Linux — '/'. Сверка хвоста нормализует разделители, иначе проверка
  ! образца была бы Windows-only (а сам тест — красным на любой POSIX-машине).
  pure function path_norm(s) result(r)
    character(len=*), intent(in) :: s
    character(len=len(s)) :: r
    integer :: k
    r = s
    do k = 1, len_trim(r)
      if (r(k:k) == achar(92_1)) r(k:k) = '/'
    end do
  end function path_norm

  subroutine check_suffix(got, tail, what)
    character(len=*), intent(in) :: got, tail, what
    character(len=len(got)) :: g
    character(len=len(tail)) :: t
    integer :: ng, nt
    g = path_norm(got)
    t = path_norm(tail)
    ng = len_trim(g)
    nt = len_trim(t)
    if (ng < nt) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL '//what//': короткая строка ['//trim(g)//']'
    else if (g(ng - nt + 1:ng) /= trim(t)) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL '//what//': ['//trim(g)//'] не кончается на ['//trim(t)//']'
    end if
  end subroutine check_suffix

  subroutine test_numbers
    call eq_num(0.0_dp, '0')
    call eq_num(-0.0_dp, '0')
    call eq_num(1.0_dp, '1')
    call eq_num(-1.0_dp, '-1')
    call eq_num(7.0_dp, '7')
    call eq_num(0.5_dp, '0.5')
    call eq_num(0.1_dp, '0.1')
    call eq_num(2.5_dp, '2.5')
    call eq_num(180.0_dp, '180')
    call eq_num(1.0e14_dp, '100000000000000')
    call eq_num(1.0e15_dp, '1e+15')
    call eq_num(1.0e20_dp, '1e+20')
    call eq_num(1.0e-5_dp, '1e-05')
    call eq_num(1.2345e-7_dp, '1.2345e-07')
    call eq_num(0.000123_dp, '0.000123')
    call eq_num(123456.789_dp, '123456.789')
    call eq_num(-25.714285714285715_dp, '-25.714285714285715')
  end subroutine test_numbers

  subroutine test_esc
    call eq_str(json_esc('a"b\c'//achar(10)//achar(9)//achar(7)), &
                'a\"b\\c\n\t\u0007', 'esc')
    call eq_str(json_esc('Русский текст'), 'Русский текст', 'esc utf8')
  end subroutine test_esc

  subroutine test_tree
    doc = jd_create()
    root = jd_obj(doc)
    call jobj_add_str(doc, root, 'format', 'pappa')
    call jobj_add_int(doc, root, 'version', 2)
    call jobj_add_num(doc, root, 'half_sector_deg', 25.714285714285715_dp)
    call jobj_add_numv(doc, root, 'centers_deg', [90.3_dp, 200.25_dp])
    pits = jobj_add_obj(doc, root, 'pit')
    call jobj_add_bool(doc, pits, 'on', .true.)
    call jobj_add_null(doc, pits, 'none')
    call jobj_add_numv(doc, pits, 'vec', [1.0_dp, 2.0_dp])
    out = '{'//achar(10)// &
          '  "format": "pappa",'//achar(10)// &
          '  "version": 2,'//achar(10)// &
          '  "half_sector_deg": 25.714285714285715,'//achar(10)// &
          '  "centers_deg": ['//achar(10)// &
          '    90.3, 200.25'//achar(10)// &
          '  ],'//achar(10)// &
          '  "pit": {'//achar(10)// &
          '    "on": true,'//achar(10)// &
          '    "none": null,'//achar(10)// &
          '    "vec": ['//achar(10)// &
          '      1, 2'//achar(10)// &
          '    ]'//achar(10)// &
          '  }'//achar(10)// &
          '}'
    call eq_str(json_render(doc), out, 'render tree')
    ! массив из чисел, собранный поэлементно, -- каждый на своей строке
    doc = jd_create()
    root = jd_obj(doc)
    arr = jobj_add_arr(doc, root, 'x')
    call jarr_add_num(doc, arr, 1.0_dp)
    call jarr_add_num(doc, arr, 2.0_dp)
    call eq_str(json_render(doc), '{'//achar(10)//'  "x": ['//achar(10)// &
                '    1,'//achar(10)//'    2'//achar(10)//'  ]'//achar(10)//'}', &
                'render arr of nums')
    ! пустые контейнеры
    doc = jd_create()
    root = jd_obj(doc)
    c = jobj_add_obj(doc, root, 'o')
    arr = jobj_add_arr(doc, root, 'a')
    call eq_str(json_render(doc), '{'//achar(10)//'  "o": {},'//achar(10)// &
                '  "a": []'//achar(10)//'}', 'render empty')
  end subroutine test_tree

  subroutine test_parse_access
    character(len=200) :: in
    in = '{"a": {"b": [1, 2, 3], "c": "text"}, "d": [{"e": 5}, {"e": 6}],'// &
         ' "g": [[1, 2], [3, 4, 5]]}'
    doc = json_parse(trim(in))
    root = doc%root
    call eq_str(jtext(doc, root, 'nope', 'def'), 'def', 'missing key')
    call eq_str(jtext(doc, root, 'd', 'def'), 'def', 'wrong type')
    meta = jfind(doc, root, 'a')
    if (meta == 0) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL find a'
      return
    end if
    call eq_str(jtext(doc, meta, 'c', ''), 'text', 'nested text')
    if (.not. jhas(doc, meta, 'b')) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL has b'
    end if
    if (jisnull(doc, meta, 'b') .or. .not. jisnull(doc, root, 'zz')) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL isnull'
    end if
    arr = jfind(doc, meta, 'b')
    if (jkind(doc, arr) /= JK_NUMV) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL numv kind'
    end if
    block
      real(dp), allocatable :: v(:)
      v = jnums(doc, meta, 'b')
      if (size(v) /= 3 .or. abs(v(3) - 3.0_dp) > 0.0_dp) then
        nbad = nbad + 1
        write(*, '(a)') 'FAIL jnums'
      end if
      arr = jfind(doc, root, 'd')
      if (jlen(doc, arr) /= 2) then
        nbad = nbad + 1
        write(*, '(a)') 'FAIL jlen'
      end if
      if (jnode_int(doc, jfind(doc, jel(doc, arr, 2), 'e'), 0) /= 6) then
        nbad = nbad + 1
        write(*, '(a)') 'FAIL jel int'
      end if
      block
        real(dp), allocatable :: z(:)
        z = jitem_nums(doc, jfind(doc, root, 'g'), 2)
        if (size(z) /= 3 .or. abs(z(3) - 5.0_dp) > 0.0_dp) then
          nbad = nbad + 1
          write(*, '(a)') 'FAIL item nums'
        end if
      end block
      if (jel(doc, root, 1) /= 0) then
        nbad = nbad + 1
        write(*, '(a)') 'FAIL jel on object'
      end if
      if (jlen(doc, root) /= 3) then
        nbad = nbad + 1
        write(*, '(a)') 'FAIL jlen object'
      end if
      if (jnode_num(doc, root, 3.0_dp) /= 3.0_dp) then
        nbad = nbad + 1
        write(*, '(a)') 'FAIL jnode_num default'
      end if
      if (jnode_bool(doc, root, .true.) .neqv. .true.) then
        nbad = nbad + 1
        write(*, '(a)') 'FAIL jnode_bool default'
      end if
    end block
  end subroutine test_parse_access

  ! Арена: много узлов -> рост пула, обход по индексам, целостность значений.
  subroutine test_arena_growth
    integer(ip) :: n, i, k, t
    real(dp) :: s
    character(len=16) :: buf
    doc = jd_create()
    root = jd_obj(doc)
    arr = jobj_add_arr(doc, root, 'items')
    n = 4000
    do i = 1, n
      t = jarr_add_obj(doc, arr)
      call jobj_add_int(doc, t, 'i', i)
      call jobj_add_str(doc, t, 's', 'x')
    end do
    if (jd_count(doc) <= n) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL arena size'
    end if
    s = 0.0_dp
    do i = 1, n
      t = jel(doc, arr, i)
      s = s + real(jnode_int(doc, jfind(doc, t, 'i'), 0), dp)
    end do
    if (abs(s - real(n * (n + 1) / 2, dp)) > 0.0_dp) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL arena walk'
    end if
    if (jkind(doc, root) /= JK_OBJ .or. jkind(doc, 0) /= JK_NULL) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL arena kinds'
    end if
    k = jfind(doc, root, 'items')
    if (k /= arr) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL arena find'
    end if
    write(buf, '(i0)') jd_count(doc)
    write(*, '(a)') 'arena nodes: '//trim(buf)
  end subroutine test_arena_growth

  ! Разбор -> рендер обязан дать БАЙТ В БАЙТ исходный текст (файлы Octave-порта).
  subroutine rt_file(path)
    character(len=*), intent(in) :: path
    integer(ip) :: i, n
    txt = json_read_text(path)
    doc = json_parse(txt)
    out = json_render(doc)
    if (txt == out) then
      write(*, '(a)') 'RT ok (точно)  '//path
      return
    end if
    if (len(txt) == len(out) + 1) then
      if (txt == out//achar(10)) then
        write(*, '(a)') 'RT ok (хвостовой LF) '//path
        return
      end if
    end if
    nbad = nbad + 1
    write(*, '(a)') 'FAIL roundtrip '//path
    write(*, '(a,i0,a,i0)') '  len(txt)=', len(txt), ' len(out)=', len(out)
    n = min(len(txt), len(out))
    do i = 1, n
      if (txt(i:i) /= out(i:i)) then
        write(*, '(a,i0)') '  first difference at ', i
        write(*, '(a)') '  txt: ['// &
          txt(max(1, i - 40):min(len(txt), i + 20))//']'
        write(*, '(a)') '  out: ['// &
          out(max(1, i - 40):min(len(out), i + 20))//']'
        exit
      end if
    end do
    if (i > n) write(*, '(a)') '  префикс совпал, различие в длине/хвосте'
  end subroutine rt_file

  function strip_cr(s) result(t)
    character(len=*), intent(in) :: s
    character(len=:), allocatable :: t
    integer(ip) :: i, n
    allocate(character(len=len(s)) :: t)
    n = 0
    do i = 1, len(s)
      if (iachar(s(i:i)) /= 13) then
        n = n + 1
        t(n:n) = s(i:i)
      end if
    end do
    t = t(1:n)
  end function strip_cr

  ! sample.json разбором->рендером побайтно не воспроизвести: эталон Octave
  ! вставляет компактные объекты ("cleaner", "detector") обёрткой json_raw,
  ! то есть КАК ТЕКСТ, а разбор честно строит по ним дерево (в остальных
  ! портах -- ровно так же). Поэтому здесь только чтение полей.
  ! `created` — время прогона, а образцы перегенерируются (`verify_all.ps1 -Full`,
  ! `build_fortran.ps1 -Pipeline`), поэтому проверяется ФОРМАТ метки времени
  ! (ISO-8601 UTC «ГГГГ-ММ-ДДTЧЧ:ММ:ССZ»), а не само значение.
  function iso_utc_ok(s) result(ok)
    character(len=*), intent(in) :: s
    logical :: ok
    character(len=*), parameter :: pat = '9999-99-99T99:99:99Z'
    integer(ip) :: i
    ok = (len_trim(s) == len(pat))
    if (.not. ok) return
    do i = 1, len(pat)
      if (pat(i:i) == '9') then
        if (s(i:i) < '0' .or. s(i:i) > '9') then
          ok = .false.
          return
        end if
      else if (s(i:i) /= pat(i:i)) then
        ok = .false.
        return
      end if
    end do
  end function iso_utc_ok

  subroutine test_sample_doc(path)
    character(len=*), intent(in) :: path
    integer(ip) :: cfg, secs
    txt = json_read_text(path)
    doc = json_parse(txt)
    root = doc%root
    call eq_str(jtext(doc, root, 'format', ''), 'pappa-sample', 'sample format')
    call eq_str(jtext(doc, root, 'name', ''), 'synthetic_sphere', 'sample name')
    if (.not. iso_utc_ok(jtext(doc, root, 'created', ''))) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL sample created: ожидается «ГГГГ-ММ-ДДTЧЧ:ММ:ССZ», '// &
        'получено ['//trim(jtext(doc, root, 'created', ''))//']'
    end if
    meta = jfind(doc, root, 'meta')
    call eq_str(jtext(doc, meta, 'description', ''), 'PAPPA Octave port', &
                'sample description')
    call eq_str(jtext(doc, jfind(doc, root, 'units'), 'length', ''), 'mm', &
                'sample units')
    ! Путь к CSV в образце записан абсолютным (так его пишет питон-пайплайн),
    ! поэтому сверяем хвост пути: имя файла и каталог python/.
    call check_suffix(jtext(doc, jfind(doc, root, 'input'), 'csv', ''), &
                      'python\synthetic_data.csv', 'sample input csv')
    cfg = jfind(doc, root, 'config')
    if (jint(doc, cfg, 'n_patches', 0) /= 7) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL sample n_patches'
    end if
    if (abs(jnum(doc, cfg, 'phase_deg', 0.0_dp) - 24.75_dp) > 0.0_dp) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL sample phase_deg'
    end if
    if (jnum(doc, cfg, 'deg_elbow_tol', 0.0_dp) /= 0.05_dp) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL sample deg_elbow_tol'
    end if
    if (.not. jnode_bool(doc, jfind(doc, cfg, 'pits'), .false.)) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL sample pits'
    end if
    if (.not. jisnull(doc, cfg, 'detector')) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL sample detector null'
    end if
    secs = jfind(doc, root, 'sections')
    if (jlen(doc, secs) /= 10) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL sample sections'
    end if
    meta = jel(doc, secs, 6)
    call eq_str(jtext(doc, meta, 'file', ''), 'sections/05.pappa.json', &
                'sample section file')
    if (jint(doc, meta, 'n_points', 0) /= 6000) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL sample n_points'
    end if
    write(*, '(a)') 'sample.json прочитан'
  end subroutine test_sample_doc

  subroutine test_report_doc(path)
    character(len=*), intent(in) :: path
    character(len=:), allocatable :: norm, out2
    integer(ip) :: sm, secs, one
    norm = strip_cr(json_read_text(path))
    doc = json_parse(norm)
    out = json_render(doc)
    doc = json_parse(out)
    out2 = json_render(doc)
    if (out2 /= out) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL report render unstable'
    end if
    root = doc%root
    call eq_str(jtext(doc, root, 'check', ''), 'verify_port', 'report check')
    if (jnum(doc, root, 'tol_mm', 0.0_dp) /= 1.0e-6_dp) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL report tol_mm'
    end if
    if (jint(doc, root, 'grid_points', 0) /= 6000) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL report grid_points'
    end if
    sm = jfind(doc, root, 'summary')
    if (abs(jnum(doc, sm, 'max_delta', 0.0_dp) - 1.3429257705865894e-12_dp) &
        > 0.0_dp) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL report max_delta'
    end if
    if (jint(doc, sm, 'worst_section', -1) /= 5) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL report worst_section'
    end if
    if (jint(doc, sm, 'n_ok', 0) /= 10 .or. jint(doc, sm, 'n_total', 0) /= 10) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL report n_ok'
    end if
    call eq_str(jtext(doc, sm, 'verdict', ''), &
                'порт воспроизводит референс в пределах допуска', &
                'report verdict (utf8)')
    secs = jfind(doc, root, 'sections')
    if (jlen(doc, secs) /= 10) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL report sections'
    end if
    one = jel(doc, secs, 6)
    if (jint(doc, one, 'section_id', -1) /= 5) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL report section_id'
    end if
    if (abs(jnum(doc, one, 'rmse_py', 0.0_dp) - &
            0.012565267605545617_dp) > 0.0_dp) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL report rmse_py'
    end if
    if (.not. jnode_bool(doc, jfind(doc, one, 'ok'), .false.)) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL report ok flag'
    end if
    write(*, '(a)') 'report/verify.json прочитан и устойчив'
  end subroutine test_report_doc

  ! Обход всех папок образцов (все порты репозитория): разбор обязан пройти без
  ! ошибок, а разбор<->рендер -- быть устойчивым. Побайтной сверки здесь нет: у
  ! портов свои форматы чисел, эталон побайтности -- папка Octave.
  subroutine scan_all_samples
    character(len=JP_PATH_LEN), allocatable :: dirs(:), files(:)
    character(len=500) :: p, base
    character(len=16) :: subs(2)
    integer(ip) :: i, j, s, nfiles
    logical :: ex
    base = trim(repo)//'\samples'
    subs(1) = 'sections'
    subs(2) = 'report'
    nfiles = 0
    inquire(file=trim(base)//'\synthetic_sphere_octave\sample.json', exist=ex)
    if (.not. ex) then
      write(*, '(a)') 'samples/ пуст (образцы не собраны): обход пропущен'
      return
    end if
    call json_list_files(base, '*', dirs)
    if (size(dirs) == 0) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL json_list_files: пустой список папок'
      return
    end if
    do i = 1, size(dirs)
      do s = 1, 2
        call json_list_files(trim(base)//'\'//trim(dirs(i))//'\'//trim(subs(s)), &
                             '*.json', files)
        do j = 1, size(files)
          p = trim(base)//'\'//trim(dirs(i))//'\'//trim(subs(s))//'\'// &
              trim(files(j))
          call check_stable(trim(p))
          nfiles = nfiles + 1
        end do
      end do
      p = trim(base)//'\'//trim(dirs(i))//'\sample.json'
      inquire(file=trim(p), exist=ex)
      if (ex) then
        call check_stable(trim(p))
        nfiles = nfiles + 1
      end if
    end do
    write(pbuf, '(a,i0,a,i0,a)') 'папок: ', size(dirs), ', документов: ', &
      nfiles, ' -- разбор и устойчивость проверены'
    write(*, '(a)') trim(pbuf)
  end subroutine scan_all_samples

  ! Разбор -> рендер -> разбор -> рендер: второй рендер обязан совпасть с первым
  ! (устойчивость), и обе половины не должны падать.
  subroutine check_stable(path)
    character(len=*), intent(in) :: path
    character(len=:), allocatable :: r1, r2
    txt = json_read_text(path)
    doc = json_parse(txt)
    r1 = json_render(doc)
    doc = json_parse(r1)
    r2 = json_render(doc)
    if (r1 /= r2) then
      nbad = nbad + 1
      write(*, '(a)') 'FAIL unstable '//path
    end if
  end subroutine check_stable

end program test_json
