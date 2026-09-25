"""Проверка целочисленного ядра PAPPA: AVR/хост против референса на Python.

Что делает:
  1) регенерирует то же сечение, что ушло в прошивку (embedded/tools/section.py);
  2) считает эталон НА PYTHON (double, независимая реализация: накопление Грама
     в базисе Чебышёва + правило «локтя» по явным остаткам + абсолютный пол);
  3) берёт числа от устройства: из файла (--log), из хост-сборки (--host) или
     из симуляции Wokwi (--wokwi, нужен WOKWI_CLI_TOKEN);
  4) сравнивает степени, таблицу RMSE и КРИВУЮ (max|dr|, допуск 1e-6 мм).

Коды выхода: 0 — всё сошлось, 1 — расхождение, 2 — не найдены числа устройства.
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import section as S  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                 # embedded/
TOL_CURVE_MM = 1.0e-6        # допуск метода (как в spec/conformance)
TOL_RMSE_MM = 1.0e-6         # печать RMSE в пм + округление float


def cheb_mono_int(kmax):
    """Целочисленные мономиальные коэффициенты T_k (по возрастанию степени).

    T_k = 2x*T_{k-1} - T_{k-2}: умножение на x сдвигает коэффициенты на 1.
    """
    T = [[1]]
    if kmax >= 1:
        T.append([0, 1])
    for k in range(2, kmax + 1):
        prev, prev2 = T[k - 1], T[k - 2]
        v = [0] * (len(prev) + 1)
        for i, c in enumerate(prev):
            v[i + 1] += 2 * c
        for i, c in enumerate(prev2):
            v[i] -= c
        T.append(v)
    return T


def solve(M, b, n):
    """Гаусс с выбором главного элемента; M — n x n (копируется)."""
    A = [[M[i][j] for j in range(n)] + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(A[r][col]))
        A[col], A[piv] = A[piv], A[col]
        d = A[col][col]
        for k in range(col, n + 1):
            A[col][k] /= d
        for r in range(n):
            if r == col:
                continue
            f = A[r][col]
            if f == 0.0:
                continue
            for k in range(col, n + 1):
                A[r][k] -= f * A[col][k]
    return [A[i][n] for i in range(n)]


def cheb_row(x, deg_max):
    T = [1.0]
    if deg_max >= 1:
        T.append(x)
    for k in range(2, deg_max + 1):
        T.append(2.0 * x * T[k - 1] - T[k - 2])
    return T


def cheb_sum(c, deg, x):
    b1 = b2 = 0.0
    for k in range(deg, 0, -1):
        b1, b2 = 2.0 * x * b1 - b2 + c[k], b1
    return x * b1 - b2 + c[0]


def reference_fit(y_u, centers, half, deg_min, deg_max, floor_u):
    """Эталон в double: список (deg, coef_mm_asc, rmse_tab_mm)."""
    n = len(y_u)
    y_mm = [v / 1.0e5 for v in y_u]
    Tm = cheb_mono_int(deg_max)
    out = []
    for center in centers:
        yref = y_mm[center]
        nwin = 2 * half + 1
        ncol = deg_max + 1
        M = [[0.0] * ncol for _ in range(ncol)]
        b = [0.0] * ncol
        xs = []
        for k in range(nwin):
            off = k - half
            i = (center + off) % n
            x = off / half
            yc = y_mm[i] - yref
            xs.append((x, yc))
            row = cheb_row(x, deg_max)
            for a in range(ncol):
                b[a] += row[a] * yc
                for c in range(a, ncol):
                    M[a][c] += row[a] * row[c]
        for a in range(ncol):
            for c in range(a + 1, ncol):
                M[c][a] = M[a][c]

        best, rmse_tab = None, []
        sel, hit = deg_min, False
        for deg in range(deg_min, deg_max + 1, 2):
            nn = deg + 1
            c = solve([row[:nn] for row in M[:nn]], b[:nn], nn)
            sse = sum((cheb_sum(c, deg, x) - yc) ** 2 for x, yc in xs)
            rmse = (sse / nwin) ** 0.5
            rmse_tab.append(rmse)
            if best is None or rmse < best:
                best = rmse
            if rmse <= floor_u / 1.0e5:
                sel, hit = deg, True
                break
        if not hit:
            limit = best * 1.05
            for t, rmse in enumerate(rmse_tab):
                if rmse <= limit:
                    sel = deg_min + 2 * t
                    break

        nn = sel + 1
        c = solve([row[:nn] for row in M[:nn]], b[:nn], nn)
        coef = [0.0] * nn
        for j in range(nn):
            coef[j] = sum(c[kk] * Tm[kk][j] for kk in range(j, nn))
        coef[0] += yref          # абсолютный радиус, как в документе
        out.append((sel, coef, rmse_tab))
    return out


def parse_report(text):
    deg, coef, rmse, yref, cheb, time_us = {}, {}, {}, {}, {}, None
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == 'PATCH' and len(parts) >= 3:
            deg[int(parts[1])] = int(parts[2].split('=')[1])
        elif parts[0] == 'YREF' and len(parts) >= 3:
            yref[int(parts[1])] = int(parts[2]) / 1.0e5      # единицы 1e-5 мм -> мм
        elif parts[0] == 'COEF' and len(parts) >= 3:
            coef[int(parts[1])] = [int(v) / 1.0e8 for v in parts[2:]]
        elif parts[0] == 'CHEB' and len(parts) >= 3:
            cheb[int(parts[1])] = [int(v) / 1.0e8 for v in parts[2:]]
        elif parts[0] == 'RMSE' and len(parts) >= 3:
            rmse[int(parts[1])] = [int(v) / 1.0e9 for v in parts[2:]]
        elif parts[0] == 'TIME_US' and len(parts) >= 2:
            time_us = int(parts[1])
    return deg, coef, rmse, yref, cheb, time_us


def run_host():
    gcc = shutil.which('gcc')
    if not gcc:
        for cand in (r'C:\msys64\mingw64\bin\gcc.exe', r'C:\msys64\ucrt64\bin\gcc.exe'):
            if os.path.exists(cand):
                gcc = cand
                break
    if not gcc:
        print('нет gcc для хост-сборки')
        return None
    out_dir = os.path.join(ROOT, 'build_host')
    os.makedirs(out_dir, exist_ok=True)
    exe = os.path.join(out_dir, 'pp_host.exe' if os.name == 'nt' else 'pp_host')
    cmd = [gcc, '-std=c99', '-O2', '-Wall', f'-I{ROOT}',
           f'-I{os.path.join(ROOT, S.BOARD)}',
           f'-DPP_MAX_PATCHES={S.N_PATCHES}', f'-DPP_MAX_DEG={S.DEG_MAX}',
           os.path.join(ROOT, 'pappa_int.c'), os.path.join(ROOT, 'host_main.c'),
           '-o', exe, '-lm']
    print('сборка хоста: ' + ' '.join(cmd))
    subprocess.run(cmd, check=True)
    return subprocess.run([exe], capture_output=True, text=True, check=False).stdout


def run_wokwi(timeout_ms):
    token = os.environ.get('WOKWI_CLI_TOKEN', '')
    cli = os.path.join(os.path.expanduser('~'), '.wokwi', 'bin',
                       'wokwi-cli.exe' if os.name == 'nt' else 'wokwi-cli')
    if not os.path.exists(cli):
        print(f'нет wokwi-cli ({cli}) — поставь: iwr https://wokwi.com/ci/install.ps1 -useb | iex')
        return None
    if not token:
        print('нет WOKWI_CLI_TOKEN — токен берётся на https://wokwi.com/dashboard/ci')
        return None
    log = os.path.join(ROOT, S.BOARD, 'build', 'serial.log')
    os.makedirs(os.path.dirname(log), exist_ok=True)
    if os.path.exists(log):
        os.remove(log)
    cmd = [cli, os.path.join(ROOT, S.BOARD), '--timeout', str(timeout_ms),
           '--serial-log-file', log, '--expect-text', 'PAPPA_DONE']
    print('запуск: ' + ' '.join(cmd))
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.stdout.strip():
        print(res.stdout.strip()[-3000:])
    print(f'wokwi-cli код возврата: {res.returncode}')
    if os.path.exists(log):
        return open(log, encoding='utf-8', errors='replace').read()
    return res.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--board', default='uno', choices=sorted(S.PRESETS),
                    help='пресет платы (uno/mega): сечение, патчи, степени')
    ap.add_argument('--log', help='файл с выводом устройства (serial log)')
    ap.add_argument('--host', action='store_true', help='собрать и запустить хост-сборку')
    ap.add_argument('--wokwi', action='store_true', help='запустить симуляцию Wokwi')
    ap.add_argument('--timeout', type=int, default=20000)
    ap.add_argument('--tol', type=float, default=TOL_CURVE_MM)
    args = ap.parse_args()
    S.use(args.board)

    y_u = S.section_u()
    centers = S.center_points()
    ref = reference_fit(y_u, centers, S.HALF_TRAIN_PTS, S.DEG_MIN, S.DEG_MAX, S.FLOOR_U)

    if args.log:
        text, src = open(args.log, encoding='utf-8', errors='replace').read(), args.log
    elif args.wokwi:
        text, src = run_wokwi(args.timeout), f'Wokwi ({S.BOARD})'
    elif args.host:
        text, src = run_host(), 'хост (x86, тот же C-код)'
    else:
        print('укажи --host, --wokwi или --log FILE')
        return 2
    if not text:
        print('числа устройства не получены')
        return 2

    deg, coef, rmse, yref, cheb, time_us = parse_report(text)
    if not deg:
        print('в выводе нет строк PATCH/COEF (прошивка не дошла до отчёта?)')
        print(text[-2000:])
        return 2

    print(f'источник: {src}')
    print(f'сечение: точек {len(y_u)}, патчей {len(centers)}, окно '
          f'{2 * S.HALF_TRAIN_PTS + 1} точек, степени {S.DEG_MIN}..{S.DEG_MAX}, '
          f'пол {S.FLOOR_U}e-5 мм')
    if time_us is not None:
        print(f'время обучения на чипе: {time_us} мкс ({time_us / 1000.0:.1f} мс)')
    ok = True
    print(f'{"патч":>4} {"deg":>4} {"deg эталон":>10} {"max|dr|, мм":>12} '
          f'{"RMSE устр., мм":>14} {"RMSE эталон":>12}')
    for p, (rdeg, rcoef, rrmse) in enumerate(ref):
        d = deg.get(p, -1)
        max_dc = 0.0
        cq = cheb.get(p, [])
        if cq:
            # Устройство отдаёт коэффициенты ЧЕБЫШЁВА + опорный радиус: форма
            # устойчива (Clenshaw), поэтому кривая сверяется именно по ним.
            # Мономиальная форма при большой степени плохо обусловлена — на
            # патче со трещиной степенью 10 она даёт сотни мкм (docs/embedded.md §12).
            y_dev = yref.get(p, 0.0)
            for t in range(201):
                x = -1.0 + 2.0 * t / 200.0
                fw = y_dev + cheb_sum(cq, len(cq) - 1, x)
                rf = sum(v * x ** j for j, v in enumerate(rcoef))
                max_dc = max(max_dc, abs(fw - rf))
        else:
            c = list(coef.get(p, []))
            if c:
                c[0] += yref.get(p, 0.0)
            for t in range(201):
                x = -1.0 + 2.0 * t / 200.0
                fw = sum(v * x ** j for j, v in enumerate(c))
                rf = sum(v * x ** j for j, v in enumerate(rcoef))
                max_dc = max(max_dc, abs(fw - rf))
        rmse_dev = rmse.get(p, [])
        r_ok = bool(rmse_dev) and all(abs(a - b) <= TOL_RMSE_MM
                                      for a, b in zip(rmse_dev, rrmse))
        row_ok = (d == rdeg) and r_ok and (max_dc <= args.tol)
        ok = ok and row_ok
        tail = '' if d == rdeg else '  <- СТЕПЕНЬ РАСХОДИТСЯ'
        print(f'{p:>4} {d:>4} {rdeg:>10} {max_dc:>12.3e} '
              f'{(rmse_dev[-1] if rmse_dev else float("nan")):>14.9f} '
              f'{rrmse[-1]:>12.9f}{tail}')
    print(('ВЫВОД: устройство воспроизводит референс в пределах допуска '
           f'{args.tol:g} мм') if ok else 'ВЫВОД: есть расхождения')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

