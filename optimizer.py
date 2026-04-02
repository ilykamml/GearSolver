"""
Модуль математической модели и оптимизации параметров зубчатых передач.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np
from scipy.optimize import least_squares

from cli import GearInput
from config import (
    X_BOUNDS, HA_BOUNDS, C_BOUNDS,
    GOST_MODULES, DP_PITCHES, STANDARD_MATCH_TOLERANCE
)


@dataclass
class SolveResult:
    """Результат оптимизации для одного модуля."""
    m: float                      # Модуль
    x1: float                     # Коэффициент смещения шестерни 1
    x2: Optional[float] = None    # Коэффициент смещения шестерни 2 (для пары)
    ha_star: float = 0.0          # Коэффициент высоты головки
    c_star: float = 0.0           # Коэффициент радиального зазора
    total_error: float = 0.0      # Суммарная невязка (мм)
    is_gost: bool = False         # Совпадает со стандартом ГОСТ
    dp_label: Optional[str] = None  # Метка DP (напр. "DP 8")


def optimize_for_module(m: float, gear_input: GearInput) -> SolveResult:
    """
    Оптимизировать параметры для заданного модуля.
    
    Для одной шестерни: оптимизируем [x1, ha_star, c_star]
    Для пары: оптимизируем [x1, x2, ha_star, c_star] (ha_star и c_star общие)
    
    Args:
        m: Модуль (мм)
        gear_input: Входные параметры
    
    Returns:
        SolveResult с оптимизированными параметрами
    """
    is_pair = gear_input.is_pair()
    
    # Множественные стартовые точки для избежания локальных минимумов
    x_starts = [-1.0, -0.5, 0.0, 0.5, 1.0]
    ha_starts = [0.7, 0.9, 1.0]
    
    best_result = None
    best_error = float('inf')
    
    for x_init in x_starts:
        for ha_init in ha_starts:
            c_init = 0.25
            
            if is_pair:
                x0 = [x_init, x_init, ha_init, c_init]
            else:
                x0 = [x_init, ha_init, c_init]
            
            try:
                res = least_squares(
                    _residuals,
                    x0,
                    args=(m, gear_input, is_pair),
                    bounds=_get_bounds(is_pair),
                    max_nfev=1000
                )
                
                error = np.sum(res.fun ** 2)
                if error < best_error:
                    best_error = error
                    best_result = (res.x, error)
            except Exception:
                # Если оптимизация не сошлась, пропускаем этот старт
                pass
    
    if best_result is None:
        # Fallback: вернуть неудачный результат
        if is_pair:
            return SolveResult(m=m, x1=0.0, x2=0.0, ha_star=1.0, c_star=0.25, total_error=1e6)
        else:
            return SolveResult(m=m, x1=0.0, ha_star=1.0, c_star=0.25, total_error=1e6)
    
    params, error = best_result
    
    if is_pair:
        x1, x2, ha_star, c_star = params
        result = SolveResult(
            m=m, x1=x1, x2=x2, ha_star=ha_star, c_star=c_star,
            total_error=np.sqrt(error)
        )
    else:
        x1, ha_star, c_star = params
        result = SolveResult(
            m=m, x1=x1, ha_star=ha_star, c_star=c_star,
            total_error=np.sqrt(error)
        )
    
    # Проверить совпадение со стандартами
    _mark_standard(result)
    
    return result


def _residuals(
    params: list[float],
    m: float,
    gear_input: GearInput,
    is_pair: bool
) -> list[float]:
    """
    Вычислить вектор невязок для least_squares.
    
    Формулы:
      da = m * (z + 2*ha_star + 2*x)
      df = m * (z - 2*(ha_star + c_star) + 2*x)
      aw = m * (z1 + z2) / 2 + m * (x1 + x2)
    """
    residuals = []
    
    if is_pair:
        x1, x2, ha_star, c_star = params
        
        # Шестерня 1
        da1_calc = m * (gear_input.z1 + 2*ha_star + 2*x1)
        df1_calc = m * (gear_input.z1 - 2*(ha_star + c_star) + 2*x1)
        
        if gear_input.da1 != 0:
            residuals.append(da1_calc - gear_input.da1)
        if gear_input.df1 != 0:
            residuals.append(df1_calc - gear_input.df1)
        
        # Шестерня 2
        z2 = gear_input.z2
        if z2 is not None:
            da2_calc = m * (z2 + 2*ha_star + 2*x2)
            df2_calc = m * (z2 - 2*(ha_star + c_star) + 2*x2)
            
            if gear_input.da2 is not None and gear_input.da2 != 0:
                residuals.append(da2_calc - gear_input.da2)
            if gear_input.df2 is not None and gear_input.df2 != 0:
                residuals.append(df2_calc - gear_input.df2)
        
        # Межосевое расстояние
        if gear_input.aw != 0:
            z2 = gear_input.z2
            if z2 is not None:
                aw_calc = m * (gear_input.z1 + z2) / 2 + m * (x1 + x2)
                residuals.append(aw_calc - gear_input.aw)
    else:
        x1, ha_star, c_star = params
        
        # Одна шестерня
        da1_calc = m * (gear_input.z1 + 2*ha_star + 2*x1)
        df1_calc = m * (gear_input.z1 - 2*(ha_star + c_star) + 2*x1)
        
        if gear_input.da1 != 0:
            residuals.append(da1_calc - gear_input.da1)
        if gear_input.df1 != 0:
            residuals.append(df1_calc - gear_input.df1)
    
    # Если нет ограничений, вернуть пустой список (может привести к проблеме)
    if not residuals:
        residuals = [0.0]
    
    return residuals


def _get_bounds(is_pair: bool) -> tuple:
    """Получить bounds для least_squares в зависимости от типа (пара или одна)."""
    if is_pair:
        return (
            [X_BOUNDS[0], X_BOUNDS[0], HA_BOUNDS[0], C_BOUNDS[0]],
            [X_BOUNDS[1], X_BOUNDS[1], HA_BOUNDS[1], C_BOUNDS[1]]
        )
    else:
        return (
            [X_BOUNDS[0], HA_BOUNDS[0], C_BOUNDS[0]],
            [X_BOUNDS[1], HA_BOUNDS[1], C_BOUNDS[1]]
        )


def _mark_standard(result: SolveResult) -> None:
    """
    Проверить и отметить совпадение с ГОСТ или DP.
    """
    m = result.m
    
    # Проверка ГОСТ
    for gost_m in GOST_MODULES:
        if abs(m - gost_m) <= STANDARD_MATCH_TOLERANCE:
            result.is_gost = True
            return
    
    # Проверка DP
    for dp in DP_PITCHES:
        dp_m = round(25.4 / dp, 3)
        if abs(m - dp_m) <= STANDARD_MATCH_TOLERANCE:
            result.dp_label = f"DP {dp}"
            return
