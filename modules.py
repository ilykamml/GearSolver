"""
Модуль для генерации пула модулей для оптимизации.
"""

import numpy as np
from config import GOST_MODULES, DP_PITCHES, MODULE_MIN, MODULE_MAX, MODULE_STEP


def build_module_pool(
    step: float = MODULE_STEP,
    min_m: float = MODULE_MIN,
    max_m: float = MODULE_MAX
) -> list[float]:
    """
    Построить пул уникальных модулей для проверки.
    
    Объединяет:
    1. Равномерную сетку от min_m до max_m с шагом step
    2. Стандартные метрические модули (ГОСТ)
    3. Дюймовые питчи, переведённые в метрические модули
    
    Args:
        step: Шаг сетки модулей (мм)
        min_m: Минимальный модуль (мм)
        max_m: Максимальный модуль (мм)
    
    Returns:
        Отсортированный список уникальных модулей (мм)
    """
    modules = set()
    
    # 1. Равномерная сетка
    grid = np.arange(min_m, max_m + step, step)
    modules.update(grid)
    
    # 2. ГОСТ модули (в диапазоне)
    modules.update([m for m in GOST_MODULES if min_m <= m <= max_m])
    
    # 3. DP → метрический модуль (m = 25.4 / DP)
    for dp in DP_PITCHES:
        m = round(25.4 / dp, 3)
        if min_m <= m <= max_m:
            modules.add(m)
    
    # Округлить до 3 знаков, убрать дубликаты и отсортировать
    modules = set(round(m, 3) for m in modules)
    return sorted(list(modules))
