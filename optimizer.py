"""
Модуль математической модели и оптимизации параметров зубчатых передач.

Two-stage search strategy:
  Stage 1: fix ha*=1.0, iterate discrete c* and root fillet coefficients,
           optimize only x1 [x2].
  Stage 2: if stage-1 weighted RMSE > STAGE1_THRESHOLD, free ha* while
           keeping discrete c* and fillet, with regularization to standard values.
"""

from dataclasses import dataclass
from typing import Optional
import math

import numpy as np
from scipy.optimize import least_squares

from cli import GearInput
from config import (
    X_BOUNDS,
    HA_BOUNDS,
    C_BOUNDS,
    GOST_MODULES,
    DP_PITCHES,
    STANDARD_MATCH_TOLERANCE,
    REGULARIZATION_WEIGHT,
    STAGE1_THRESHOLD,
    MEASUREMENT_TOLERANCE,
    WEIGHT_DA,
    WEIGHT_DF,
    WEIGHT_AW,
    C_STAR_VALUES,
    ROOT_FILLET_COEFFS,
)

# Standard values for regularization
HA_STAR_STD = 1.0
C_STAR_STD = 0.25
PRESSURE_ANGLE_RAD = math.radians(20.0)


@dataclass
class SolveResult:
    """Результат оптимизации для одного модуля."""

    m: float
    x1: float
    x2: Optional[float] = None
    ha_star: float = 0.0
    c_star: float = 0.0
    root_fillet_coeff: float = 0.25

    # Errors
    total_error: float = 0.0  # Геометрическая RMSE (мм), без весов и без регуляризации
    weighted_error: float = 0.0  # RMSE по взвешенным невязкам (используется для ранжирования)

    # Derived diagnostics
    confidence: float = 0.0  # [0..1]
    aw_calc: Optional[float] = None

    tooth_thickness_tip1: Optional[float] = None
    tooth_thickness_root1: Optional[float] = None
    tooth_thickness_tip2: Optional[float] = None
    tooth_thickness_root2: Optional[float] = None

    # Standard labels / meta
    is_gost: bool = False
    dp_label: Optional[str] = None
    stage: int = 1  # 1 = standard ha*, 2 = free ha*


def optimize_for_module(m: float, gear_input: GearInput) -> SolveResult:
    """
    Двухэтапная оптимизация для заданного модуля.

    Stage 1: ha*=1.0 фиксирован, дискретный перебор c* и root fillet.
    Stage 2: если weighted RMSE этапа 1 > STAGE1_THRESHOLD — освобождаем ha*
             при фиксированном дискретном c* и root fillet.
    """
    is_pair = gear_input.is_pair()

    result_s1 = _run_stage1(m, gear_input, is_pair)
    if result_s1.weighted_error <= STAGE1_THRESHOLD:
        _mark_standard(result_s1)
        return result_s1

    result_s2 = _run_stage2(m, gear_input, is_pair)

    # Prefer better weighted fit, then better geometric fit
    if result_s1.weighted_error < result_s2.weighted_error:
        best = result_s1
    elif result_s2.weighted_error < result_s1.weighted_error:
        best = result_s2
    else:
        best = result_s1 if result_s1.total_error <= result_s2.total_error else result_s2

    _mark_standard(best)
    return best


# ---------------------------------------------------------------------------
# Stage 1
# ---------------------------------------------------------------------------

def _run_stage1(m: float, gear_input: GearInput, is_pair: bool) -> SolveResult:
    """Оптимизация с фиксированным ha*=1.0 и дискретным перебором c*/fillet."""
    x_starts = [-1.0, -0.5, 0.0, 0.5, 1.0]

    best: Optional[SolveResult] = None

    for c_star in C_STAR_VALUES:
        # Keep bounds compatibility with configured numeric interval
        if not (C_BOUNDS[0] <= c_star <= C_BOUNDS[1]):
            continue

        for fillet_coeff in ROOT_FILLET_COEFFS:
            best_params = None
            best_weighted = float("inf")

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
                        args=(m, gear_input, is_pair, c_star, fillet_coeff),
                        bounds=bounds,
                        max_nfev=600,
                    )
                    err_w = _rmse(res.fun)
                    if err_w < best_weighted:
                        best_weighted = err_w
                        best_params = res.x
                except Exception:
                    pass

            if best_params is None:
                continue

            if is_pair:
                x1, x2 = float(best_params[0]), float(best_params[1])
            else:
                x1, x2 = float(best_params[0]), None

            candidate = _build_result(
                m=m,
                gear_input=gear_input,
                is_pair=is_pair,
                x1=x1,
                x2=x2,
                ha_star=HA_STAR_STD,
                c_star=float(c_star),
                root_fillet_coeff=float(fillet_coeff),
                stage=1,
            )

            if best is None or _result_better(candidate, best):
                best = candidate

    if best is not None:
        return best

    # Fallback if optimizer failed for all hypotheses
    fallback = _build_result(
        m=m,
        gear_input=gear_input,
        is_pair=is_pair,
        x1=0.0,
        x2=0.0 if is_pair else None,
        ha_star=HA_STAR_STD,
        c_star=C_STAR_STD,
        root_fillet_coeff=ROOT_FILLET_COEFFS[0],
        stage=1,
    )
    fallback.total_error = 1e6
    fallback.weighted_error = 1e6
    fallback.confidence = 0.0
    return fallback


def _residuals_stage1(
    params: list[float],
    m: float,
    gear_input: GearInput,
    is_pair: bool,
    c_star: float,
    fillet_coeff: float,
) -> list[float]:
    """Невязки при фиксированном ha*=1.0 и дискретных c*/fillet."""
    if is_pair:
        x1, x2 = params
    else:
        x1 = params[0]
        x2 = None

    return _compute_residuals(
        m,
        gear_input,
        is_pair,
        x1,
        x2,
        HA_STAR_STD,
        c_star,
        fillet_coeff,
        use_weights=True,
        include_tooth_penalty=True,
    )


# ---------------------------------------------------------------------------
# Stage 2
# ---------------------------------------------------------------------------

def _run_stage2(m: float, gear_input: GearInput, is_pair: bool) -> SolveResult:
    """Оптимизация с освобождённым ha* и дискретными c*/fillet."""
    x_starts = [-1.0, -0.5, 0.0, 0.5, 1.0]
    ha_starts = [0.8, 1.0, 1.1]

    best: Optional[SolveResult] = None

    for c_star in C_STAR_VALUES:
        if not (C_BOUNDS[0] <= c_star <= C_BOUNDS[1]):
            continue

        for fillet_coeff in ROOT_FILLET_COEFFS:
            best_params = None
            best_weighted = float("inf")

            for x_init in x_starts:
                for ha_init in ha_starts:
                    x0 = [x_init, x_init, ha_init] if is_pair else [x_init, ha_init]
                    try:
                        res = least_squares(
                            _residuals_stage2,
                            x0,
                            args=(m, gear_input, is_pair, c_star, fillet_coeff),
                            bounds=_get_bounds_stage2(is_pair),
                            max_nfev=1200,
                        )
                        err_w = _rmse(res.fun)
                        if err_w < best_weighted:
                            best_weighted = err_w
                            best_params = res.x
                    except Exception:
                        pass

            if best_params is None:
                continue

            if is_pair:
                x1, x2, ha_star = (float(best_params[0]), float(best_params[1]), float(best_params[2]))
            else:
                x1, ha_star = float(best_params[0]), float(best_params[1])
                x2 = None

            candidate = _build_result(
                m=m,
                gear_input=gear_input,
                is_pair=is_pair,
                x1=x1,
                x2=x2,
                ha_star=ha_star,
                c_star=float(c_star),
                root_fillet_coeff=float(fillet_coeff),
                stage=2,
            )

            if best is None or _result_better(candidate, best):
                best = candidate

    if best is not None:
        return best

    fallback = _build_result(
        m=m,
        gear_input=gear_input,
        is_pair=is_pair,
        x1=0.0,
        x2=0.0 if is_pair else None,
        ha_star=HA_STAR_STD,
        c_star=C_STAR_STD,
        root_fillet_coeff=ROOT_FILLET_COEFFS[0],
        stage=2,
    )
    fallback.total_error = 1e6
    fallback.weighted_error = 1e6
    fallback.confidence = 0.0
    return fallback


def _residuals_stage2(
    params: list[float],
    m: float,
    gear_input: GearInput,
    is_pair: bool,
    c_star: float,
    fillet_coeff: float,
) -> list[float]:
    """
    Невязки для Stage 2 с регуляризацией ha* и c* к стандарту.
    c* дискретный, поэтому его вклад — константный штраф для гипотезы.
    """
    if is_pair:
        x1, x2, ha_star = params
    else:
        x1, ha_star = params
        x2 = None

    residuals = _compute_residuals(
        m,
        gear_input,
        is_pair,
        x1,
        x2,
        ha_star,
        c_star,
        fillet_coeff,
        use_weights=True,
        include_tooth_penalty=True,
    )

    residuals.append(REGULARIZATION_WEIGHT * (ha_star - HA_STAR_STD))
    residuals.append(REGULARIZATION_WEIGHT * (c_star - C_STAR_STD))

    return residuals


def _get_bounds_stage2(is_pair: bool) -> tuple:
    if is_pair:
        return (
            [X_BOUNDS[0], X_BOUNDS[0], HA_BOUNDS[0]],
            [X_BOUNDS[1], X_BOUNDS[1], HA_BOUNDS[1]],
        )
    return (
        [X_BOUNDS[0], HA_BOUNDS[0]],
        [X_BOUNDS[1], HA_BOUNDS[1]],
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
    root_fillet_coeff: float,
    use_weights: bool,
    include_tooth_penalty: bool,
) -> list[float]:
    """Вычислить невязки (мм)."""
    residuals: list[float] = []

    da1_calc = m * (gear_input.z1 + 2 * ha_star + 2 * x1)
    df1_calc = m * (gear_input.z1 - 2 * (ha_star + c_star) + 2 * x1)

    if gear_input.da1 != 0:
        residuals.append(_weighted_diff("da1", da1_calc - gear_input.da1, gear_input, use_weights))
    if gear_input.df1 != 0:
        residuals.append(_weighted_diff("df1", df1_calc - gear_input.df1, gear_input, use_weights))

    if is_pair and gear_input.z2 is not None and x2 is not None:
        z2 = gear_input.z2
        da2_calc = m * (z2 + 2 * ha_star + 2 * x2)
        df2_calc = m * (z2 - 2 * (ha_star + c_star) + 2 * x2)

        if gear_input.da2 is not None and gear_input.da2 != 0:
            residuals.append(_weighted_diff("da2", da2_calc - gear_input.da2, gear_input, use_weights))
        if gear_input.df2 is not None and gear_input.df2 != 0:
            residuals.append(_weighted_diff("df2", df2_calc - gear_input.df2, gear_input, use_weights))

    if gear_input.aw != 0 and is_pair and gear_input.z2 is not None and x2 is not None:
        aw_calc = _calc_aw(m, gear_input.z1, gear_input.z2, x1, x2)
        residuals.append(_weighted_diff("aw", aw_calc - gear_input.aw, gear_input, use_weights))

    if include_tooth_penalty:
        s_tip1, s_root1 = _tooth_thickness(m, gear_input.z1, x1, ha_star, c_star, root_fillet_coeff)
        if s_tip1 <= 0:
            residuals.append(0.5 * abs(s_tip1))
        if s_root1 <= 0:
            residuals.append(0.5 * abs(s_root1))

        if is_pair and gear_input.z2 is not None and x2 is not None:
            s_tip2, s_root2 = _tooth_thickness(m, gear_input.z2, x2, ha_star, c_star, root_fillet_coeff)
            if s_tip2 <= 0:
                residuals.append(0.5 * abs(s_tip2))
            if s_root2 <= 0:
                residuals.append(0.5 * abs(s_root2))

    if not residuals:
        return [0.0]
    return residuals


def _weighted_diff(field: str, diff: float, gear_input: GearInput, use_weights: bool) -> float:
    if not use_weights:
        return float(diff)

    if field.startswith("da"):
        base_w = WEIGHT_DA
    elif field.startswith("df"):
        base_w = WEIGHT_DF
    elif field == "aw":
        base_w = WEIGHT_AW
    else:
        base_w = 1.0

    # Reliability adaptation by input spread (if multiple measurements were provided)
    stats = gear_input.measurement_stats.get(field)
    if stats is not None:
        std = float(stats.get("std", 0.0))
        if std > 0:
            # Higher std -> lower effective weight (clamped)
            rel = 1.0 / (1.0 + std / max(MEASUREMENT_TOLERANCE, 1e-6))
            rel = min(1.25, max(0.5, rel))
            base_w *= rel

    return float(base_w * diff)


def _build_result(
    m: float,
    gear_input: GearInput,
    is_pair: bool,
    x1: float,
    x2: Optional[float],
    ha_star: float,
    c_star: float,
    root_fillet_coeff: float,
    stage: int,
) -> SolveResult:
    raw_residuals = _compute_residuals(
        m,
        gear_input,
        is_pair,
        x1,
        x2,
        ha_star,
        c_star,
        root_fillet_coeff,
        use_weights=False,
        include_tooth_penalty=False,
    )
    weighted_residuals = _compute_residuals(
        m,
        gear_input,
        is_pair,
        x1,
        x2,
        ha_star,
        c_star,
        root_fillet_coeff,
        use_weights=True,
        include_tooth_penalty=False,
    )

    total_error = _rmse(raw_residuals)
    weighted_error = _rmse(weighted_residuals)

    tip1, root1 = _tooth_thickness(m, gear_input.z1, x1, ha_star, c_star, root_fillet_coeff)
    tip2 = root2 = None
    if is_pair and gear_input.z2 is not None and x2 is not None:
        tip2, root2 = _tooth_thickness(m, gear_input.z2, x2, ha_star, c_star, root_fillet_coeff)

    aw_calc = None
    if is_pair and gear_input.z2 is not None and x2 is not None:
        aw_calc = _calc_aw(m, gear_input.z1, gear_input.z2, x1, x2)

    result = SolveResult(
        m=m,
        x1=x1,
        x2=x2,
        ha_star=ha_star,
        c_star=c_star,
        root_fillet_coeff=root_fillet_coeff,
        total_error=total_error,
        weighted_error=weighted_error,
        aw_calc=aw_calc,
        tooth_thickness_tip1=tip1,
        tooth_thickness_root1=root1,
        tooth_thickness_tip2=tip2,
        tooth_thickness_root2=root2,
        stage=stage,
    )
    result.confidence = _compute_confidence(result)
    return result


def _result_better(a: SolveResult, b: SolveResult) -> bool:
    """Сравнение кандидатов: weighted_error -> total_error -> confidence."""
    if a.weighted_error < b.weighted_error:
        return True
    if b.weighted_error < a.weighted_error:
        return False

    if a.total_error < b.total_error:
        return True
    if b.total_error < a.total_error:
        return False

    return a.confidence > b.confidence


def _tooth_thickness(
    m: float,
    z: int,
    x: float,
    ha_star: float,
    c_star: float,
    root_fillet_coeff: float,
) -> tuple[float, float]:
    """
    Приближённая оценка толщины зуба:
    - на делительной окружности: s = m*(pi/2 + 2*x*tan(alpha))
    - на вершине: уменьшается за счёт подъёма по эвольвенте
    - у основания: увеличивается, но уменьшается из-за скругления у основания
    """
    tan_a = math.tan(PRESSURE_ANGLE_RAD)
    s_pitch = m * (math.pi / 2.0 + 2.0 * x * tan_a)
    s_tip = s_pitch - 2.0 * m * ha_star * tan_a

    # Root thickness with explicit fillet influence
    root_depth = (ha_star + c_star)
    fillet_reduction = 2.0 * m * root_fillet_coeff
    s_root = s_pitch + 2.0 * m * root_depth * tan_a - fillet_reduction

    return float(s_tip), float(s_root)


def _calc_aw(m: float, z1: int, z2: int, x1: float, x2: float) -> float:
    return float(m * (z1 + z2) / 2.0 + m * (x1 + x2))


def _compute_confidence(result: SolveResult) -> float:
    """Оценка confidence в диапазоне [0..1]."""
    sigma = max(MEASUREMENT_TOLERANCE, 1e-6)
    base = math.exp(-((result.weighted_error / sigma) ** 2))

    # stage-2 is less preferred unless it strongly improves fit
    stage_factor = 0.95 if result.stage == 2 else 1.0

    at_bound = abs(result.x1) >= abs(X_BOUNDS[1]) * 0.90
    if result.x2 is not None:
        at_bound = at_bound or abs(result.x2) >= abs(X_BOUNDS[1]) * 0.90
    bound_factor = 0.85 if at_bound else 1.0

    tooth_factor = 1.0
    min_tooth = min(
        t
        for t in [
            result.tooth_thickness_tip1,
            result.tooth_thickness_root1,
            result.tooth_thickness_tip2,
            result.tooth_thickness_root2,
        ]
        if t is not None
    )
    if min_tooth <= 0:
        tooth_factor = 0.6

    conf = base * stage_factor * bound_factor * tooth_factor
    return float(max(0.0, min(1.0, conf)))


def _rmse(residuals) -> float:
    """Root Mean Square Error по вектору невязок (мм)."""
    arr = np.asarray(residuals, dtype=float)
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
