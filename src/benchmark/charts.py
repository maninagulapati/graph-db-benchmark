"""Chart generation for the README's "Charts and Visualization" section.

Colors and chart chrome follow the validated categorical palette and light
chart surface from the dataviz skill (references/palette.md): fixed hue
order assigned by database identity (never re-assigned by rank, so a given
database keeps its color across every chart), thin marks, muted
grid/axes, and one y-axis per plot (never a dual-axis chart — the ingestion
chart uses two subplots rather than twin axes because nodes/sec and
relationships/sec are different scales).
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: this module only ever writes PNG files
import matplotlib.pyplot as plt  # noqa: E402

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
AXIS = "#c3c2b7"

# Fixed categorical order — validated for adjacent-pair colorblind safety.
# Assigned to databases by position, never re-ordered by value/rank.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]


def _color_map(database_names):
    """Stable database -> color assignment, independent of which subset a
    particular chart happens to include."""
    return {name: CATEGORICAL[i % len(CATEGORICAL)] for i, name in enumerate(sorted(database_names))}


def _style_axes(ax):
    ax.set_facecolor(SURFACE)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(AXIS)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    ax.xaxis.label.set_color(INK_SECONDARY)
    ax.yaxis.label.set_color(INK_SECONDARY)


def _new_figure(figsize=(7, 4.5)):
    fig, ax = plt.subplots(figsize=figsize, facecolor=SURFACE)
    _style_axes(ax)
    return fig, ax


def _save(fig, path, title):
    ax = fig.axes[0]
    ax.set_title(title, color=INK_PRIMARY, fontsize=12, loc="left", pad=12)
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_traversal_latency(results, metric_key, metric_label, path):
    depths = ["1hop", "2hop", "3hop"]
    workload_names = {"1hop": "traversal_1hop", "2hop": "traversal_2hop", "3hop": "traversal_3hop"}
    colors = _color_map(r["database"] for r in results)

    fig, ax = _new_figure()
    bar_width = 0.8 / max(len(results), 1)
    x_base = range(len(depths))

    for i, db_result in enumerate(results):
        values = [db_result["summary"].get(workload_names[d], {}).get(metric_key) for d in depths]
        offsets = [x + i * bar_width for x in x_base]
        ax.bar(offsets, [v if v is not None else 0 for v in values], width=bar_width,
               label=db_result["database"], color=colors[db_result["database"]], zorder=3)

    ax.set_xticks([x + bar_width * (len(results) - 1) / 2 for x in x_base])
    ax.set_xticklabels(["1-hop", "2-hop", "3-hop"])
    ax.set_ylabel(f"{metric_label} (ms)")
    if len(results) > 1:
        ax.legend(frameon=False, labelcolor=INK_SECONDARY, fontsize=9)
    _save(fig, path, f"Traversal latency — {metric_label}")


def plot_ingestion(results, path):
    colors = _color_map(r["database"] for r in results)
    fig, (ax_nodes, ax_rels) = plt.subplots(1, 2, figsize=(9, 4.5), facecolor=SURFACE)
    for ax in (ax_nodes, ax_rels):
        _style_axes(ax)

    names = [r["database"] for r in results]
    node_rates = [r["load_stats"].get("nodes_per_second", 0) for r in results]
    rel_rates = [r["load_stats"].get("relationships_per_second", 0) for r in results]
    bar_colors = [colors[n] for n in names]

    ax_nodes.bar(names, node_rates, color=bar_colors, zorder=3)
    ax_nodes.set_ylabel("Nodes / sec")
    ax_nodes.tick_params(axis="x", rotation=30)

    ax_rels.bar(names, rel_rates, color=bar_colors, zorder=3)
    ax_rels.set_ylabel("Relationships / sec")
    ax_rels.tick_params(axis="x", rotation=30)

    fig.suptitle("Data loading throughput", color=INK_PRIMARY, fontsize=12, x=0.02, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def _plot_concurrency_line(results, value_fn, ylabel, title, path):
    colors = _color_map(r["database"] for r in results)
    fig, ax = _new_figure()

    for db_result in results:
        points = sorted(db_result.get("mixed_workload", []), key=lambda p: p["concurrency"])
        if not points:
            continue
        x = [p["concurrency"] for p in points]
        y = [value_fn(p) for p in points]
        ax.plot(x, y, marker="o", markersize=6, linewidth=2,
                color=colors[db_result["database"]], label=db_result["database"])

    ax.set_xlabel("Concurrency (clients)")
    ax.set_ylabel(ylabel)
    if len(results) > 1:
        ax.legend(frameon=False, labelcolor=INK_SECONDARY, fontsize=9)
    _save(fig, path, title)


def generate_charts(results, output_dir):
    """Render every chart in README section 38 and return the written paths.

    Silently skips a chart only when its underlying data is entirely
    absent (e.g. no mixed-workload results yet) — it does not silently
    truncate the databases shown within a chart that does render.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []

    if any(r["summary"].get("traversal_1hop") for r in results):
        p50_path = output_dir / "traversal_p50.png"
        plot_traversal_latency(results, "p50_ms", "p50", p50_path)
        written.append(p50_path)

        p95_path = output_dir / "traversal_p95.png"
        plot_traversal_latency(results, "p95_ms", "p95", p95_path)
        written.append(p95_path)

    if any(r.get("load_stats") for r in results):
        ingestion_path = output_dir / "ingestion.png"
        plot_ingestion(results, ingestion_path)
        written.append(ingestion_path)

    if any(r.get("mixed_workload") for r in results):
        throughput_path = output_dir / "throughput_vs_concurrency.png"
        _plot_concurrency_line(
            results, lambda p: p["throughput_ops_per_sec"], "Throughput (ops/sec)",
            "Throughput vs. concurrency", throughput_path,
        )
        written.append(throughput_path)

        latency_path = output_dir / "latency_vs_concurrency.png"
        _plot_concurrency_line(
            results, lambda p: p["p95_ms"], "p95 latency (ms)",
            "Tail latency vs. concurrency", latency_path,
        )
        written.append(latency_path)

        error_path = output_dir / "error_rate_vs_concurrency.png"
        _plot_concurrency_line(
            results, lambda p: p["error_rate_pct"], "Error rate (%)",
            "Error rate vs. concurrency", error_path,
        )
        written.append(error_path)

    return written
