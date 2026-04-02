"""
Модуль интерактивной визуализации результатов с помощью Plotly.
"""

import webbrowser
from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

from cli import GearInput
from optimizer import SolveResult


def build_dashboard(
    results: list[SolveResult],
    gear_input: GearInput,
    output_path: str = "gear_results.html"
) -> None:
    """
    Построить интерактивный дашборд Plotly с двумя графиками.
    
    График 1: Модуль vs Ошибка (Scatter+Line)
    График 2: Смещение vs Модуль (Scatter с colorscale)
    
    Args:
        results: Список результатов оптимизации
        gear_input: Входные параметры
        output_path: Путь для сохранения HTML
    """
    # Создать подграфики
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=(
            "Модуль vs Ошибка",
            "Смещение vs Модуль"
        ),
        specs=[[{"secondary_y": False}, {"secondary_y": False}]]
    )
    
    # Подготовить данные
    modules = [r.m for r in results]
    errors = [r.total_error for r in results]
    
    # Определить смещение для второго графика
    if gear_input.is_pair():
        displacements = [(r.x1 + r.x2) / 2 if r.x2 is not None else r.x1 for r in results]
    else:
        displacements = [r.x1 for r in results]
    
    # Определить цвета: ГOST — зелёный, DP — синий, остальное — серый
    colors1 = []
    symbols1 = []
    for r in results:
        if r.is_gost:
            colors1.append("green")
            symbols1.append("star")
        elif r.dp_label:
            colors1.append("blue")
            symbols1.append("triangle-up")
        else:
            colors1.append("gray")
            symbols1.append("circle")
    
    # График 1: Модуль vs Ошибка (Scatter + Line)
    fig.add_trace(
        go.Scatter(
            x=modules,
            y=errors,
            mode='lines+markers',
            name='Ошибка',
            line=dict(color='lightgray', width=1),
            marker=dict(
                size=8,
                color=colors1,
                symbol=symbols1,
                line=dict(width=1, color='DarkSlateGrey')
            ),
            hovertemplate='<b>m = %{x:.3f}</b><br>Ошибка = %{y:.4f} мм<extra></extra>'
        ),
        row=1, col=1
    )
    
    # График 2: Смещение vs Модуль (Scatter с colorscale)
    fig.add_trace(
        go.Scatter(
            x=modules,
            y=displacements,
            mode='markers',
            name='Смещение',
            marker=dict(
                size=8,
                color=errors,
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(
                    title="Ошибка<br>(мм)",
                    x=1.12,
                    len=0.7,
                    y=0.5
                ),
                line=dict(width=0.5, color='DarkSlateGrey')
            ),
            hovertemplate='<b>m = %{x:.3f}</b><br>Смещение = %{y:.3f}<br>Ошибка = %{marker.color:.4f}<extra></extra>'
        ),
        row=1, col=2
    )
    
    # Обновить оси
    fig.update_xaxes(title_text="Модуль m (мм)", row=1, col=1)
    fig.update_yaxes(title_text="Суммарная ошибка (мм)", row=1, col=1)
    
    fig.update_xaxes(title_text="Модуль m (мм)", row=1, col=2)
    fig.update_yaxes(title_text="Смещение x", row=1, col=2)
    
    # Общие параметры
    fig.update_layout(
        title_text=f"GearSolver — Анализ параметров{'передачи' if gear_input.is_pair() else 'шестерни'}",
        height=600,
        showlegend=False,
        hovermode='closest',
        template='plotly_white'
    )
    
    # Сохранить HTML
    fig.write_html(output_path)
    print(f"\n✓ Дашборд сохранён: {output_path}")
    
    # Открыть в браузере
    try:
        webbrowser.open(f"file://{Path(output_path).absolute()}")
        print("✓ Открыто в браузере\n")
    except Exception as e:
        print(f"⚠ Не удалось открыть браузер: {e}\n")
