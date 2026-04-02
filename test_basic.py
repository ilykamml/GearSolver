#!/usr/bin/env python3
"""
Простой тест для проверки базовой функциональности GearSolver.
"""

import sys
from config import GOST_MODULES, DP_PITCHES, TOLERANCE, TOP_N
from modules import build_module_pool
from cli import GearInput
from optimizer import optimize_for_module

def test_basic():
    """Тест базовой функциональности."""
    print("=" * 60)
    print("GearSolver — Базовый тест функциональности")
    print("=" * 60)
    
    # Тест 1: Построение пула модулей
    print("\n✓ Тест 1: Построение пула модулей")
    modules = build_module_pool()
    print(f"  Всего модулей: {len(modules)}")
    print(f"  Первые 10: {modules[:10]}")
    print(f"  ГОСТ модули в пуле: {sum(1 for m in modules if m in GOST_MODULES)}")
    assert len(modules) > 0, "Пул модулей пуст!"
    
    # Тест 2: Одна шестерня
    print("\n✓ Тест 2: Оптимизация для одной шестерни")
    gear1 = GearInput(da1=50.0, df1=45.0, z1=20)
    result1 = optimize_for_module(2.0, gear1)
    print(f"  Модуль: {result1.m}")
    print(f"  x1: {result1.x1:.3f}")
    print(f"  ha*: {result1.ha_star:.3f}")
    print(f"  c*: {result1.c_star:.3f}")
    print(f"  Ошибка: {result1.total_error:.4f} мм")
    print(f"  ГОСТ: {result1.is_gost}, DP: {result1.dp_label}")
    assert result1.total_error >= 0, "Ошибка не может быть отрицательной!"
    
    # Тест 3: Пара шестерён
    print("\n✓ Тест 3: Оптимизация для пары шестерён")
    gear2 = GearInput(
        da1=50.0, df1=45.0, z1=20,
        da2=100.0, df2=95.0, z2=40,
        aw=0.0
    )
    result2 = optimize_for_module(2.0, gear2)
    print(f"  Модуль: {result2.m}")
    print(f"  x1: {result2.x1:.3f}, x2: {result2.x2:.3f}")
    print(f"  ha*: {result2.ha_star:.3f}")
    print(f"  c*: {result2.c_star:.3f}")
    print(f"  Ошибка: {result2.total_error:.4f} мм")
    assert result2.x2 is not None, "x2 должно быть определено для пары!"
    
    # Тест 4: Маркировка стандартов
    print("\n✓ Тест 4: Маркировка стандартов")
    result_gost = optimize_for_module(1.0, gear1)
    print(f"  m=1.0 -> ГОСТ: {result_gost.is_gost}")
    result_dp = optimize_for_module(6.35, gear1)  # 25.4/4 = 6.35 DP4
    print(f"  m=6.35 -> DP: {result_dp.dp_label}")
    
    print("\n" + "=" * 60)
    print("✓ Все тесты пройдены успешно!")
    print("=" * 60)

if __name__ == '__main__':
    try:
        test_basic()
    except Exception as e:
        print(f"\n✗ Ошибка теста: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
