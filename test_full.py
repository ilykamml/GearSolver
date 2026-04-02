#!/usr/bin/env python3
"""
Полный интеграционный тест GearSolver.
"""

import sys
from modules import build_module_pool
from cli import GearInput
from solver import run_parallel_solve
from report import filter_and_print
from config import TOLERANCE, TOP_N

def test_full_pipeline():
    """Полный тест пайплайна с параллелизацией."""
    print("=" * 70)
    print("GearSolver — Полный интеграционный тест (параллелизм)")
    print("=" * 70)
    
    # Входные данные: одна шестерня
    print("\n✓ Шаг 1: Ввод данных")
    gear = GearInput(
        da1=52.0,    # Диаметр вершин
        df1=46.0,    # Диаметр впадин
        z1=20,       # Число зубьев
        aw=0.0       # Нет межосевого расстояния
    )
    print(f"  Тип: одна шестерня")
    print(f"  da1={gear.da1}, df1={gear.df1}, z1={gear.z1}")
    
    # Построение пула модулей
    print("\n✓ Шаг 2: Построение пула модулей")
    modules = build_module_pool()
    print(f"  Всего модулей: {len(modules)}")
    print(f"  Диапазон: {modules[0]:.3f} - {modules[-1]:.3f} мм")
    
    # Параллельная оптимизация
    print("\n✓ Шаг 3: Параллельная оптимизация...")
    results = run_parallel_solve(modules, gear)
    print(f"  Завершено {len(results)} оптимизаций")
    
    # Статистика
    min_error = min(r.total_error for r in results)
    max_error = max(r.total_error for r in results)
    avg_error = sum(r.total_error for r in results) / len(results)
    print(f"  Статистика ошибок:")
    print(f"    Минимум: {min_error:.4f} мм")
    print(f"    Максимум: {max_error:.4f} мм")
    print(f"    Среднее: {avg_error:.4f} мм")
    
    # Фильтрация и вывод
    print(f"\n✓ Шаг 4: Фильтрация (допуск {TOLERANCE} мм) и вывод таблицы\n")
    filtered = filter_and_print(results, TOLERANCE, TOP_N)
    
    if filtered:
        print(f"\n✓ Найдено {len(filtered)} решений в пределах допуска")
        best = filtered[0]
        print(f"  Лучший результат:")
        print(f"    Модуль: {best.m:.3f} мм")
        print(f"    Смещение x1: {best.x1:.3f}")
        print(f"    ha*: {best.ha_star:.3f}")
        print(f"    c*: {best.c_star:.3f}")
        print(f"    Ошибка: {best.total_error:.4f} мм")
        if best.is_gost:
            print(f"    ✓ Совпадает с ГОСТ стандартом")
        if best.dp_label:
            print(f"    ✓ Совпадает с {best.dp_label}")
    else:
        print(f"⚠ Нет решений в пределах допуска {TOLERANCE} мм")
    
    print("\n" + "=" * 70)
    print("✓ Полный тест завершён успешно!")
    print("=" * 70 + "\n")

if __name__ == '__main__':
    try:
        test_full_pipeline()
    except Exception as e:
        print(f"\n✗ Ошибка: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
