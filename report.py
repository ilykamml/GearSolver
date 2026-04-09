"""
Модуль фильтрации результатов и вывода таблицы в консоль и файл.
"""

from typing import Optional, Callable
import math
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from cli import GearInput
from optimizer import SolveResult
from config import MEASUREMENT_TOLERANCE, X_BOUNDS


console = Console(width=240)

X_BOUND_LIMIT = abs(X_BOUNDS[1]) * 0.90  # 90% от границы = подозрительное решение


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _calc_diameters(
    r: SolveResult,
    gear_input: GearInput,
) -> tuple[float, float, Optional[float], Optional[float]]:
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
    """True если x1 или x2 близки к границе bounds."""
    if abs(r.x1) >= X_BOUND_LIMIT:
        return True
    if r.x2 is not None and abs(r.x2) >= X_BOUND_LIMIT:
        return True
    return False


# ---------------------------------------------------------------------------
# Ranking keys
# ---------------------------------------------------------------------------

def _std_priority(r: SolveResult) -> int:
    return 0 if r.is_gost else (1 if r.dp_label else 2)


def _disp_norm(r: SolveResult) -> float:
    x2_val = r.x2 if r.x2 is not None else 0.0
    return math.sqrt(r.x1 ** 2 + x2_val ** 2)


def _rank_key_error(r: SolveResult) -> tuple:
    return (
        1 if _at_bound(r) else 0,
        r.weighted_error,
        r.total_error,
        _std_priority(r),
        _disp_norm(r),
    )


def _rank_key_confidence(r: SolveResult) -> tuple:
    return (
        1 if _at_bound(r) else 0,
        -r.confidence,
        r.weighted_error,
        r.total_error,
        _std_priority(r),
        _disp_norm(r),
    )


def _rank_key_hybrid(r: SolveResult) -> tuple:
    # lower score is better
    hybrid_score = (1.0 - r.confidence) + (r.weighted_error / max(MEASUREMENT_TOLERANCE, 1e-6))
    return (
        1 if _at_bound(r) else 0,
        hybrid_score,
        r.weighted_error,
        r.total_error,
        _std_priority(r),
        _disp_norm(r),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def filter_and_print(
    results: list[SolveResult],
    tolerance: float,
    top_n: int,
    gear_input: Optional[GearInput] = None,
) -> list[SolveResult]:
    """
    Фильтрация по геометрическому допуску и печать 3 таблиц:
      1) error-based,
      2) confidence-based,
      3) hybrid.

    Возвращает список, отсортированный по error-based (для обратной совместимости).
    """
    filtered = [r for r in results if r.total_error <= tolerance]

    error_sorted = sorted(filtered, key=_rank_key_error)
    conf_sorted = sorted(filtered, key=_rank_key_confidence)
    hybrid_sorted = sorted(filtered, key=_rank_key_hybrid)

    _print_table(error_sorted[:top_n], gear_input, title="GearSolver — Топ (error-based)")
    _print_table(conf_sorted[:top_n], gear_input, title="GearSolver — Топ (confidence-based)")
    _print_table(hybrid_sorted[:top_n], gear_input, title="GearSolver — Топ (hybrid)")

    return error_sorted


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

def _format_table_md(
    results: list[SolveResult],
    gear_input: Optional[GearInput] = None,
) -> str:
    """Форматировать таблицу результатов в Markdown."""
    is_pair = gear_input is not None and gear_input.is_pair()

    cols = [
        "#",
        "m (мм)",
        "Стандарт",
        "Этап",
        "x₁",
        "x₂",
        "hₐ*",
        "c*",
        "fillet",
        "da₁расч",
        "df₁расч",
    ]
    if is_pair:
        cols.extend(["da₂расч", "df₂расч", "awрасч"])
    cols.extend(
        [
            "s_tip1",
            "s_root1",
            "s_tip2",
            "s_root2",
            "RMSE",
            "wRMSE",
            "conf",
        ]
    )

    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]

    for i, r in enumerate(results, 1):
        if r.is_gost:
            standard = "ГОСТ ✓"
        elif r.dp_label:
            standard = r.dp_label
        else:
            standard = "—"

        stage_str = "1" if r.stage == 1 else "2"
        x2_str = f"{r.x2:.3f}" if r.x2 is not None else "—"

        if gear_input is not None:
            da1c, df1c, da2c, df2c = _calc_diameters(r, gear_input)
            da1_str = f"{da1c:.3f}"
            df1_str = f"{df1c:.3f}"
            da2_str = f"{da2c:.3f}" if da2c is not None else "—"
            df2_str = f"{df2c:.3f}" if df2c is not None else "—"
        else:
            da1_str = df1_str = da2_str = df2_str = "—"

        aw_str = f"{r.aw_calc:.3f}" if r.aw_calc is not None else "—"

        row = [
            str(i),
            f"{r.m:.3f}",
            standard,
            stage_str,
            f"{r.x1:.3f}",
            x2_str,
            f"{r.ha_star:.3f}",
            f"{r.c_star:.3f}",
            f"{r.root_fillet_coeff:.3f}",
            da1_str,
            df1_str,
        ]

        if is_pair:
            row.extend([da2_str, df2_str, aw_str])

        row.extend(
            [
                f"{r.tooth_thickness_tip1:.3f}" if r.tooth_thickness_tip1 is not None else "—",
                f"{r.tooth_thickness_root1:.3f}" if r.tooth_thickness_root1 is not None else "—",
                f"{r.tooth_thickness_tip2:.3f}" if r.tooth_thickness_tip2 is not None else "—",
                f"{r.tooth_thickness_root2:.3f}" if r.tooth_thickness_root2 is not None else "—",
                f"{r.total_error:.3e}",
                f"{r.weighted_error:.3e}",
                f"{r.confidence:.4f}",
            ]
        )

        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Console table
# ---------------------------------------------------------------------------

def _print_table(
    results: list[SolveResult],
    gear_input: Optional[GearInput] = None,
    title: str = "GearSolver — Топ результатов",
) -> None:
    """Вывести таблицу результатов в консоль с помощью rich."""
    is_pair = gear_input is not None and gear_input.is_pair()

    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
        expand=False,
        padding=(0, 1),
    )

    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("m", justify="right", no_wrap=True)
    table.add_column("Стандарт", justify="center", no_wrap=True)
    table.add_column("Этап", justify="center", no_wrap=True)
    table.add_column("x₁", justify="right", no_wrap=True)
    table.add_column("x₂", justify="right", no_wrap=True)
    table.add_column("hₐ*", justify="right", no_wrap=True)
    table.add_column("c*", justify="right", no_wrap=True)
    table.add_column("fillet", justify="right", no_wrap=True)

    table.add_column("da₁расч", justify="right", no_wrap=True)
    table.add_column("df₁расч", justify="right", no_wrap=True)
    if is_pair:
        table.add_column("da₂расч", justify="right", no_wrap=True)
        table.add_column("df₂расч", justify="right", no_wrap=True)
        table.add_column("awрасч", justify="right", no_wrap=True)

    table.add_column("s_tip1", justify="right", no_wrap=True)
    table.add_column("s_root1", justify="right", no_wrap=True)
    table.add_column("s_tip2", justify="right", no_wrap=True)
    table.add_column("s_root2", justify="right", no_wrap=True)
    table.add_column("RMSE", justify="right", no_wrap=True)
    table.add_column("wRMSE", justify="right", no_wrap=True)
    table.add_column("conf", justify="right", no_wrap=True)

    for i, r in enumerate(results, 1):
        if r.is_gost:
            standard = "[green]ГОСТ ✓[/green]"
        elif r.dp_label:
            standard = f"[cyan]{r.dp_label}[/cyan]"
        else:
            standard = "—"

        stage_str = "[green]1[/green]" if r.stage == 1 else "[yellow]2[/yellow]"
        x2_str = f"{r.x2:.3f}" if r.x2 is not None else "—"

        err_str = f"[green]{r.total_error:.3e}[/green]" if r.total_error <= MEASUREMENT_TOLERANCE else f"{r.total_error:.3e}"

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
            f"{r.root_fillet_coeff:.3f}",
            da1_str,
            df1_str,
        ]

        if is_pair:
            row.extend([da2_str, df2_str, f"{r.aw_calc:.3f}" if r.aw_calc is not None else "—"])

        row.extend(
            [
                f"{r.tooth_thickness_tip1:.3f}" if r.tooth_thickness_tip1 is not None else "—",
                f"{r.tooth_thickness_root1:.3f}" if r.tooth_thickness_root1 is not None else "—",
                f"{r.tooth_thickness_tip2:.3f}" if r.tooth_thickness_tip2 is not None else "—",
                f"{r.tooth_thickness_root2:.3f}" if r.tooth_thickness_root2 is not None else "—",
                err_str,
                f"{r.weighted_error:.3e}",
                f"{r.confidence:.4f}",
            ]
        )

        table.add_row(*row)

    console.print(table)
    print()


# ---------------------------------------------------------------------------
# Save report
# ---------------------------------------------------------------------------

def _save_report_to_file(
    results: list[SolveResult],
    gear_input: GearInput,
    tolerance: float,
    top_n: int,
) -> None:
    """Сохранить отчёт в файл Markdown."""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if gear_input.is_pair():
        params = (
            f"da1_{gear_input.da1}_df1_{gear_input.df1}_z1_{gear_input.z1}_"
            f"da2_{gear_input.da2}_df2_{gear_input.df2}_z2_{gear_input.z2}"
        )
    else:
        params = f"da1_{gear_input.da1}_df1_{gear_input.df1}_z1_{gear_input.z1}"

    if gear_input.aw != 0:
        params += f"_aw_{gear_input.aw}"

    filepath = reports_dir / f"report_{params}_{timestamp}.md"

    filtered = [r for r in results if r.total_error <= tolerance]
    error_sorted = sorted(filtered, key=_rank_key_error)
    conf_sorted = sorted(filtered, key=_rank_key_confidence)
    hybrid_sorted = sorted(filtered, key=_rank_key_hybrid)

    md_content: list[str] = []
    md_content.append("# GearSolver — Отчёт анализа\n")
    md_content.append(f"**Дата и время:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    md_content.append("## Входные данные\n")
    if gear_input.is_pair():
        md_content.append("- **Тип:** Пара шестерён\n")
        md_content.append(f"- **Шестерня 1:** da1={gear_input.da1}, df1={gear_input.df1}, z1={gear_input.z1}\n")
        md_content.append(f"- **Шестерня 2:** da2={gear_input.da2}, df2={gear_input.df2}, z2={gear_input.z2}\n")
    else:
        md_content.append("- **Тип:** Одна шестерня\n")
        md_content.append(f"- **Шестерня:** da1={gear_input.da1}, df1={gear_input.df1}, z1={gear_input.z1}\n")

    if gear_input.aw != 0:
        md_content.append(f"- **Межосевое расстояние:** aw={gear_input.aw}\n")

    if gear_input.measurement_stats:
        md_content.append("\n## Статистика измерений\n")
        for field, stat in gear_input.measurement_stats.items():
            md_content.append(
                f"- **{field}**: n={int(stat.get('n', 1))}, used={int(stat.get('n_used', 1))}, "
                f"median={stat.get('median', 0.0):.4f}, mean={stat.get('mean', 0.0):.4f}, std={stat.get('std', 0.0):.4f}\n"
            )

    md_content.append("\n## Параметры анализа\n")
    md_content.append(f"- **Допуск:** {tolerance} мм\n")
    md_content.append(f"- **Топ результатов:** {top_n}\n")

    md_content.append("\n## Ранжирование: error-based\n")
    md_content.append(_format_table_md(error_sorted[:top_n], gear_input) if error_sorted else "Нет решений в допуске.\n")

    md_content.append("\n\n## Ранжирование: confidence-based\n")
    md_content.append(_format_table_md(conf_sorted[:top_n], gear_input) if conf_sorted else "Нет решений в допуске.\n")

    md_content.append("\n\n## Ранжирование: hybrid\n")
    md_content.append(_format_table_md(hybrid_sorted[:top_n], gear_input) if hybrid_sorted else "Нет решений в допуске.\n")

    md_content.append(f"\n\n**Найдено решений в допуске:** {len(filtered)}\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(md_content))

    print(f"✓ Отчёт сохранён: {filepath}")


def print_results(
    results: list[SolveResult],
    tolerance: float,
    top_n: int,
    gear_input: Optional[GearInput] = None,
) -> list[SolveResult]:
    """Основная функция фильтрации/вывода результатов."""
    filtered = filter_and_print(results, tolerance, top_n, gear_input)

    if gear_input is not None:
        _save_report_to_file(results, gear_input, tolerance, top_n)

    return filtered
