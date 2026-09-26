! PAPPA Fortran port -- общие константы.
!
! Порядок компиляции: этот модуль идёт первым, от него зависят остальные.
module pappa_kinds
  use, intrinsic :: iso_fortran_env, only: int32, int64, real64
  implicit none
  private
  public :: dp, ip, lp, pi, pappa_version, pappa_language

  ! Референс (Python/numpy) считает в float64, поэтому весь порт -- real64.
  integer, parameter :: dp = real64
  integer, parameter :: ip = int32
  integer, parameter :: lp = int64

  real(dp), parameter :: pi = 3.14159265358979323846264338327950288_dp

  character(len=*), parameter :: pappa_version = '0.1.0'
  character(len=*), parameter :: pappa_language = 'fortran'
end module pappa_kinds
