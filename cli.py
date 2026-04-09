"""
Модуль парсинга CLI и интерактивного ввода данных.
"""

import argparse
import math
import statistics
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GearInput:
    """Входные данные о шестернях."""
    da1: float          # Диаметр вершин шестерни 1
    df1: float          # Диаметр впадин шестерни 1
    z1: int             # Число зубьев шестерни 1

    # Измеренные толщины зуба (0 = неизвестно)
    s_tip1: float = 0.0
    s_root1: float = 0.0

    da2: Optional[float] = None  # Диаметр вершин шестерни 2
    df2: Optional[float] = None  # Диаметр впадин шестерни 2
    z2: Optional[int] = None     # Число зубьев шестерни 2
    s_tip2: Optional[float] = None
    s_root2: Optional[float] = None

    aw: float = 0.0              # Межосевое расстояние (0 = не задано)

    # Статистика по множественным измерениям (для отчёта)
    measurement_stats: dict[str, dict[str, float]] = field(default_factory=dict)

    def is_pair(self) -> bool:
        """Проверить, является ли это парой шестерён."""
        return self.da2 is not None and self.z2 is not None


def _parse_float_token(token: str) -> float:
    """Parse float token with support for decimal comma."""
    return float(token.strip().replace(',', '.'))


def _parse_float_sequence(raw: str) -> list[float]:
    """Parse a space-separated list of numbers with dot/comma decimal separator."""
    parts = [p for p in raw.strip().split() if p]
    if not parts:
        raise ValueError("empty input")
    return [_parse_float_token(p) for p in parts]


def _robust_stats(values: list[float]) -> tuple[float, dict[str, float]]:
    """
    Robust aggregate: MAD-based outlier filtering + median representative value.
    """
    if not values:
        raise ValueError("empty values")

    original_count = len(values)
    sorted_vals = sorted(values)
    median_val = statistics.median(sorted_vals)

    if len(values) >= 3:
        deviations = [abs(v - median_val) for v in values]
        mad = statistics.median(deviations)
        if mad > 0:
            robust_sigma = 1.4826 * mad
            threshold = 3.0 * robust_sigma
            filtered = [v for v in values if abs(v - median_val) <= threshold]
            if not filtered:
                filtered = values
        else:
            filtered = values
    else:
        filtered = values

    rep = statistics.median(filtered)
    mean_val = statistics.fmean(filtered)
    std_val = statistics.pstdev(filtered) if len(filtered) > 1 else 0.0

    stats = {
        "n": float(original_count),
        "n_used": float(len(filtered)),
        "median": float(rep),
        "mean": float(mean_val),
        "std": float(std_val),
        "min": float(min(filtered)),
        "max": float(max(filtered)),
    }
    return float(rep), stats


def _input_float_multi(prompt: str, field_name: str, allow_zero: bool = True) -> tuple[float, dict[str, float]]:
    """Read one or multiple float measurements, aggregate robustly."""
    while True:
        raw = input(prompt).strip()
        try:
            values = _parse_float_sequence(raw)
            if not allow_zero and any(v <= 0 for v in values):
                print("Пожалуйста, вводите только положительные значения")
                continue

            rep, stats = _robust_stats(values)
            if rep == 0 and not allow_zero:
                print("Пожалуйста, вводите только положительные значения")
                continue

            if len(values) > 1:
                print(
                    f"    -> {field_name}: median={stats['median']:.4f}, "
                    f"mean={stats['mean']:.4f}, std={stats['std']:.4f}, "
                    f"использовано {int(stats['n_used'])}/{int(stats['n'])}"
                )
            return rep, stats
        except ValueError:
            print("Пожалуйста, введите число или несколько чисел через пробел (поддержка 50.2 и 50,2)")


def _input_int_multi(prompt: str) -> int:
    """Read one or multiple integer-like values and return robust rounded median."""
    while True:
        raw = input(prompt).strip()
        try:
            values = _parse_float_sequence(raw)
            rep, _ = _robust_stats(values)
            val = int(round(rep))
            if val > 0 or val == 0:
                return val
            print("Пожалуйста, введите положительное число")
        except ValueError:
            print("Пожалуйста, введите корректное число")


def parse_cli_args() -> tuple[Optional[GearInput], bool]:
    """
    Парсить аргументы командной строки.

    Поддерживаемые сигнатуры:
      - python gear_calc.py da1 df1 z1 [aw]               # одна шестерня
      - python gear_calc.py da1 df1 z1 da2 df2 z2 [aw]    # пара
      - python gear_calc.py -d ...                        # только ГОСТ+DP

    В CLI принимается по одному значению на параметр.
    """
    if len(sys.argv) == 1:
        return None, False

    parser = argparse.ArgumentParser(
        description="GearSolver — реверс-инжиниринг параметров зубчатых передач",
        add_help=True
    )

    parser.add_argument('-d', '--default', action='store_true',
                        help='Использовать только дефолтные модули (ГОСТ и DP)')
    parser.add_argument('args', nargs='*', help='Аргументы для ввода')

    parsed = parser.parse_args()
    args = parsed.args
    use_default = parsed.default

    if not args:
        return None, use_default

    try:
        if len(args) in (3, 4):
            aw = _parse_float_token(args[3]) if len(args) == 4 else 0.0
            return GearInput(
                da1=_parse_float_token(args[0]),
                df1=_parse_float_token(args[1]),
                z1=int(round(_parse_float_token(args[2]))),
                aw=aw
            ), use_default
        elif len(args) in (6, 7):
            aw = _parse_float_token(args[6]) if len(args) == 7 else 0.0
            return GearInput(
                da1=_parse_float_token(args[0]),
                df1=_parse_float_token(args[1]),
                z1=int(round(_parse_float_token(args[2]))),
                da2=_parse_float_token(args[3]),
                df2=_parse_float_token(args[4]),
                z2=int(round(_parse_float_token(args[5]))),
                aw=aw
            ), use_default
        else:
            print(f"Ошибка: ожидается 3-4 или 6-7 аргументов, получено {len(args)}")
            return None, use_default
    except ValueError as e:
        print(f"Ошибка парсинга аргументов: {e}")
        return None, use_default


def interactive_input() -> GearInput:
    """Пошаговый интерактивный ввод параметров шестерён."""
    print("\n=== GearSolver — Интерактивный режим ===\n")

    while True:
        n_gears = input("Количество шестерён (1 или 2)? ").strip()
        if n_gears in ('1', '2'):
            n_gears = int(n_gears)
            break
        print("Пожалуйста, введите 1 или 2")

    print("\nДля каждого параметра можно ввести несколько замеров через пробел.")
    print("Поддерживаются десятичные разделители '.' и ','; 0 = параметр неизвестен.\n")

    stats: dict[str, dict[str, float]] = {}

    print("=== Шестерня 1 ===")
    da1, stats['da1'] = _input_float_multi("  da1 (диаметр вершин, мм): ", "da1")
    df1, stats['df1'] = _input_float_multi("  df1 (диаметр впадин, мм): ", "df1")
    z1 = _input_int_multi("  z1 (число зубьев): ")

    st1, stats['s_tip1'] = _input_float_multi(
        "  s_tip1 (толщина вершины зуба, мм, 0 если неизвестно): ",
        "s_tip1",
    )
    sr1, stats['s_root1'] = _input_float_multi(
        "  s_root1 (толщина у основания зуба, мм, 0 если неизвестно): ",
        "s_root1",
    )

    if n_gears == 1:
        aw, stats['aw'] = _input_float_multi("\naw (межосевое расстояние, мм, опционально): ", "aw")
        return GearInput(
            da1=da1,
            df1=df1,
            z1=z1,
            s_tip1=st1,
            s_root1=sr1,
            aw=aw,
            measurement_stats=stats,
        )

    print("\n=== Шестерня 2 ===")
    da2, stats['da2'] = _input_float_multi("  da2 (диаметр вершин, мм): ", "da2")
    df2, stats['df2'] = _input_float_multi("  df2 (диаметр впадин, мм): ", "df2")
    z2 = _input_int_multi("  z2 (число зубьев): ")
    st2, stats['s_tip2'] = _input_float_multi(
        "  s_tip2 (толщина вершины зуба, мм, 0 если неизвестно): ",
        "s_tip2",
    )
    sr2, stats['s_root2'] = _input_float_multi(
        "  s_root2 (толщина у основания зуба, мм, 0 если неизвестно): ",
        "s_root2",
    )
    aw, stats['aw'] = _input_float_multi("\naw (межосевое расстояние, мм, опционально): ", "aw")

    return GearInput(
        da1=da1,
        df1=df1,
        z1=z1,
        s_tip1=st1,
        s_root1=sr1,
        da2=da2,
        df2=df2,
        z2=z2,
        s_tip2=st2,
        s_root2=sr2,
        aw=aw,
        measurement_stats=stats,
    )
