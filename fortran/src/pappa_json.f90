! PAPPA Fortran port -- JSON: собственный парсер, рендерер и формат чисел.
! Внешних библиотек нет намеренно: у порта не должно быть зависимостей, кроме
! рантайма (то же правило, что у остальных портов репозитория).
!
! ЛОВУШКИ, найденные пробными компиляциями TDM-GCC 10.3.0 (все -- на живых
! примерах, см. fortran/README.md):
!   * ГЛАВНАЯ ЛОВУШКА: РЕКУРСИВНЫЙ производный тип (узел, содержащий массив
!     узлов) в этом компиляторе ломает кучу: глубокое копирование в элементы
!     массива и освобождение вложенных аллокатов падали с 0xC0000374 (пробы
!     mini_rec/mini_rec3). Поэтому дерево JSON хранится ПЛОСКО: узлы лежат в
!     одной арене (json_doc%pool), а связи -- ЦЕЛЫЕ ИНДЕКСЫ в пул. Глубоких
!     копий и рекурсивных аллокатов нет; рекурсия есть только в ВЫЗОВАХ
!     обхода (рендер/разбор), где она безопасна.
!   * Ёмкость пула ведём СВОИМ счётчиком (json_doc%cap), а не size(): опора на
!     size() нераспределённого компонента после move_alloc при -O2 оказалась
!     ненадёжной -- проба mini_arena2 «залипала» на нуле.
!   * ФОРМАТНЫЙ write на Windows печатает CRLF, поэтому JSON пишется ТОЛЬКО
!     через access='stream', form='unformatted' (json_write_text) -- переводы
!     строк остаются LF, и файлы совпадают с остальными портами побайтно;
!   * nint() округляет половину ОТ нуля, а режим 'int' в остальных портах
!     округляет К ЧЁТНОМУ -- здесь для этого sig_round_even;
!   * es0.d (нулевая ширина поля) в gfortran 10.3 печатает 18 значащих цифр
!     независимо от d, поэтому мантисса берётся с ЯВНОЙ шириной (es40.d e3);
!   * внутренняя запись в строку с ОТЛОЖЕННОЙ длиной не распределяет её
!     («End of record»), поэтому все внутренние записи идут в буферы
!     фиксированной длины.
module pappa_json
  use pappa_kinds, only: dp, ip, lp
  use pappa_signal, only: sig_round_even
  implicit none
  private

  integer(ip), parameter :: TB_CHUNK = 512       ! размер куска текстового буфера
  integer(ip), parameter :: JNAME_LEN = 64       ! предел длины имени поля
  integer(ip), parameter :: JP_PATH_LEN = 260    ! предел длины пути/имени файла

  ! Коды символов берём константами: в case(...) допустимо только константное
  ! выражение, а achar() в метке варианта выглядит слишком хрупко.
  character(len=1), parameter :: CH_DQ = achar(34)   ! двойная кавычка
  character(len=1), parameter :: CH_BS = achar(92)   ! обратный слэш
  character(len=1), parameter :: CH_NL = achar(10)   ! перевод строки (LF)
  character(len=1), parameter :: CH_CR = achar(13)   ! CR (в файлах Windows)

  ! Те же символы кодами: в json_esc выбор идёт по КОДУ (целому), и метки
  ! вариантов обязаны быть целыми -- ловушка, поймана компилятором.
  integer(ip), parameter :: CODE_DQ = 34, CODE_BS = 92

  integer(ip), parameter :: JK_NULL = 0, JK_BOOL = 1, JK_NUM = 2, JK_NUMV = 3
  integer(ip), parameter :: JK_TEXT = 4, JK_RAW = 5, JK_ARR = 6, JK_OBJ = 7

  ! Узел JSON в плоской арене. Детей узел держит ИНДЕКСАМИ в пул: у объекта
  ! это значения полей (kids) вместе с именами (kname), у массива -- элементы.
  ! Полей типа json_node здесь нет намеренно (см. ловушку рекурсивного типа).
  type :: json_node
    integer(ip) :: kind = JK_NULL
    logical :: bval = .false.
    real(dp) :: nval = 0.0_dp
    real(dp), allocatable :: nvec(:)                   ! JK_NUMV
    character(len=:), allocatable :: text              ! JK_TEXT / JK_RAW
    integer(ip), allocatable :: kids(:)                ! индексы детей в пуле
    character(len=JNAME_LEN), allocatable :: kname(:)  ! имена детей (объект)
  end type json_node

  ! Арена документа: все узлы в одном массиве, связи -- индексы.
  ! root -- первый созданный узел (корень документа).
  type :: json_doc
    type(json_node), allocatable :: pool(:)
    integer(ip) :: n = 0
    integer(ip) :: cap = 0
    integer(ip) :: root = 0
  end type json_doc

  ! Текстовый буфер: список кусков (копирование всей строки на каждое
  ! добавление сделало бы рендер квадратичным).
  type :: text_buf
    character(len=TB_CHUNK), allocatable :: parts(:)
    integer(ip), allocatable :: used(:)
    integer(ip) :: n = 0
    integer(ip) :: cap = 0
  end type text_buf

  public :: JK_NULL, JK_BOOL, JK_NUM, JK_NUMV, JK_TEXT, JK_RAW, JK_ARR, JK_OBJ
  public :: JP_PATH_LEN, JNAME_LEN, json_node, json_doc, text_buf
  public :: jd_create, jd_new, jd_count, nkids, jkid, jkind
  public :: jd_null, jd_bool, jd_num, jd_int, jd_str, jd_raw, jd_numv
  public :: jd_obj, jd_arr
  public :: jobj_add, jobj_add_num, jobj_add_int, jobj_add_str, jobj_add_raw
  public :: jobj_add_bool, jobj_add_null, jobj_add_numv
  public :: jobj_add_obj, jobj_add_arr
  public :: jarr_add, jarr_add_num, jarr_add_int, jarr_add_str, jarr_add_raw
  public :: jarr_add_bool, jarr_add_null, jarr_add_numv
  public :: jarr_add_obj, jarr_add_arr
  public :: jfind, jhas, jisnull, jlen, jel
  public :: jnode_num, jnode_int, jnode_text, jnode_bool, jnode_nums
  public :: jnum, jint, jtext, jbool, jnums, jitem_nums
  public :: tb_init, tb_add, tb_text
  public :: json_num_text, json_esc, json_render, json_render_node
  public :: json_read_text, json_write_text, json_parse, json_list_files

contains

  !------------------------------- арена -----------------------------------

  function jd_create() result(doc)
    ! Пустой документ: пул не распределён, первое добавление его создаст.
    type(json_doc) :: doc
  end function jd_create

  subroutine jd_grow(doc)
    type(json_doc), intent(inout) :: doc
    type(json_node), allocatable :: tmp(:)
    integer(ip) :: i, grew
    if (doc%n < doc%cap) return
    grew = max(8_ip, 2 * doc%cap)
    allocate(tmp(grew))
    do i = 1, doc%n
      tmp(i) = doc%pool(i)
    end do
    call move_alloc(tmp, doc%pool)
    doc%cap = grew
  end subroutine jd_grow

  ! Добавить узел в арену, вернуть его индекс. Первый узел становится корнем.
  function jd_new(doc) result(k)
    type(json_doc), intent(inout) :: doc
    integer(ip) :: k
    call jd_grow(doc)
    doc%n = doc%n + 1
    k = doc%n
    doc%pool(k)%kind = JK_NULL
    doc%pool(k)%bval = .false.
    doc%pool(k)%nval = 0.0_dp
    if (allocated(doc%pool(k)%nvec)) deallocate(doc%pool(k)%nvec)
    if (allocated(doc%pool(k)%text)) deallocate(doc%pool(k)%text)
    if (allocated(doc%pool(k)%kids)) deallocate(doc%pool(k)%kids)
    if (allocated(doc%pool(k)%kname)) deallocate(doc%pool(k)%kname)
    if (doc%root == 0) doc%root = k
  end function jd_new

  pure function jd_count(doc) result(n)
    type(json_doc), intent(in) :: doc
    integer(ip) :: n
    n = doc%n
  end function jd_count

  ! Число детей узла (0, если узел не контейнер или индекс вне арены).
  pure function nkids(doc, node) result(n)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    integer(ip) :: n
    n = 0
    if (node < 1 .or. node > doc%n) return
    if (allocated(doc%pool(node)%kids)) n = int(size(doc%pool(node)%kids), ip)
  end function nkids

  ! Индекс k-го ребёнка узла (0 -- вне диапазона).
  pure function jkid(doc, node, k) result(c)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    integer(ip), intent(in) :: k
    integer(ip) :: c
    c = 0
    if (k >= 1 .and. k <= nkids(doc, node)) c = doc%pool(node)%kids(k)
  end function jkid

  ! Вид узла по индексу (JK_NULL, если индекс вне арены).
  pure function jkind(doc, node) result(k)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    integer(ip) :: k
    k = JK_NULL
    if (node >= 1 .and. node <= doc%n) k = doc%pool(node)%kind
  end function jkind

  ! Дописать ребёнка в узел (объект или массив).
  subroutine jkid_push(doc, node, name, child)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    integer(ip), intent(in) :: child
    integer(ip), allocatable :: kd(:)
    character(len=JNAME_LEN), allocatable :: kn(:)
    integer(ip) :: n, i
    if (node < 1 .or. node > doc%n) error stop 'json: node index is out of range'
    if (child < 1 .or. child > doc%n) error stop 'json: child index is out of range'
    if (doc%pool(node)%kind /= JK_OBJ .and. doc%pool(node)%kind /= JK_ARR) &
      error stop 'json: only an object or an array can have children'
    if (len_trim(name) > JNAME_LEN) error stop 'json: field name is too long'
    n = nkids(doc, node)
    allocate(kd(n + 1), kn(n + 1))
    do i = 1, n
      kd(i) = doc%pool(node)%kids(i)
      kn(i) = doc%pool(node)%kname(i)
    end do
    kd(n + 1) = child
    kn(n + 1) = trim(name)
    call move_alloc(kd, doc%pool(node)%kids)
    call move_alloc(kn, doc%pool(node)%kname)
  end subroutine jkid_push

  subroutine jcheck_kind(doc, node, want, who)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    integer(ip), intent(in) :: want
    character(len=*), intent(in) :: who
    if (node < 1 .or. node > doc%n) error stop who//': node index is out of range'
    if (doc%pool(node)%kind /= want) error stop who//': wrong node kind'
  end subroutine jcheck_kind

  !--------------------------- узел: конструкторы ---------------------------

  function jd_null(doc) result(k)
    type(json_doc), intent(inout) :: doc
    integer(ip) :: k
    k = jd_new(doc)
    doc%pool(k)%kind = JK_NULL
  end function jd_null

  function jd_bool(doc, x) result(k)
    type(json_doc), intent(inout) :: doc
    logical, intent(in) :: x
    integer(ip) :: k
    k = jd_new(doc)
    doc%pool(k)%kind = JK_BOOL
    doc%pool(k)%bval = x
  end function jd_bool

  function jd_num(doc, x) result(k)
    type(json_doc), intent(inout) :: doc
    real(dp), intent(in) :: x
    integer(ip) :: k
    k = jd_new(doc)
    doc%pool(k)%kind = JK_NUM
    doc%pool(k)%nval = x
  end function jd_num

  ! Целое как JSON-число: 7 рендерится как 7 (не 7.0) -- как json_num в
  ! остальных портах, где printf('%.0f') для целых.
  function jd_int(doc, i) result(k)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: i
    integer(ip) :: k
    k = jd_num(doc, real(i, dp))
  end function jd_int

  ! Строка JSON (кавычки и экранирование добавит рендерер).
  function jd_str(doc, s) result(k)
    type(json_doc), intent(inout) :: doc
    character(len=*), intent(in) :: s
    integer(ip) :: k
    k = jd_new(doc)
    doc%pool(k)%kind = JK_TEXT
    doc%pool(k)%text = s
  end function jd_str

  ! Значение «вставить как есть» (готовая строка JSON).
  function jd_raw(doc, s) result(k)
    type(json_doc), intent(inout) :: doc
    character(len=*), intent(in) :: s
    integer(ip) :: k
    k = jd_new(doc)
    doc%pool(k)%kind = JK_RAW
    doc%pool(k)%text = s
  end function jd_raw

  function jd_numv(doc, x) result(k)
    type(json_doc), intent(inout) :: doc
    real(dp), intent(in) :: x(:)
    integer(ip) :: k
    real(dp), allocatable :: tmp(:)
    k = jd_new(doc)
    doc%pool(k)%kind = JK_NUMV
    allocate(tmp(size(x)))
    if (size(x) > 0) tmp = x
    call move_alloc(tmp, doc%pool(k)%nvec)
  end function jd_numv

  function jd_obj(doc) result(k)
    type(json_doc), intent(inout) :: doc
    integer(ip) :: k
    k = jd_new(doc)
    doc%pool(k)%kind = JK_OBJ
  end function jd_obj

  function jd_arr(doc) result(k)
    type(json_doc), intent(inout) :: doc
    integer(ip) :: k
    k = jd_new(doc)
    doc%pool(k)%kind = JK_ARR
  end function jd_arr

  !---------------------- узел: добавление полей/элементов ------------------

  subroutine jobj_add(doc, node, name, val)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    integer(ip), intent(in) :: val
    call jcheck_kind(doc, node, JK_OBJ, 'jobj_add')
    call jkid_push(doc, node, name, val)
  end subroutine jobj_add

  subroutine jobj_add_num(doc, node, name, x)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    real(dp), intent(in) :: x
    integer(ip) :: k
    k = jd_num(doc, x)
    call jobj_add(doc, node, name, k)
  end subroutine jobj_add_num

  subroutine jobj_add_int(doc, node, name, i)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    integer(ip), intent(in) :: i
    integer(ip) :: k
    k = jd_int(doc, i)
    call jobj_add(doc, node, name, k)
  end subroutine jobj_add_int

  subroutine jobj_add_str(doc, node, name, s)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    character(len=*), intent(in) :: s
    integer(ip) :: k
    k = jd_str(doc, s)
    call jobj_add(doc, node, name, k)
  end subroutine jobj_add_str

  subroutine jobj_add_raw(doc, node, name, s)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    character(len=*), intent(in) :: s
    integer(ip) :: k
    k = jd_raw(doc, s)
    call jobj_add(doc, node, name, k)
  end subroutine jobj_add_raw

  subroutine jobj_add_bool(doc, node, name, x)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    logical, intent(in) :: x
    integer(ip) :: k
    k = jd_bool(doc, x)
    call jobj_add(doc, node, name, k)
  end subroutine jobj_add_bool

  subroutine jobj_add_null(doc, node, name)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    integer(ip) :: k
    k = jd_null(doc)
    call jobj_add(doc, node, name, k)
  end subroutine jobj_add_null

  subroutine jobj_add_numv(doc, node, name, x)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    real(dp), intent(in) :: x(:)
    integer(ip) :: k
    k = jd_numv(doc, x)
    call jobj_add(doc, node, name, k)
  end subroutine jobj_add_numv

  ! Новый ПУСТОЙ объект/массив как поле; возвращается его индекс.
  function jobj_add_obj(doc, node, name) result(k)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    integer(ip) :: k
    k = jd_obj(doc)
    call jobj_add(doc, node, name, k)
  end function jobj_add_obj

  function jobj_add_arr(doc, node, name) result(k)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: name
    integer(ip) :: k
    k = jd_arr(doc)
    call jobj_add(doc, node, name, k)
  end function jobj_add_arr

  subroutine jarr_add(doc, node, val)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    integer(ip), intent(in) :: val
    call jcheck_kind(doc, node, JK_ARR, 'jarr_add')
    call jkid_push(doc, node, '', val)
  end subroutine jarr_add

  subroutine jarr_add_num(doc, node, x)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    real(dp), intent(in) :: x
    integer(ip) :: k
    k = jd_num(doc, x)
    call jarr_add(doc, node, k)
  end subroutine jarr_add_num

  subroutine jarr_add_int(doc, node, i)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    integer(ip), intent(in) :: i
    integer(ip) :: k
    k = jd_int(doc, i)
    call jarr_add(doc, node, k)
  end subroutine jarr_add_int

  subroutine jarr_add_str(doc, node, s)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: s
    integer(ip) :: k
    k = jd_str(doc, s)
    call jarr_add(doc, node, k)
  end subroutine jarr_add_str

  subroutine jarr_add_raw(doc, node, s)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: s
    integer(ip) :: k
    k = jd_raw(doc, s)
    call jarr_add(doc, node, k)
  end subroutine jarr_add_raw

  subroutine jarr_add_bool(doc, node, x)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    logical, intent(in) :: x
    integer(ip) :: k
    k = jd_bool(doc, x)
    call jarr_add(doc, node, k)
  end subroutine jarr_add_bool

  subroutine jarr_add_null(doc, node)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    integer(ip) :: k
    k = jd_null(doc)
    call jarr_add(doc, node, k)
  end subroutine jarr_add_null

  subroutine jarr_add_numv(doc, node, x)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    real(dp), intent(in) :: x(:)
    integer(ip) :: k
    k = jd_numv(doc, x)
    call jarr_add(doc, node, k)
  end subroutine jarr_add_numv

  ! Новый ПУСТОЙ объект/массив как элемент; возвращается его индекс.
  function jarr_add_obj(doc, node) result(k)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    integer(ip) :: k
    k = jd_obj(doc)
    call jarr_add(doc, node, k)
  end function jarr_add_obj

  function jarr_add_arr(doc, node) result(k)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    integer(ip) :: k
    k = jd_arr(doc)
    call jarr_add(doc, node, k)
  end function jarr_add_arr

  !------------------------------- узел: доступ -----------------------------

  ! Индекс значения поля объекта по имени (0 -- нет такого поля).
  function jfind(doc, node, key) result(k)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: key
    integer(ip) :: k, i, n
    k = 0
    if (jkind(doc, node) /= JK_OBJ) return
    n = nkids(doc, node)
    do i = 1, n
      if (trim(doc%pool(node)%kname(i)) == key) then
        k = doc%pool(node)%kids(i)
        return
      end if
    end do
  end function jfind

  function jhas(doc, node, key) result(tf)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: key
    logical :: tf
    tf = jfind(doc, node, key) > 0
  end function jhas

  ! Поле отсутствует или равно null (== isempty(json_val(...)) в selftest).
  function jisnull(doc, node, key) result(tf)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: key
    logical :: tf
    tf = jkind(doc, jfind(doc, node, key)) == JK_NULL
  end function jisnull

  ! Длина контейнера (-1 -- узел не массив и не объект).
  function jlen(doc, node) result(n)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    integer(ip) :: n
    if (jkind(doc, node) == JK_ARR .or. jkind(doc, node) == JK_OBJ) then
      n = nkids(doc, node)
    else
      n = -1
    end if
  end function jlen

  ! Индекс i-го элемента массива (0 -- узел не массив или индекс вне диапазона).
  function jel(doc, node, i) result(c)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    integer(ip), intent(in) :: i
    integer(ip) :: c
    c = 0
    if (jkind(doc, node) /= JK_ARR) return
    c = jkid(doc, node, i)
  end function jel

  ! Значения узла по индексу (для узлов, полученных через jfind/jel).
  function jnode_num(doc, node, def) result(x)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    real(dp), intent(in) :: def
    real(dp) :: x
    x = def
    if (jkind(doc, node) == JK_NUM) x = doc%pool(node)%nval
  end function jnode_num

  ! Целое из числа, округление К ЧЁТНОМУ (как round() в Python/Octave).
  function jnode_int(doc, node, def) result(i)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    integer(ip), intent(in) :: def
    integer(ip) :: i
    if (jkind(doc, node) == JK_NUM) then
      i = int(sig_round_even(doc%pool(node)%nval), ip)
    else
      i = def
    end if
  end function jnode_int

  function jnode_text(doc, node, def) result(s)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: def
    character(len=:), allocatable :: s
    if (jkind(doc, node) == JK_TEXT .or. jkind(doc, node) == JK_RAW) then
      s = doc%pool(node)%text
    else
      s = def
    end if
  end function jnode_text

  function jnode_bool(doc, node, def) result(tf)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    logical, intent(in) :: def
    logical :: tf
    tf = def
    if (jkind(doc, node) == JK_BOOL) tf = doc%pool(node)%bval
  end function jnode_bool

  ! Числа из узла-массива (числовой вектор JK_NUMV тоже принимается).
  subroutine jnode_nums(doc, node, v)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    real(dp), allocatable, intent(out) :: v(:)
    integer(ip) :: i, n, c
    select case (jkind(doc, node))
    case (JK_NUMV)
      allocate(v(size(doc%pool(node)%nvec)))
      if (size(v) > 0) v = doc%pool(node)%nvec
    case (JK_ARR)
      n = nkids(doc, node)
      allocate(v(n))
      do i = 1, n
        c = doc%pool(node)%kids(i)
        if (doc%pool(c)%kind /= JK_NUM) error stop 'json_nums: element is not a number'
        v(i) = doc%pool(c)%nval
      end do
    case default
      error stop 'json_nums: node is not an array'
    end select
  end subroutine jnode_nums

  ! Число из поля объекта.
  function jnum(doc, node, key, def) result(x)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: key
    real(dp), intent(in) :: def
    real(dp) :: x
    x = jnode_num(doc, jfind(doc, node, key), def)
  end function jnum

  ! Целое из поля объекта (округление к чётному).
  function jint(doc, node, key, def) result(i)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: key
    integer(ip), intent(in) :: def
    integer(ip) :: i, k
    k = jfind(doc, node, key)
    if (k > 0) then
      i = jnode_int(doc, k, def)
    else
      i = def
    end if
  end function jint

  function jtext(doc, node, key, def) result(s)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: key
    character(len=*), intent(in) :: def
    character(len=:), allocatable :: s
    s = jnode_text(doc, jfind(doc, node, key), def)
  end function jtext

  function jbool(doc, node, key, def) result(tf)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: key
    logical, intent(in) :: def
    logical :: tf
    tf = jnode_bool(doc, jfind(doc, node, key), def)
  end function jbool

  function jnums(doc, node, key) result(v)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=*), intent(in) :: key
    real(dp), allocatable :: v(:)
    integer(ip) :: k
    k = jfind(doc, node, key)
    if (k == 0) error stop 'json_nums: missing key'
    call jnode_nums(doc, k, v)
  end function jnums

  function jitem_nums(doc, node, i) result(v)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    integer(ip), intent(in) :: i
    real(dp), allocatable :: v(:)
    integer(ip) :: c
    c = jel(doc, node, i)
    if (c == 0) error stop 'json_nums: array index out of range'
    call jnode_nums(doc, c, v)
  end function jitem_nums

  !------------------------- текст числа, строки, рендер --------------------

  ! Кратчайшая запись числа в стиле C `%g` (так же, как json_num в остальных
  ! портах): целые по модулю меньше 1e15 -- без дробной части, иначе пробуем
  ! %.1g, %.2g, ..., %.17g и берём первую запись, которая читается обратно
  ! РОВНО в то же число; экспонента -- со знаком и минимум двумя цифрами.
  function json_num_text(v) result(s)
    real(dp), intent(in) :: v
    character(len=:), allocatable :: s
    integer(ip) :: p, ios
    integer(lp) :: iv
    real(dp) :: back
    character(len=32) :: buf
    character(len=:), allocatable :: cand
    if (.not. (v == v)) then          ! NaN: сравнение с собой ложно
      s = '0'
      return
    end if
    if (abs(v) > huge(v)) then        ! +-Inf: больше любого конечного
      s = '0'
      return
    end if
    if (v == 0.0_dp) then
      s = '0'
      return
    end if
    if (abs(v) < 1.0e15_dp) then
      iv = int(v, lp)                 ! усечение к нулю
      if (real(iv, dp) == v) then     ! число целое
        ! ЛОВУШКА: внутренняя запись в строку с ОТЛОЖЕННОЙ длиной не
        ! распределяет её (gfortran <= 12: «End of record»). Пишем в буфер.
        write(buf, '(i0)') iv
        s = trim(buf)
        return
      end if
    end if
    do p = 1, 17
      cand = num_g(v, p)
      read(cand, *, iostat=ios) back
      if (ios == 0) then
        if (back == v) then
          s = cand
          return
        end if
      end if
    end do
    s = num_g(v, 17)                  ! 17 цифр хватает всегда
  end function json_num_text

  ! Эмуляция C `%.*g` через мантиссу формата ES: gfortran даёт ПРАВИЛЬНО
  ! округлённые цифры, а раскладку (фиксированная или экспоненциальная) и
  ! вид экспоненты делаем сами, ровно как printf.
  function num_g(v, p) result(s)
    real(dp), intent(in) :: v
    integer(ip), intent(in) :: p
    character(len=:), allocatable :: s
    character(len=:), allocatable :: digits, frac
    character(len=64) :: mant, fmt
    integer(ip) :: k, x, neg
    ! ЛОВУШКА: es0.d (нулевая ширина поля) печатает 18 цифр независимо от d,
    ! поэтому ширина поля задана явно.
    write(fmt, '("(es40.",i0,"e3)")') p - 1
    write(mant, fmt) v
    mant = adjustl(mant)
    k = index(mant, 'E')
    if (k < 3) error stop 'json_num: unsupported float format'
    neg = 0
    if (mant(1:1) == '-') neg = 1
    digits = mant(neg + 1:neg + 1) // mant(neg + 3:k - 1)   ! цифры без точки
    read(mant(k + 1:), *) x                                 ! показатель
    if (x < -4 .or. x >= p) then
      frac = trim_zeros(digits(2:))
      s = ''
      if (neg == 1) s = s // '-'
      s = s // digits(1:1)
      if (len(frac) > 0) s = s // '.' // frac
      s = s // exp_text(x)
    else if (x >= 0) then
      frac = trim_zeros(digits(x + 2:))
      s = ''
      if (neg == 1) s = s // '-'
      s = s // digits(1:x + 1)
      if (len(frac) > 0) s = s // '.' // frac
    else
      s = ''
      if (neg == 1) s = s // '-'
      s = s // '0.' // repeat('0', -x - 1) // trim_zeros(digits)
    end if
  end function num_g

  pure function trim_zeros(s) result(t)
    character(len=*), intent(in) :: s
    character(len=:), allocatable :: t
    integer(ip) :: i
    i = len(s)
    do while (i > 0)
      if (s(i:i) /= '0') exit
      i = i - 1
    end do
    t = s(1:i)
  end function trim_zeros

  pure function exp_text(x) result(s)
    integer(ip), intent(in) :: x
    character(len=:), allocatable :: s
    character(len=8) :: d
    character(len=1) :: sg
    write(d, '(i0)') abs(x)
    if (x < 0) then
      sg = '-'
    else
      sg = '+'
    end if
    if (len_trim(d) < 2) then
      s = 'e' // sg // '0' // trim(d)
    else
      s = 'e' // sg // trim(d)
    end if
  end function exp_text

  !------------------------------ текстовый буфер ---------------------------

  subroutine tb_init(b)
    type(text_buf), intent(out) :: b
    b%cap = 16
    b%n = 0
    allocate(b%parts(b%cap))
    allocate(b%used(b%cap))
  end subroutine tb_init

  subroutine tb_grow(b, need)
    type(text_buf), intent(inout) :: b
    integer(ip), intent(in) :: need
    character(len=TB_CHUNK), allocatable :: parts(:)
    integer(ip), allocatable :: used(:)
    integer(ip) :: cap
    cap = b%cap
    do while (cap < need)
      cap = cap * 2
    end do
    allocate(parts(cap))
    allocate(used(cap))
    used = 0
    if (b%n > 0) then
      parts(1:b%n) = b%parts(1:b%n)
      used(1:b%n) = b%used(1:b%n)
    end if
    call move_alloc(parts, b%parts)
    call move_alloc(used, b%used)
    b%cap = cap
  end subroutine tb_grow

  subroutine tb_add(b, txt)
    type(text_buf), intent(inout) :: b
    character(len=*), intent(in) :: txt
    integer(ip) :: i8, nb, take
    nb = len(txt)
    i8 = 1
    do while (i8 <= nb)
      take = min(nb - i8 + 1, TB_CHUNK)
      if (b%n + 1 > b%cap) call tb_grow(b, b%n + 1)
      b%n = b%n + 1
      b%parts(b%n) = txt(i8:i8 + take - 1)
      b%used(b%n) = take
      i8 = i8 + take
    end do
  end subroutine tb_add

  function tb_text(b) result(s)
    type(text_buf), intent(in) :: b
    character(len=:), allocatable :: s
    integer(ip) :: k, total, off
    total = 0
    do k = 1, b%n
      total = total + b%used(k)
    end do
    allocate(character(len=total) :: s)
    off = 1
    do k = 1, b%n
      if (b%used(k) > 0) s(off:off + b%used(k) - 1) = b%parts(k)(1:b%used(k))
      off = off + b%used(k)
    end do
  end function tb_text

  pure function indent_for(depth) result(s)
    integer(ip), intent(in) :: depth
    character(len=:), allocatable :: s
    s = repeat(' ', 2 * depth)
  end function indent_for

  !------------------------- текст строки и рендерер ------------------------

  ! Экранирование строки для JSON: кавычка, обратный слэш, переводы строк и
  ! остальные управляющие символы (шестнадцатеричный код -- в нижнем регистре,
  ! как sprintf('\u%04x') в остальных портах).
  function json_esc(s) result(out)
    character(len=*), intent(in) :: s
    character(len=:), allocatable :: out
    type(text_buf) :: b
    character(len=16) :: tmp
    integer(ip) :: k, c
    call tb_init(b)
    do k = 1, len(s)
      c = iachar(s(k:k))
      select case (c)
      case (CODE_DQ)
        call tb_add(b, '\"')
      case (CODE_BS)
        call tb_add(b, '\\')
      case (10)
        call tb_add(b, '\n')
      case (13)
        call tb_add(b, '\r')
      case (9)
        call tb_add(b, '\t')
      case default
        if (c < 32) then
          write(tmp, '("\u",z4.4)') c
          call tb_add(b, to_lower_hex(tmp))
        else
          call tb_add(b, s(k:k))
        end if
      end select
    end do
    out = tb_text(b)
  end function json_esc

  pure function to_lower_hex(s) result(t)
    character(len=*), intent(in) :: s
    character(len=len(s)) :: t
    integer(ip) :: k, c
    t = s
    do k = 1, len(s)
      c = iachar(t(k:k))
      if (c >= 65 .and. c <= 70) t(k:k) = achar(c + 32)
    end do
  end function to_lower_hex

  ! Документ как текст JSON: отступ 2 пробела, ключи в порядке полей (та же
  ! форма, что json_render в Octave-порту и JsonWriter в остальных портах).
  function json_render(doc) result(s)
    type(json_doc), intent(in) :: doc
    character(len=:), allocatable :: s
    s = json_render_node(doc, doc%root)
  end function json_render

  ! Текст любого узла арены (нужно тестам и разбору готовых кусков).
  function json_render_node(doc, node) result(s)
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    character(len=:), allocatable :: s
    type(text_buf) :: b
    call tb_init(b)
    call rn_value(b, doc, node, 0)
    s = tb_text(b)
  end function json_render_node

  ! Рекурсия идёт по ИНДЕКСАМ арены (в типах рекурсии нет -- см. ловушку).
  recursive subroutine rn_value(b, doc, node, depth)
    type(text_buf), intent(inout) :: b
    type(json_doc), intent(in) :: doc
    integer(ip), intent(in) :: node
    integer(ip), intent(in) :: depth
    integer(ip) :: k, n
    select case (jkind(doc, node))
    case (JK_NULL)
      call tb_add(b, 'null')
    case (JK_BOOL)
      if (doc%pool(node)%bval) then
        call tb_add(b, 'true')
      else
        call tb_add(b, 'false')
      end if
    case (JK_NUM)
      call tb_add(b, json_num_text(doc%pool(node)%nval))
    case (JK_TEXT)
      call tb_add(b, '"' // json_esc(doc%pool(node)%text) // '"')
    case (JK_RAW)
      call tb_add(b, doc%pool(node)%text)
    case (JK_NUMV)
      if (size(doc%pool(node)%nvec) == 0) then
        call tb_add(b, '[]')
      else
        call tb_add(b, '[' // CH_NL)
        call tb_add(b, indent_for(depth + 1))
        do k = 1, size(doc%pool(node)%nvec)
          if (k > 1) call tb_add(b, ', ')
          call tb_add(b, json_num_text(doc%pool(node)%nvec(k)))
        end do
        call tb_add(b, CH_NL // indent_for(depth) // ']')
      end if
    case (JK_ARR)
      n = nkids(doc, node)
      if (n == 0) then
        call tb_add(b, '[]')
      else
        call tb_add(b, '[' // CH_NL)
        do k = 1, n
          call tb_add(b, indent_for(depth + 1))
          call rn_value(b, doc, doc%pool(node)%kids(k), depth + 1)
          if (k < n) call tb_add(b, ',')
          call tb_add(b, CH_NL)
        end do
        call tb_add(b, indent_for(depth) // ']')
      end if
    case (JK_OBJ)
      n = nkids(doc, node)
      if (n == 0) then
        call tb_add(b, '{}')
      else
        call tb_add(b, '{' // CH_NL)
        do k = 1, n
          call tb_add(b, indent_for(depth + 1))
          call tb_add(b, '"' // json_esc(trim(doc%pool(node)%kname(k))) // '": ')
          call rn_value(b, doc, doc%pool(node)%kids(k), depth + 1)
          if (k < n) call tb_add(b, ',')
          call tb_add(b, CH_NL)
        end do
        call tb_add(b, indent_for(depth) // '}')
      end if
    case default
      error stop 'json_render: unsupported node kind'
    end select
  end subroutine rn_value

  !------------------------------- парсер ----------------------------------
  !
  ! Рекурсивный разборщик: курсор передаётся явным аргументом, узлы кладутся в
  ! арену (doc), наружу отдаётся ИНДЕКС узла. Ошибки -- error stop: во всех
  ! портах битый JSON тоже приводит к аварийному завершению, а не к
  ! частичному результату.

  function json_parse(text) result(doc)
    character(len=*), intent(in) :: text
    type(json_doc) :: doc
    integer(ip) :: pos, root
    if (len(text) == 0) error stop 'json_parse: empty input'
    doc = jd_create()
    pos = 1
    call jp_value(text, pos, doc, root)
    doc%root = root
    call jp_ws(text, pos)
    if (pos <= len(text)) error stop 'json_parse: unexpected trailing data'
  end function json_parse

  ! Пропустить пробельные символы (пробел, табуляция, LF, CR).
  subroutine jp_ws(s, pos)
    character(len=*), intent(in) :: s
    integer(ip), intent(inout) :: pos
    integer(ip) :: c
    do while (pos <= len(s))
      c = iachar(s(pos:pos))
      if (c == 32 .or. c == 9 .or. c == 10 .or. c == 13) then
        pos = pos + 1
      else
        exit
      end if
    end do
  end subroutine jp_ws

  pure function is_numc(c) result(tf)
    character(len=1), intent(in) :: c
    logical :: tf
    integer(ip) :: k
    k = iachar(c)
    tf = (k >= 48 .and. k <= 57) .or. c == '+' .or. c == '-' .or. &
         c == '.' .or. c == 'e' .or. c == 'E'
  end function is_numc

  ! Значение: создаёт узел в арене и разбирает его содержимое.
  recursive subroutine jp_value(s, pos, doc, idx)
    character(len=*), intent(in) :: s
    integer(ip), intent(inout) :: pos
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(out) :: idx
    character(len=1) :: c
    call jp_ws(s, pos)
    if (pos > len(s)) error stop 'json_parse: unexpected end of input'
    idx = jd_new(doc)
    c = s(pos:pos)
    select case (c)
    case ('{')
      doc%pool(idx)%kind = JK_OBJ
      call jp_object(s, pos, doc, idx)
    case ('[')
      doc%pool(idx)%kind = JK_ARR
      call jp_array(s, pos, doc, idx)
    case (CH_DQ)
      doc%pool(idx)%kind = JK_TEXT
      call jp_string(s, pos, doc%pool(idx)%text)
    case ('t')
      call jp_keyword(s, pos, 'true')
      doc%pool(idx)%kind = JK_BOOL
      doc%pool(idx)%bval = .true.
    case ('f')
      call jp_keyword(s, pos, 'false')
      doc%pool(idx)%kind = JK_BOOL
      doc%pool(idx)%bval = .false.
    case ('n')
      call jp_keyword(s, pos, 'null')
      doc%pool(idx)%kind = JK_NULL
    case default
      doc%pool(idx)%kind = JK_NUM
      doc%pool(idx)%nval = jp_number(s, pos)
    end select
  end subroutine jp_value

  ! Ключевое слово true/false/null.
  subroutine jp_keyword(s, pos, word)
    character(len=*), intent(in) :: s
    integer(ip), intent(inout) :: pos
    character(len=*), intent(in) :: word
    integer(ip) :: n
    n = len(word)
    if (pos + n - 1 > len(s)) error stop 'json_parse: unterminated keyword'
    if (s(pos:pos + n - 1) /= word) error stop 'json_parse: bad keyword'
    pos = pos + n
  end subroutine jp_keyword

  ! Число: собираем подряд идущие числовые символы и читаем их тем же приёмом,
  ! что str2double в Octave-порту (внутренний list-directed read).
  function jp_number(s, pos) result(x)
    character(len=*), intent(in) :: s
    integer(ip), intent(inout) :: pos
    real(dp) :: x
    integer(ip) :: k, ios
    character(len=:), allocatable :: txt
    k = pos
    do while (k <= len(s))
      if (is_numc(s(k:k))) then
        k = k + 1
      else
        exit
      end if
    end do
    if (k == pos) error stop 'json_parse: unexpected character: '//s(pos:pos)
    txt = s(pos:k - 1)
    read(txt, *, iostat=ios) x
    if (ios /= 0) error stop 'json_parse: bad number: '//txt
    pos = k
  end function jp_number

  ! Строка в кавычках с escape-последовательностями; \uXXXX вне ASCII даёт '?'
  ! (как в Octave-порту: там hex2dec без полноценного UTF-16).
  subroutine jp_string(s, pos, out)
    character(len=*), intent(in) :: s
    integer(ip), intent(inout) :: pos
    character(len=:), allocatable, intent(out) :: out
    type(text_buf) :: b
    character(len=1) :: c
    integer(ip) :: code
    if (pos > len(s)) error stop 'json_parse: unterminated string'
    if (s(pos:pos) /= CH_DQ) error stop 'json_parse: expected a string'
    call tb_init(b)
    pos = pos + 1
    do
      if (pos > len(s)) error stop 'json_parse: unterminated string'
      c = s(pos:pos)
      if (c == CH_DQ) then
        pos = pos + 1
        exit
      end if
      if (c == CH_BS) then
        pos = pos + 1
        if (pos > len(s)) error stop 'json_parse: unterminated escape'
        c = s(pos:pos)
        select case (c)
        case ('n')
          call tb_add(b, CH_NL)
        case ('t')
          call tb_add(b, achar(9))
        case ('r')
          call tb_add(b, CH_CR)
        case ('b')
          call tb_add(b, achar(8))
        case ('f')
          call tb_add(b, achar(12))
        case ('/')
          call tb_add(b, '/')
        case (CH_DQ)
          call tb_add(b, CH_DQ)
        case (CH_BS)
          call tb_add(b, CH_BS)
        case ('u')
          code = jp_hex4(s, pos + 1)
          if (code < 128) then
            call tb_add(b, achar(code))
          else
            call tb_add(b, '?')
          end if
          pos = pos + 4
        case default
          error stop 'json_parse: bad escape sequence'
        end select
        pos = pos + 1
      else
        call tb_add(b, c)
        pos = pos + 1
      end if
    end do
    out = tb_text(b)
  end subroutine jp_string

  function jp_hex4(s, i) result(code)
    character(len=*), intent(in) :: s
    integer(ip), intent(in) :: i
    integer(ip) :: code, k, d
    code = 0
    if (i + 3 > len(s)) error stop 'json_parse: bad \u escape'
    do k = 0, 3
      d = hex_digit(s(i + k:i + k))
      if (d < 0) error stop 'json_parse: bad \u escape'
      code = code * 16 + d
    end do
  end function jp_hex4

  pure function hex_digit(c) result(d)
    character(len=1), intent(in) :: c
    integer(ip) :: d, k
    k = iachar(c)
    if (k >= 48 .and. k <= 57) then
      d = k - 48
    else if (k >= 97 .and. k <= 102) then
      d = k - 97 + 10
    else if (k >= 65 .and. k <= 70) then
      d = k - 65 + 10
    else
      d = -1
    end if
  end function hex_digit

  ! Объект: поля добавляются в узел idx по мере разбора.
  ! RECURSIVE обязателен: jp_object зовёт jp_value, который может позвать снова
  ! jp_object/jp_array (вложенность). gfortran с -fcheck=recursion это ловит.
  recursive subroutine jp_object(s, pos, doc, idx)
    character(len=*), intent(in) :: s
    integer(ip), intent(inout) :: pos
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: idx
    character(len=:), allocatable :: key
    integer(ip) :: cidx
    call jp_ws(s, pos)
    if (pos > len(s)) error stop 'json_parse: unexpected end of input'
    if (s(pos:pos) /= '{') error stop 'json_parse: expected an object'
    pos = pos + 1
    call jp_ws(s, pos)
    if (pos <= len(s)) then
      if (s(pos:pos) == '}') then
        pos = pos + 1
        return
      end if
    end if
    do
      call jp_ws(s, pos)
      call jp_string(s, pos, key)
      if (len_trim(key) > JNAME_LEN) error stop 'json_parse: field name is too long'
      call jp_ws(s, pos)
      if (pos > len(s)) error stop 'json_parse: unterminated object'
      if (s(pos:pos) /= ':') error stop 'json_parse: expected a colon'
      pos = pos + 1
      call jp_value(s, pos, doc, cidx)
      call jkid_push(doc, idx, key, cidx)
      call jp_ws(s, pos)
      if (pos > len(s)) error stop 'json_parse: unterminated object'
      if (s(pos:pos) == ',') then
        pos = pos + 1
      else if (s(pos:pos) == '}') then
        pos = pos + 1
        exit
      else
        error stop 'json_parse: expected a comma or a closing brace'
      end if
    end do
  end subroutine jp_object

  recursive subroutine jp_array(s, pos, doc, idx)
    character(len=*), intent(in) :: s
    integer(ip), intent(inout) :: pos
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: idx
    integer(ip) :: cidx, k, n
    logical :: all_num
    call jp_ws(s, pos)
    if (pos > len(s)) error stop 'json_parse: unexpected end of input'
    if (s(pos:pos) /= '[') error stop 'json_parse: expected an array'
    pos = pos + 1
    call jp_ws(s, pos)
    if (pos <= len(s)) then
      if (s(pos:pos) == ']') then
        pos = pos + 1
        return
      end if
    end if
    do
      call jp_value(s, pos, doc, cidx)
      call jarr_add(doc, idx, cidx)
      call jp_ws(s, pos)
      if (pos > len(s)) error stop 'json_parse: unterminated array'
      if (s(pos:pos) == ',') then
        pos = pos + 1
      else if (s(pos:pos) == ']') then
        pos = pos + 1
        exit
      else
        error stop 'json_parse: expected a comma or a closing bracket'
      end if
    end do
    ! Массив, ЦЕЛИКОМ состоящий из чисел, -- это числовой вектор: в остальных
    ! портах такой массив приходит числовой матрицей и рендерится ОДНОЙ
    ! строкой значений (render_numbers в Octave-порту). Иначе разбор и
    ! обратная запись документа разошлись бы по виду.
    n = nkids(doc, idx)
    all_num = n > 0
    do k = 1, n
      if (jkind(doc, jkid(doc, idx, k)) /= JK_NUM) then
        all_num = .false.
        exit
      end if
    end do
    if (all_num) call jnode_to_numv(doc, idx, n)
  end subroutine jp_array

  ! Превратить узел-массив из одних чисел в числовой вектор (JK_NUMV).
  subroutine jnode_to_numv(doc, node, n)
    type(json_doc), intent(inout) :: doc
    integer(ip), intent(in) :: node
    integer(ip), intent(in) :: n
    real(dp), allocatable :: v(:)
    integer(ip) :: k
    allocate(v(n))
    do k = 1, n
      v(k) = doc%pool(doc%pool(node)%kids(k))%nval
    end do
    doc%pool(node)%kind = JK_NUMV
    if (allocated(doc%pool(node)%kids)) deallocate(doc%pool(node)%kids)
    if (allocated(doc%pool(node)%kname)) deallocate(doc%pool(node)%kname)
    call move_alloc(v, doc%pool(node)%nvec)
  end subroutine jnode_to_numv

  !---------------------------- файлы: чтение/запись ------------------------

  ! Прочитать файл целиком байт в байт.
  !
  ! ЛОВУШКА WINDOWS: форматный ввод-вывод переводит строки в CRLF, поэтому и
  ! чтение, и запись -- ТОЛЬКО access='stream', form='unformatted': тогда
  ! переводы строк остаются такими, какие есть в файле (LF у наших документов).
  function json_read_text(path) result(txt)
    character(len=*), intent(in) :: path
    character(len=:), allocatable :: txt
    integer(ip) :: u, n
    logical :: ex
    inquire(file=path, exist=ex, size=n)
    if (.not. ex) error stop 'json_read_text: no such file: '//path
    if (n < 0) n = 0
    allocate(character(len=n) :: txt)
    open(newunit=u, file=path, access='stream', form='unformatted', status='old')
    if (n > 0) read(u) txt
    close(u)
  end function json_read_text

  subroutine json_write_text(path, txt)
    character(len=*), intent(in) :: path
    character(len=*), intent(in) :: txt
    integer(ip) :: u, ios
    open(newunit=u, file=path, access='stream', form='unformatted', &
         status='replace', iostat=ios)
    if (ios /= 0) error stop 'json_write_text: cannot open: '//path
    write(u) txt
    close(u)
  end subroutine json_write_text

  !------------------------ перечисление файлов каталога --------------------

  ! Файлы каталога по маске, по возрастанию имён (каталог конформанс-векторов).
  !
  ! В стандартном Фортране перечисления каталога нет, поэтому используем
  ! `dir /b /o:n` (Windows-специфично, как и остальные детали порта; имена
  ! векторов -- ASCII, порядок совпадает с sort() в Octave-порту). Пустой
  ! результат -- просто пустой список: решение «нет векторов» принимает
  ! вызывающий код.
  subroutine json_list_files(dir, mask, files)
    character(len=*), intent(in) :: dir
    character(len=*), intent(in) :: mask
    character(len=JP_PATH_LEN), allocatable, intent(out) :: files(:)
    character(len=JP_PATH_LEN) :: tmpdir, listfile
    character(len=1024) :: cmd
    character(len=:), allocatable :: txt
    integer(ip) :: u
    logical :: ex
    tmpdir = get_temp_dir()
    listfile = trim(tmpdir)//'\pappa_fortran_list.tmp'
    cmd = 'dir /b /o:n "'//trim(dir)//'\'//trim(mask)//'" > "'// &
          trim(listfile)//'" 2>nul'
    call execute_command_line(trim(cmd))
    allocate(files(0))
    inquire(file=trim(listfile), exist=ex)
    if (.not. ex) return
    txt = json_read_text(trim(listfile))
    call split_lines(txt, files)
    open(newunit=u, file=trim(listfile), status='old')
    close(u, status='delete')
  end subroutine json_list_files

  function get_temp_dir() result(d)
    character(len=JP_PATH_LEN) :: d
    call get_environment_variable('TEMP', d)
    if (len_trim(d) == 0) call get_environment_variable('TMP', d)
    if (len_trim(d) == 0) d = '.'
  end function get_temp_dir

  ! Разбить текст на строки: снять завершающий CR и хвостовые пробелы, пустые
  ! строки пропустить.
  subroutine split_lines(txt, lines)
    character(len=*), intent(in) :: txt
    character(len=JP_PATH_LEN), allocatable, intent(out) :: lines(:)
    integer(ip) :: k, start, cnt, n
    n = 0
    do k = 1, len(txt)
      if (iachar(txt(k:k)) == 10) n = n + 1
    end do
    if (len(txt) > 0) then
      if (iachar(txt(len(txt):len(txt))) /= 10) n = n + 1
    end if
    allocate(lines(n))
    cnt = 0
    start = 1
    do k = 1, len(txt)
      if (iachar(txt(k:k)) == 10) then
        call put_line(txt(start:k - 1), lines, cnt)
        start = k + 1
      end if
    end do
    if (start <= len(txt)) call put_line(txt(start:), lines, cnt)
  end subroutine split_lines

  subroutine put_line(s, lines, n)
    character(len=*), intent(in) :: s
    character(len=JP_PATH_LEN), allocatable, intent(inout) :: lines(:)
    integer(ip), intent(inout) :: n
    integer(ip) :: c
    c = len(s)
    do while (c > 0)
      if (iachar(s(c:c)) == 13 .or. iachar(s(c:c)) == 9 .or. &
          iachar(s(c:c)) == 32) then
        c = c - 1
      else
        exit
      end if
    end do
    if (c == 0) return
    if (c > JP_PATH_LEN) c = JP_PATH_LEN
    if (n + 1 > size(lines)) return
    n = n + 1
    lines(n) = s(1:c)
  end subroutine put_line

end module pappa_json
