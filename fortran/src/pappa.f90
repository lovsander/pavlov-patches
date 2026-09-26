! PAPPA Fortran port -- пайплайн: CSV с сечениями -> папка образца.
! Пишет ТОТ ЖЕ формат, что референс Python и остальные порты:
!   <out-dir>/sample.json  +  <out-dir>/sections/NN.pappa.json
! Сверка: python python/studies/verify_port.py --cpp-dir <out-dir>
! Запуск: pappa.exe --input FILE.csv --out-dir DIR [--name NAME]
!         [--description ТЕКСТ] [--no-pits] [--quiet]
!
! Разбор аргументов повторяет pascal/src/pappa.lpr: неизвестный ключ или
! отсутствие --input/--out-dir -> подсказка и код возврата 2 (как Halt(2)).
program pappa
  use pappa_kinds, only: ip
  use pappa_csv, only: pipe_options, pipe_default_options
  use pappa_csv, only: csv_row, section_model, csv_load, csv_process
  use pappa_document, only: sample_options, doc_default_sample, doc_save_sample
  implicit none
  character(len=1024) :: input, out_dir, name, description, arg
  logical :: pits, quiet
  type(pipe_options) :: opt
  type(csv_row), allocatable :: rows(:)
  type(section_model), allocatable :: sections(:)
  type(sample_options) :: sopts
  character(len=:), allocatable :: root
  integer(ip) :: i

  input = ''
  out_dir = ''
  name = 'sample'
  description = 'PAPPA Fortran port'
  pits = .true.
  quiet = .false.

  i = 1
  do while (i <= command_argument_count())
    call get_command_argument(i, arg)
    select case (trim(arg))
    case ('--input')
      i = i + 1
      if (i <= command_argument_count()) call get_command_argument(i, input)
    case ('--out-dir')
      i = i + 1
      if (i <= command_argument_count()) call get_command_argument(i, out_dir)
    case ('--name')
      i = i + 1
      if (i <= command_argument_count()) call get_command_argument(i, name)
    case ('--description')
      i = i + 1
      if (i <= command_argument_count()) call get_command_argument(i, description)
    case ('--no-pits')
      pits = .false.
    case ('--quiet')
      quiet = .true.
    case default
      call usage()
      stop 2
    end select
    i = i + 1
  end do
  if (len_trim(input) == 0 .or. len_trim(out_dir) == 0) then
    call usage()
    stop 2
  end if

  rows = csv_load(trim(input))
  write(*, '(a,i0,a,a)') 'PAPPA (Fortran): ', size(rows), ' точек, вход ', trim(input)

  opt = pipe_default_options()
  opt%pits = pits
  opt%verbose = .not. quiet
  sections = csv_process(rows, opt)

  sopts = doc_default_sample()
  sopts%input_csv = trim(input)
  sopts%pits = pits
  sopts%description = trim(description)
  sopts%cleaner = opt%cleaner
  sopts%detector = opt%detector
  root = doc_save_sample(trim(out_dir), trim(name), sections, sopts)

  write(*,*) ''
  write(*,*) 'Образец записан: ' // root
  write(*,*) '  манифест: ' // root // '\sample.json'
  write(*, '(a,i0,a)') '  сечений:  ', size(sections), ' (sections/*.pappa.json)'
  write(*,*) ''
  write(*,*) 'Сверка с референсом Python:'
  write(*,*) '  python python/studies/verify_port.py --cpp-dir ' // root

contains

  subroutine usage()
    write(*,*) 'PAPPA (Fortran): --input FILE.csv --out-dir DIR [--name NAME] ' // &
      '[--description ТЕКСТ] [--no-pits] [--quiet]'
  end subroutine usage

end program pappa
