"""
GearSolver — главный оркестратор для реверс-инжиниринга параметров зубчатых передач.

Использование:
  - CLI (одна шестерня):  python gear_calc.py da1 df1 z1 [aw]
  - CLI (пара):          python gear_calc.py da1 df1 z1 da2 df2 z2 [aw]
  - Интерактивно:        python gear_calc.py
"""

import sys
from io import TextIOWrapper

# Force UTF-8 output on Windows to support Unicode symbols
if isinstance(sys.stdout, TextIOWrapper) and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if isinstance(sys.stderr, TextIOWrapper) and sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

from cli import parse_cli_args, interactive_input
from modules import build_module_pool
from solver import run_parallel_solve
from report import print_results
from visualization import build_dashboard
from config import TOLERANCE, TOP_N


def main() -> None:
    """Главная функция оркестратора."""
    print("\n" + "=" * 60)
    print("           GearSolver — Реверс-инжиниринг ЗП")
    print("=" * 60 + "\n")
    
    # 1. Получить входные данные
    result = parse_cli_args()
    if result is None:
        gear_input = interactive_input()
        use_default_modules = False
    else:
        gear_input, use_default_modules = result
        if gear_input is None:
            gear_input = interactive_input()
    
    print(f"\n✓ Входные данные загружены")
    if gear_input.is_pair():
        print(f"  Тип: пара шестерён")
        print(f"  Шестерня 1: da1={gear_input.da1}, df1={gear_input.df1}, z1={gear_input.z1}")
        print(f"  Шестерня 2: da2={gear_input.da2}, df2={gear_input.df2}, z2={gear_input.z2}")
    else:
        print(f"  Тип: одна шестерня")
        print(f"  Шестерня: da1={gear_input.da1}, df1={gear_input.df1}, z1={gear_input.z1}")
    if gear_input.aw != 0:
        print(f"  Межосевое расстояние: aw={gear_input.aw}")
    
    # 2. Построить пул модулей
    print("\n✓ Формирование пула модулей...")
    modules = build_module_pool(default_only=use_default_modules)
    if use_default_modules:
        print(f"  Режим: только дефолтные модули (ГОСТ + DP)")
    print(f"  Всего модулей для проверки: {len(modules)}")
    
    # 3. Запустить параллельную оптимизацию
    print("\n✓ Оптимизация (мультипроцессинг)...")
    results = run_parallel_solve(modules, gear_input)
    print(f"  Завершено {len(results)} итераций")
    
    # 4. Фильтрация и вывод таблицы
    print(f"\n✓ Фильтрация по допуску {TOLERANCE} мм...\n")
    filtered = print_results(results, TOLERANCE, TOP_N, gear_input)
    
    if not filtered:
        print("⚠ Решений, удовлетворяющих допуску, не найдено.")
        print("  Попробуйте увеличить значение TOLERANCE в config.py")
        return
    
    # 5. Построить интерактивный дашборд (отключено)
    # print("✓ Генерация интерактивного дашборда Plotly...")
    # build_dashboard(results, gear_input, "gear_results.html")
    
    print("=" * 60)
    print("✓ Анализ завершён успешно!")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠ Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n✗ Ошибка: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
