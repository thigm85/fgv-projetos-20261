"""Dashboard interativo — seção 4.5."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import ipywidgets as widgets
from IPython.display import clear_output, display

TASK_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = TASK_ROOT / "results"


def _rank_products(
    df_detail: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    country: str,
    product_line: str,
    top_n: int,
) -> pd.DataFrame:
    filtered = df_detail[
        (df_detail["full_date"] >= start)
        & (df_detail["full_date"] <= end)
    ]
    if country != "Todos":
        filtered = filtered[filtered["country"] == country]
    if product_line != "Todos":
        filtered = filtered[filtered["product_line"] == product_line]

    return (
        filtered.groupby("product_name", as_index=False)["total_sales"]
        .sum()
        .sort_values("total_sales", ascending=False)
        .head(top_n)
    )


def _plot_top_products(
    ranked: pd.DataFrame,
    *,
    top_n: int,
    country: str,
    product_line: str,
    save_path: str | Path | None = None,
    show: bool = True,
) -> None:
    fig, ax = plt.subplots(figsize=(10, max(4, 0.4 * len(ranked))))
    sns.barplot(
        data=ranked,
        y="product_name",
        x="total_sales",
        hue="product_name",
        legend=False,
        palette="viridis",
        ax=ax,
    )
    ax.set_xlabel("Vendas totais")
    ax.set_ylabel("Produto")
    ax.set_title(
        f"Top {top_n} produtos — {country} / {product_line}"
    )
    plt.tight_layout()

    if save_path:
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=300, bbox_inches="tight")
        print(f"Imagem salva em: {path}")

    if show:
        plt.show()
    else:
        plt.close(fig)


def build_dashboard(
    df_detail: pd.DataFrame,
    save_path: str | Path | None = None,
    *,
    interactive: bool = True,
) -> None:
    """Painel com filtros de data, país, linha e Top N.

    Args:
        df_detail: DataFrame detalhado (consulta 4.4).
        save_path: Caminho opcional para salvar a imagem (ex.: results/grafico.png).
        interactive: Se False, gera um gráfico com filtros padrão e encerra (uso em main/CLI).
    """
    sns.set_theme(style="whitegrid")

    date_min = df_detail["full_date"].min()
    date_max = df_detail["full_date"].max()

    if not interactive:
        ranked = _rank_products(
            df_detail,
            date_min,
            date_max,
            country="Todos",
            product_line="Todos",
            top_n=5,
        )
        if ranked.empty:
            print("Nenhum dado para os filtros padrão.")
            return
        _plot_top_products(
            ranked,
            top_n=5,
            country="Todos",
            product_line="Todos",
            save_path=save_path,
            show=False,
        )
        return

    countries = sorted(df_detail["country"].dropna().unique().tolist())
    product_lines = sorted(
        df_detail["product_line"].dropna().unique().tolist()
    )

    date_start = widgets.DatePicker(
        description="Data início",
        value=date_min.date(),
    )
    date_end = widgets.DatePicker(
        description="Data fim",
        value=date_max.date(),
    )
    country_filter = widgets.Dropdown(
        options=["Todos"] + countries,
        value="Todos",
        description="País",
    )
    line_filter = widgets.Dropdown(
        options=["Todos"] + product_lines,
        value="Todos",
        description="Linha",
    )
    top_n = widgets.IntSlider(
        value=5,
        min=1,
        max=10,
        step=1,
        description="Top N",
    )
    out = widgets.Output()

    def update_dashboard(*_) -> None:
        with out:
            clear_output(wait=True)

            start = pd.Timestamp(date_start.value)
            end = pd.Timestamp(date_end.value)
            if start > end:
                start, end = end, start

            ranked = _rank_products(
                df_detail,
                start,
                end,
                country_filter.value,
                line_filter.value,
                top_n.value,
            )

            if ranked.empty:
                print("Nenhum dado para os filtros selecionados.")
                return

            _plot_top_products(
                ranked,
                top_n=top_n.value,
                country=country_filter.value,
                product_line=line_filter.value,
                save_path=save_path,
                show=True,
            )

    controls = widgets.VBox(
        [
            widgets.HBox([date_start, date_end]),
            widgets.HBox([country_filter, line_filter, top_n]),
            out,
        ]
    )

    for widget in (
        date_start,
        date_end,
        country_filter,
        line_filter,
        top_n,
    ):
        widget.observe(update_dashboard, names="value")

    display(controls)
    update_dashboard()
