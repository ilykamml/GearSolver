"""
Модуль мультипроцессорного диспетчера оптимизации.
"""

import os
from concurrent.futures import ProcessPoolExecutor
from functools import partial

from cli import GearInput
from optimizer import optimize_for_module, SolveResult


def run_parallel_solve(
    modules: list[float],
    gear_input: GearInput
) -> list[SolveResult]:
    """
    Запустить параллельную оптимизацию для каждого модуля.
    
    Args:
        modules: Список модулей для оптимизации
        gear_input: Входные параметры
    
    Returns:
        Список SolveResult для каждого модуля
    """
    worker_fn = partial(optimize_for_module, gear_input=gear_input)
    
    max_workers = os.cpu_count() or 1
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(worker_fn, modules))
    
    return results
