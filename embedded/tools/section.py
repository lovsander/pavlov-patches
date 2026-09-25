"""Сечение для теста целочисленного ядра на MCU.

Один и тот же профиль используется:
  * генератором заголовка для прошивки (embedded/uno/section_data.h),
  * проверкой (embedded/tools/check.py) — как вход для референса в double.

Единицы хранения: int32 в 1e-5 мм (0.01 мкм) — квантование ЗАМЕТНО точнее
допуска метода (1e-6 мм), поэтому разница «квантование vs double» не мешает
сверке алгоритма.
"""
import math

N_POINTS = 360            # точек в сечении (шаг 1°)
N_PATCHES = 3
HALF_TRAIN_PTS = 45       # полуширина обучающего окна в точках (окно 25% кольца)
DEG_MIN = 4
DEG_MAX = 8               # на 2 КБ RAM выше 8 смысла нет
FLOOR_U = 1               # абсолютный пол RMSE, единицы 1e-5 мм (= 10 пм)
PHASE_DEG = 0.0           # центры патчей: 0°, 120°, 240°
PIT_CENTER_DEG = 118.0    # узкая канавка (проверяем, что степень на неё реагирует)
PIT_WIDTH_DEG = 3.0
PIT_DEPTH_MM = 0.30
R0_MM = 15.0


def profile(i):
    """Радиус, мм, для точки i (угол = i * 360/N)."""
    a = 360.0 * i / N_POINTS
    r = R0_MM + 0.40 * math.sin(math.radians(2.0 * a)) - 0.10 * math.cos(math.radians(3.0 * a))
    d = abs(((a - PIT_CENTER_DEG + 180.0) % 360.0) - 180.0)
    if d <= PIT_WIDTH_DEG / 2.0:
        r -= PIT_DEPTH_MM
    return r


def section_u():
    """Радиусы в единицах 1e-5 мм (int32)."""
    return [int(round(profile(i) * 1.0e5)) for i in range(N_POINTS)]


def center_points():
    """Индексы центров патчей (геометрию задаёт хост, МНК считает устройство)."""
    out = []
    for p in range(N_PATCHES):
        deg = PHASE_DEG + 360.0 * p / N_PATCHES + 360.0 / (2.0 * N_PATCHES)
        out.append(int(round(deg / 360.0 * N_POINTS)) % N_POINTS)
    return out


def write_header(path):
    y = section_u()
    c = center_points()
    lines = [
        "// СГЕНЕРИРОВАНО embedded/tools/section.py — не править руками.",
        "#ifndef PP_SECTION_DATA_H",
        "#define PP_SECTION_DATA_H",
        "#include <stdint.h>",
        '#include "pappa_int.h"',
        "",
        f"#define PP_SECTION_N {N_POINTS}",
        f"#define PP_N_PATCHES {N_PATCHES}",
        f"#define PP_HALF_TRAIN_PTS {HALF_TRAIN_PTS}",
        f"#define PP_DEG_MIN {DEG_MIN}",
        f"#define PP_DEG_MAX {DEG_MAX}",
        f"#define PP_FLOOR_U {FLOOR_U}",
        "",
        f"static const int32_t pp_section_u[PP_SECTION_N] PP_CONST = {{",
    ]
    for i in range(0, len(y), 8):
        lines.append("    " + ", ".join(str(v) for v in y[i:i + 8]) + ",")
    lines.append("};")
    lines.append("")
    lines.append(f"static const int16_t pp_center_pt[PP_N_PATCHES] PP_CONST = {{ "
                 + ", ".join(str(v) for v in c) + " };")
    lines.append("")
    lines.append("#endif  // PP_SECTION_DATA_H")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return y, c


if __name__ == "__main__":
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(os.path.dirname(here), "uno", "section_data.h")
    y, c = write_header(out)
    print(f"записан {out}: точек {len(y)}, патчей {len(c)}, центры {c}, "
          f"радиус {min(y) / 1e5:.4f}..{max(y) / 1e5:.4f} мм")
