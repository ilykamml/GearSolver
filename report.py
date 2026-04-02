"""
Модуль фильтрации результатов и вывода таблицы в консоль.
"""

from typing import Optional
import math
from rich.console import Console
from rich.table import Table

from cli import GearInput
from optimizer import SolveResult


console = Console()


def filter_and_print(
    results: list[SolveResult],
    tolerance: float,
    top_n: int
) -> list[SolveResult]:
    """
    Отфильтровать результаты по допуску, отсортировать и вывести таблицу.
    
    Args:
        results: Список всех результатов оптимизации
        tolerance: Допустимое суммарное отклонение (мм)
        top_n: Количество топ-результатов для вывода
    
    Returns:
        Отфильтрованный и отсортированный список результатов
    """
    # Фильтрация
    filtered = [r for r in results if r.total_error <= tolerance]
    
    # Многоуровневая сортировка:
    # 1. По евклидовой норме смещения (sqrt(x₁² + x₂²))
    # 2. По приоритету стандарта (ГОСТ → DP → остальное)
    # 3. По ошибке
    def sort_key(r: SolveResult):
        # Евклидова норма смещения
        x2_val = r.x2 if r.x2 is not None else 0.0
        displacement_norm = math.sqrt(r.x1**2 + x2_val**2)
        
        # Приоритет стандарта: 0=ГОСТ (высший), 1=DP, 2=остальное
        if r.is_gost:
            priority = 0
        elif r.dp_label:
            priority = 1
        else:
            priority = 2
        
        return (displacement_norm, priority, r.total_error)
    
    filtered.sort(key=sort_key)
    
    # Вывод таблицы
    _print_table(filtered[:top_n])
    
    return filtered


def _print_table(results: list[SolveResult], gear_input: Optional[GearInput] = None) -> None:
    """
    Вывести таблицу результатов в консоль с помощью rich.
    """
    table = Table(title="GearSolver — Топ результатов", show_header=True, header_style="bold cyan")
    
    table.add_column("#", justify="right", width=3)
    table.add_column("m (мм)", justify="right", width=10)
    table.add_column("Стандарт", justify="center", width=12)
    table.add_column("x₁", justify="right", width=8)
    table.add_column("x₂", justify="right", width=8)
    table.add_column("hₐ*", justify="right", width=8)
    table.add_column("c*", justify="right", width=8)
    table.add_column("Ошибка (мм)", justify="right", width=12)
    
    for i, result in enumerate(results, 1):
        # Определить обозначение стандарта
        if result.is_gost:
            standard = "ГОСТ *"
        elif result.dp_label:
            standard = result.dp_label
        else:
            standard = "—"
        
        # Форматирование
        x2_str = f"{result.x2:.3f}" if result.x2 is not None else "—"
        
        table.add_row(
            str(i),
            f"{result.m:.3f}",
            standard,
            f"{result.x1:.3f}",
            x2_str,
            f"{result.ha_star:.3f}",
            f"{result.c_star:.3f}",
            f"{result.total_error:.3e}"
        )
    
    console.print(table)
    print()


def print_results(
    results: list[SolveResult],
    tolerance: float,
    top_n: int,
    gear_input: Optional[GearInput] = None
) -> list[SolveResult]:
    """
    Основная функция для фильтрации и вывода результатов.
    
    Args:
        results: Список результатов
        tolerance: Допуск
        top_n: Количество результатов для вывода
        gear_input: Входные параметры (опционально)
    
    Returns:
        Отфильтрованный список
    """
    filtered = filter_and_print(results, tolerance, top_n)
    return filtered
