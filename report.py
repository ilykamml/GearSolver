"""
Модуль фильтрации результатов и вывода таблицы в консоль и файл.
"""

from typing import Optional
import math
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.table import Table

from cli import GearInput
from optimizer import SolveResult
from config import MEASUREMENT_TOLERANCE, X_BOUNDS


console = Console(width=200)

X_BOUND_LIMIT = abs(X_BOUNDS[1]) * 0.90  # 90% от границы = подозрительное решение


def _calc_diameters(r: SolveResult, gear_input: GearInput) -> tuple[float, float, Optional[float], Optional[float]]:
    """Вычислить расчётные da/df для шестерён по найденным параметрам."""
    m, ha, c, x1 = r.m, r.ha_star, r.c_star, r.x1
    da1 = m * (gear_input.z1 + 2 * ha + 2 * x1)
    df1 = m * (gear_input.z1 - 2 * (ha + c) + 2 * x1)
    da2, df2 = None, None
    if r.x2 is not None and gear_input.z2 is not None:
        da2 = m * (gear_input.z2 + 2 * ha + 2 * r.x2)
        df2 = m * (gear_input.z2 - 2 * (ha + c) + 2 * r.x2)
    return da1, df1, da2, df2


def _at_bound(r: SolveResult) -> bool:
    """True если x1 или x2 достигли границы bounds."""
    if abs(r.x1) >= X_BOUND_LIMIT:
        return True
    if r.x2 is not None and abs(r.x2) >= X_BOUND_LIMIT:
        return True
    return False


def filter_and_print(
    results: list[SolveResult],
    tolerance: float,
    top_n: int,
    gear_input: Optional[GearInput] = None,
) -> list[SolveResult]:
    """
    Отфильтровать результаты по допуску, отсортировать и вывести таблицу.

    Сортировка:
      1. Решения с x на границе bounds (|x| >= 97% от X_BOUNDS) — в конец.
      2. Основной критерий: RMSE (меньше = лучше).
      3. При равной RMSE: stage=1 > stage=2, ГОСТ > DP > прочее, меньше |x|.
    """
    filtered = [r for r in results if r.total_error <= tolerance]

    def sort_key(r: SolveResult):
        x2_val = r.x2 if r.x2 is not None else 0.0
        displacement_norm = math.sqrt(r.x1 ** 2 + x2_val ** 2)
        at_bound = 1 if _at_bound(r) else 0
        std_priority = 0 if r.is_gost else (1 if r.dp_label else 2)

        # For ranking: penalize stage=2 by adding MEASUREMENT_TOLERANCE to its error.
        # This means stage=2 only wins if its geometric error is significantly better
        # than stage=1 (by more than the measurement uncertainty).
        ranking_error = r.total_error + (MEASUREMENT_TOLERANCE if r.stage == 2 else 0.0)

        return (at_bound, ranking_error, std_priority, displacement_norm)

    filtered.sort(key=sort_key)
    _print_table(filtered[:top_n], gear_input)
    return filtered


def _format_table_md(results: list[SolveResult], gear_input: Optional[GearInput] = None) -> str:
    """Форматировать таблицу результатов в Markdown."""
    is_pair = gear_input is not None and gear_input.is_pair()
    
    lines = []
    
    # Заголовок таблицы
    header = "| # | m (мм) | Стандарт | Этап | x₁ | x₂ | hₐ* | c* | da₁расч | df₁расч |"
    if is_pair:
        header += " da₂расч | df₂расч |"
    header += " RMSE (мм) |"
    lines.append(header)
    
    # Разделитель
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    if is_pair:
        sep += "---|---|"
    sep += "---|"
    lines.append(sep)
    
    # Строки данных
    for i, r in enumerate(results, 1):
        if r.is_gost:
            standard = "ГОСТ ✓"
        elif r.dp_label:
            standard = r.dp_label
        else:
            standard = "—"
        
        stage_str = "1" if r.stage == 1 else "2"
        x2_str = f"{r.x2:.3f}" if r.x2 is not None else "—"
        
        # Расчётные диаметры
        if gear_input is not None:
            da1c, df1c, da2c, df2c = _calc_diameters(r, gear_input)
            da1_str = f"{da1c:.3f}"
            df1_str = f"{df1c:.3f}"
            da2_str = f"{da2c:.3f}" if da2c is not None else "—"
            df2_str = f"{df2c:.3f}" if df2c is not None else "—"
        else:
            da1_str = df1_str = da2_str = df2_str = "—"
        
        row = f"| {i} | {r.m:.3f} | {standard} | {stage_str} | {r.x1:.3f} | {x2_str} | {r.ha_star:.3f} | {r.c_star:.3f} | {da1_str} | {df1_str} |"
        if is_pair:
            row += f" {da2_str} | {df2_str} |"
        row += f" {r.total_error:.3e} |"
        lines.append(row)
    
    return "\n".join(lines)


def _print_table(results: list[SolveResult], gear_input: Optional[GearInput] = None) -> None:
    """Вывести таблицу результатов в консоль с помощью rich."""
    is_pair = gear_input is not None and gear_input.is_pair()

    table = Table(
        title="GearSolver — Топ результатов",
        show_header=True,
        header_style="bold cyan",
        expand=False,
        padding=(0, 1),
    )

    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("m (мм)", justify="right", no_wrap=True)
    table.add_column("Стандарт", justify="center", no_wrap=True)
    table.add_column("Этап", justify="center", no_wrap=True)
    table.add_column("x₁", justify="right", no_wrap=True)
    table.add_column("x₂", justify="right", no_wrap=True)
    table.add_column("hₐ*", justify="right", no_wrap=True)
    table.add_column("c*", justify="right", no_wrap=True)
    # Расчётные диаметры
    table.add_column("da₁расч", justify="right", no_wrap=True)
    table.add_column("df₁расч", justify="right", no_wrap=True)
    if is_pair:
        table.add_column("da₂расч", justify="right", no_wrap=True)
        table.add_column("df₂расч", justify="right", no_wrap=True)
    table.add_column("RMSE (мм)", justify="right", no_wrap=True)

    for i, r in enumerate(results, 1):
        if r.is_gost:
            standard = "[green]ГОСТ ✓[/green]"
        elif r.dp_label:
            standard = f"[cyan]{r.dp_label}[/cyan]"
        else:
            standard = "—"

        stage_str = "[green]1[/green]" if r.stage == 1 else "[yellow]2[/yellow]"
        x2_str = f"{r.x2:.3f}" if r.x2 is not None else "—"

        if r.total_error <= MEASUREMENT_TOLERANCE:
            err_str = f"[green]{r.total_error:.3e}[/green]"
        else:
            err_str = f"{r.total_error:.3e}"

        # Расчётные диаметры
        if gear_input is not None:
            da1c, df1c, da2c, df2c = _calc_diameters(r, gear_input)
            da1_str = f"{da1c:.3f}"
            df1_str = f"{df1c:.3f}"
            da2_str = f"{da2c:.3f}" if da2c is not None else "—"
            df2_str = f"{df2c:.3f}" if df2c is not None else "—"
        else:
            da1_str = df1_str = da2_str = df2_str = "—"

        row = [
            str(i),
            f"{r.m:.3f}",
            standard,
            stage_str,
            f"{r.x1:.3f}",
            x2_str,
            f"{r.ha_star:.3f}",
            f"{r.c_star:.3f}",
            da1_str,
            df1_str,
        ]
        if is_pair:
            row += [da2_str, df2_str]
        row.append(err_str)

        table.add_row(*row)

    console.print(table)
    print()


def _save_report_to_file(
    results: list[SolveResult],
    gear_input: GearInput,
    tolerance: float,
    top_n: int,
) -> None:
    """Сохранить отчёт в файл Markdown."""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    # Формируем имя файла с входными данными и датой/временем
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if gear_input.is_pair():
        params = f"da1_{gear_input.da1}_df1_{gear_input.df1}_z1_{gear_input.z1}_da2_{gear_input.da2}_df2_{gear_input.df2}_z2_{gear_input.z2}"
    else:
        params = f"da1_{gear_input.da1}_df1_{gear_input.df1}_z1_{gear_input.z1}"
    
    if gear_input.aw != 0:
        params += f"_aw_{gear_input.aw}"
    
    filename = f"report_{params}_{timestamp}.md"
    filepath = reports_dir / filename
    
    # Формируем содержимое отчёта
    md_content = []
    md_content.append("# GearSolver — Отчёт анализа\n")
    md_content.append(f"**Дата и время:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    md_content.append("## Входные данные\n")
    if gear_input.is_pair():
        md_content.append(f"- **Тип:** Пара шестерён\n")
        md_content.append(f"- **Шестерня 1:** da1={gear_input.da1}, df1={gear_input.df1}, z1={gear_input.z1}\n")
        md_content.append(f"- **Шестерня 2:** da2={gear_input.da2}, df2={gear_input.df2}, z2={gear_input.z2}\n")
    else:
        md_content.append(f"- **Тип:** Одна шестерня\n")
        md_content.append(f"- **Шестерня:** da1={gear_input.da1}, df1={gear_input.df1}, z1={gear_input.z1}\n")
    
    if gear_input.aw != 0:
        md_content.append(f"- **Межосевое расстояние:** aw={gear_input.aw}\n")
    
    md_content.append(f"\n## Параметры анализа\n")
    md_content.append(f"- **Допуск:** {tolerance} мм\n")
    md_content.append(f"- **Топ результатов:** {top_n}\n")
    
    md_content.append(f"\n## Результаты\n")
    filtered = [r for r in results if r.total_error <= tolerance]
    filtered.sort(key=lambda r: (1 if _at_bound(r) else 0, r.total_error, 0 if r.is_gost else (1 if r.dp_label else 2)))
    
    if filtered:
        md_content.append(_format_table_md(filtered[:top_n], gear_input))
        md_content.append(f"\n\n**Найдено решений:** {len(filtered)}\n")
    else:
        md_content.append("⚠ Решений, удовлетворяющих допуску, не найдено.\n")
    
    # Записываем в файл
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(md_content))
    
    print(f"✓ Отчёт сохранён: {filepath}")


def print_results(
    results: list[SolveResult],
    tolerance: float,
    top_n: int,
    gear_input: Optional[GearInput] = None,
) -> list[SolveResult]:
    """Основная функция для фильтрации и вывода результатов."""
    filtered = filter_and_print(results, tolerance, top_n, gear_input)
    
    # Сохраняем отчёт в файл
    if gear_input is not None:
        _save_report_to_file(results, gear_input, tolerance, top_n)
    
    return filtered
