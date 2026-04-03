"""
Модуль математической модели и оптимизации параметров зубчатых передач.

Two-stage search strategy:
  Stage 1: fix ha*=1.0, c*=0.25 (standard), optimize only x1 [x2].
           This is the physically correct solution for standard gears.
  Stage 2: if stage-1 RMSE > STAGE1_THRESHOLD, free ha* and c* with
           regularization penalty to stay close to standard values.
"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from scipy.optimize import least_squares

from cli import GearInput
from config import (
    X_BOUNDS, HA_BOUNDS, C_BOUNDS,
    GOST_MODULES, DP_PITCHES, STANDARD_MATCH_TOLERANCE,
    REGULARIZATION_WEIGHT, STAGE1_THRESHOLD,
)

# Standard values for stage-1 fixed search
HA_STAR_STD = 1.0
C_STAR_STD = 0.25


@dataclass
class SolveResult:
    """Результат оптимизации для одного модуля."""
    m: float
    x1: float
    x2: Optional[float] = None
    ha_star: float = 0.0
    c_star: float = 0.0
    total_error: float = 0.0      # Геометрическая RMSE (мм), без штрафа регуляризации
    is_gost: bool = False
    dp_label: Optional[str] = None
    stage: int = 1                # 1 = standard ha*/c*, 2 = free ha*/c*


def optimize_for_module(m: float, gear_input: GearInput) -> SolveResult:
    """
    Двухэтапная оптимизация для заданного модуля.

    Stage 1: ha*=1.0, c*=0.25 фиксированы → ищем только x1 [x2].
    Stage 2: если RMSE > STAGE1_THRESHOLD → освобождаем ha*, c*
             с регуляризацией (штраф за отклонение от стандарта).
    """
    is_pair = gear_input.is_pair()

    # --- Stage 1: fixed standard coefficients ---
    result_s1 = _run_stage1(m, gear_input, is_pair)

    if result_s1.total_error <= STAGE1_THRESHOLD:
        _mark_standard(result_s1)
        return result_s1

    # --- Stage 2: free ha*/c* with regularization ---
    result_s2 = _run_stage2(m, gear_input, is_pair)

    # Return whichever stage gave lower error
    best = result_s1 if result_s1.total_error <= result_s2.total_error else result_s2
    _mark_standard(best)
    return best


# ---------------------------------------------------------------------------
# Stage 1
# ---------------------------------------------------------------------------

def _run_stage1(m: float, gear_input: GearInput, is_pair: bool) -> SolveResult:
    """Оптимизация с фиксированными ha*=1.0, c*=0.25."""
    x_starts = [-1.0, -0.5, 0.0, 0.5, 1.0]

    best_params = None
    best_error = float('inf')

    for x_init in x_starts:
        x0 = [x_init, x_init] if is_pair else [x_init]
        bounds = (
            [X_BOUNDS[0]] * (2 if is_pair else 1),
            [X_BOUNDS[1]] * (2 if is_pair else 1),
        )
        try:
            res = least_squares(
                _residuals_stage1,
                x0,
                args=(m, gear_input, is_pair),
                bounds=bounds,
                max_nfev=500,
            )
            err = _rmse(res.fun)
            if err < best_error:
                best_error = err
                best_params = res.x
        except Exception:
            pass

    if best_params is None:
        x1 = 0.0
        x2 = 0.0 if is_pair else None
        return SolveResult(m=m, x1=x1, x2=x2,
                           ha_star=HA_STAR_STD, c_star=C_STAR_STD,
                           total_error=1e6, stage=1)

    if is_pair:
        x1, x2 = best_params
        return SolveResult(m=m, x1=x1, x2=x2,
                           ha_star=HA_STAR_STD, c_star=C_STAR_STD,
                           total_error=best_error, stage=1)
    else:
        x1 = best_params[0]
        return SolveResult(m=m, x1=x1,
                           ha_star=HA_STAR_STD, c_star=C_STAR_STD,
                           total_error=best_error, stage=1)


def _residuals_stage1(
    params: list[float],
    m: float,
    gear_input: GearInput,
    is_pair: bool,
) -> list[float]:
    """Невязки при фиксированных ha*=1.0, c*=0.25."""
    ha_star = HA_STAR_STD
    c_star = C_STAR_STD

    if is_pair:
        x1, x2 = params
    else:
        x1 = params[0]
        x2 = None

    return _compute_residuals(m, gear_input, is_pair, x1, x2, ha_star, c_star)


# ---------------------------------------------------------------------------
# Stage 2
# ---------------------------------------------------------------------------

def _run_stage2(m: float, gear_input: GearInput, is_pair: bool) -> SolveResult:
    """Оптимизация с освобождёнными ha*, c* и регуляризацией."""
    x_starts = [-1.0, -0.5, 0.0, 0.5, 1.0]
    ha_starts = [0.8, 1.0, 1.1]

    best_params = None
    best_error = float('inf')

    for x_init in x_starts:
        for ha_init in ha_starts:
            c_init = C_STAR_STD
            x0 = [x_init, x_init, ha_init, c_init] if is_pair else [x_init, ha_init, c_init]
            try:
                res = least_squares(
                    _residuals_stage2,
                    x0,
                    args=(m, gear_input, is_pair),
                    bounds=_get_bounds_stage2(is_pair),
                    max_nfev=1000,
                )
                err = _rmse(res.fun)
                if err < best_error:
                    best_error = err
                    best_params = res.x
            except Exception:
                pass

    if best_params is None:
        x1 = 0.0
        x2 = 0.0 if is_pair else None
        return SolveResult(m=m, x1=x1, x2=x2,
                           ha_star=HA_STAR_STD, c_star=C_STAR_STD,
                           total_error=1e6, stage=2)

    if is_pair:
        x1, x2, ha_star, c_star = best_params
        # Compute geometric-only RMSE (without regularization penalty)
        geom_residuals = _compute_residuals(m, gear_input, is_pair, x1, x2, ha_star, c_star)
        geom_error = _rmse(geom_residuals)
        return SolveResult(m=m, x1=x1, x2=x2,
                           ha_star=ha_star, c_star=c_star,
                           total_error=geom_error, stage=2)
    else:
        x1, ha_star, c_star = best_params
        geom_residuals = _compute_residuals(m, gear_input, is_pair, x1, None, ha_star, c_star)
        geom_error = _rmse(geom_residuals)
        return SolveResult(m=m, x1=x1,
                           ha_star=ha_star, c_star=c_star,
                           total_error=geom_error, stage=2)


def _residuals_stage2(
    params: list[float],
    m: float,
    gear_input: GearInput,
    is_pair: bool,
) -> list[float]:
    """
    Невязки с регуляризацией: штраф за отклонение ha*, c* от стандарта.
    Вес штрафа REGULARIZATION_WEIGHT масштабирован к типичной погрешности ~0.1 мм.
    """
    if is_pair:
        x1, x2, ha_star, c_star = params
    else:
        x1, ha_star, c_star = params
        x2 = None

    residuals = _compute_residuals(m, gear_input, is_pair, x1, x2, ha_star, c_star)

    # Regularization: penalize deviation from standard values
    residuals.append(REGULARIZATION_WEIGHT * (ha_star - HA_STAR_STD))
    residuals.append(REGULARIZATION_WEIGHT * (c_star - C_STAR_STD))

    return residuals


def _get_bounds_stage2(is_pair: bool) -> tuple:
    if is_pair:
        return (
            [X_BOUNDS[0], X_BOUNDS[0], HA_BOUNDS[0], C_BOUNDS[0]],
            [X_BOUNDS[1], X_BOUNDS[1], HA_BOUNDS[1], C_BOUNDS[1]],
        )
    else:
        return (
            [X_BOUNDS[0], HA_BOUNDS[0], C_BOUNDS[0]],
            [X_BOUNDS[1], HA_BOUNDS[1], C_BOUNDS[1]],
        )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _compute_residuals(
    m: float,
    gear_input: GearInput,
    is_pair: bool,
    x1: float,
    x2: Optional[float],
    ha_star: float,
    c_star: float,
) -> list[float]:
    """
    Вычислить геометрические невязки (мм).

    Формулы:
      da = m * (z + 2*ha_star + 2*x)
      df = m * (z - 2*(ha_star + c_star) + 2*x)
    """
    residuals = []

    da1_calc = m * (gear_input.z1 + 2 * ha_star + 2 * x1)
    df1_calc = m * (gear_input.z1 - 2 * (ha_star + c_star) + 2 * x1)

    if gear_input.da1 != 0:
        residuals.append(da1_calc - gear_input.da1)
    if gear_input.df1 != 0:
        residuals.append(df1_calc - gear_input.df1)

    if is_pair and gear_input.z2 is not None and x2 is not None:
        z2 = gear_input.z2
        da2_calc = m * (z2 + 2 * ha_star + 2 * x2)
        df2_calc = m * (z2 - 2 * (ha_star + c_star) + 2 * x2)

        if gear_input.da2 is not None and gear_input.da2 != 0:
            residuals.append(da2_calc - gear_input.da2)
        if gear_input.df2 is not None and gear_input.df2 != 0:
            residuals.append(df2_calc - gear_input.df2)

    if gear_input.aw != 0 and is_pair and gear_input.z2 is not None and x2 is not None:
        aw_calc = m * (gear_input.z1 + gear_input.z2) / 2 + m * (x1 + x2)
        residuals.append(aw_calc - gear_input.aw)

    if not residuals:
        residuals = [0.0]

    return residuals


def _rmse(residuals) -> float:
    """Root Mean Square Error по вектору невязок (мм)."""
    arr = np.asarray(residuals)
    return float(np.sqrt(np.mean(arr ** 2)))


def _mark_standard(result: SolveResult) -> None:
    """Проверить и отметить совпадение с ГОСТ или DP."""
    m = result.m

    for gost_m in GOST_MODULES:
        if abs(m - gost_m) <= STANDARD_MATCH_TOLERANCE:
            result.is_gost = True
            return

    for dp in DP_PITCHES:
        dp_m = round(25.4 / dp, 3)
        if abs(m - dp_m) <= STANDARD_MATCH_TOLERANCE:
            result.dp_label = f"DP {dp}"
            return
