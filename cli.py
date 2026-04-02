"""
Модуль парсинга CLI и интерактивного ввода данных.
"""

import argparse
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class GearInput:
    """Входные данные о шестернях."""
    da1: float          # Диаметр вершин шестерни 1
    df1: float          # Диаметр впадин шестерни 1
    z1: int             # Число зубьев шестерни 1
    da2: Optional[float] = None  # Диаметр вершин шестерни 2
    df2: Optional[float] = None  # Диаметр впадин шестерни 2
    z2: Optional[int] = None     # Число зубьев шестерни 2
    aw: float = 0.0     # Межосевое расстояние (0 = не задано)

    def is_pair(self) -> bool:
        """Проверить, является ли это парой шестерён."""
        return self.da2 is not None and self.z2 is not None


def parse_cli_args() -> Optional[GearInput]:
    """
    Парсить аргументы командной строки.
    
    Поддерживаемые сигнатуры:
      - python gear_calc.py da1 df1 z1 [aw]          # одна шестерня
      - python gear_calc.py da1 df1 z1 da2 df2 z2 [aw]  # пара
    
    Если аргументы не переданы, возвращает None для перехода в интерактивный режим.
    """
    # Проверяем наличие аргументов
    if len(sys.argv) == 1:
        return None
    
    parser = argparse.ArgumentParser(
        description="GearSolver — реверс-инжиниринг параметров зубчатых передач",
        add_help=True
    )
    
    # Добавляем позиционные аргументы как необязательные
    parser.add_argument('args', nargs='*', help='Аргументы для ввода')
    
    parsed = parser.parse_args()
    args = parsed.args
    
    if not args:
        return None
    
    try:
        if len(args) in (3, 4):
            # Одна шестерня: da1 df1 z1 [aw]
            aw = float(args[3]) if len(args) == 4 else 0.0
            return GearInput(
                da1=float(args[0]),
                df1=float(args[1]),
                z1=int(float(args[2])),
                aw=aw
            )
        elif len(args) in (6, 7):
            # Пара: da1 df1 z1 da2 df2 z2 [aw]
            aw = float(args[6]) if len(args) == 7 else 0.0
            return GearInput(
                da1=float(args[0]),
                df1=float(args[1]),
                z1=int(float(args[2])),
                da2=float(args[3]),
                df2=float(args[4]),
                z2=int(float(args[5])),
                aw=aw
            )
        else:
            print(f"Ошибка: ожидается 3-4 или 6-7 аргументов, получено {len(args)}")
            return None
    except ValueError as e:
        print(f"Ошибка парсинга аргументов: {e}")
        return None


def interactive_input() -> GearInput:
    """
    Пошаговый интерактивный ввод параметров шестерён.
    """
    print("\n=== GearSolver — Интерактивный режим ===\n")
    
    # Выбор количества шестерён
    while True:
        n_gears = input("Количество шестерён (1 или 2)? ").strip()
        if n_gears in ('1', '2'):
            n_gears = int(n_gears)
            break
        print("Пожалуйста, введите 1 или 2")
    
    print("\nДля каждого параметра введите значение или 0, если параметр неизвестен.\n")
    
    # Ввод параметров шестерни 1
    print("=== Шестерня 1 ===")
    da1 = _input_float("  da1 (диаметр вершин, мм): ")
    df1 = _input_float("  df1 (диаметр впадин, мм): ")
    z1 = _input_int("  z1 (число зубьев): ")
    
    if n_gears == 1:
        aw = _input_float("\naw (межосевое расстояние, мм, опционально): ")
        return GearInput(da1=da1, df1=df1, z1=z1, aw=aw)
    
    # Ввод параметров шестерни 2
    print("\n=== Шестерня 2 ===")
    da2 = _input_float("  da2 (диаметр вершин, мм): ")
    df2 = _input_float("  df2 (диаметр впадин, мм): ")
    z2 = _input_int("  z2 (число зубьев): ")
    aw = _input_float("\naw (межосевое расстояние, мм, опционально): ")
    
    return GearInput(da1=da1, df1=df1, z1=z1, da2=da2, df2=df2, z2=z2, aw=aw)


def _input_float(prompt: str) -> float:
    """Вспомогательная функция для ввода float."""
    while True:
        try:
            val = float(input(prompt))
            return val
        except ValueError:
            print("Пожалуйста, введите корректное число")


def _input_int(prompt: str) -> int:
    """Вспомогательная функция для ввода int."""
    while True:
        try:
            val = int(float(input(prompt)))
            if val > 0:
                return val
            elif val == 0:
                # Допускаем 0 как маркер неизвестного значения
                return 0
            else:
                print("Пожалуйста, введите положительное число")
        except ValueError:
            print("Пожалуйста, введите корректное число")
