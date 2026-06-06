"""Visual sanity-check harness for the FireWatch engine (no UI).

Runs five scenarios and saves PNG figures so a human can eyeball whether the
probabilistic spread "looks physically plausible": radial decay, time evolution,
chimney asymmetry, material contrast, and sprinkler suppression. It also prints a
STATS block (mean / max / burned-fraction etc.) used to judge whether the
empirical coefficients are in a reasonable range.

Run from the project root:  python3 -m firewatch.verify_engine
"""

from __future__ import annotations

import os
import sys

# Make `firewatch` importable whether run as a module or as a bare script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from firewatch.engine.ca_engine import CAEngine  # noqa: E402
from firewatch.domain import (  # noqa: E402
    Building,
    CellState,
    ConnectionCell,
    Floor,
    Material,
    SimParameters,
)
from firewatch.engine.ensemble import EnsembleRunner  # noqa: E402
from firewatch.viz.colormap import risk_colormap  # noqa: E402

# ----------------------------------------------------------------- style ------
BG = "#0D1117"
FG = "#E6EDF3"
MUTED = "#8B949E"
GRID = "#30363D"

# Risk colormap (low -> dark teal, mid -> yellow, high -> red), shared with the UI.
RISK_CMAP = risk_colormap()

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_out")
OFF = SimParameters(sprinkler_active=False, shutter_active=False)


def _heatmap(ax, prob, title, mark=None):
    """Draw one probability map (array indexed [x, y]) on a dark axis."""
    # Transpose so array[x, y] lands at plot position (x, y); origin lower.
    im = ax.imshow(prob.T, origin="lower", cmap=RISK_CMAP, vmin=0.0, vmax=1.0,
                   interpolation="nearest")
    ax.set_title(title, color=FG, fontsize=10, pad=6)
    ax.set_facecolor(BG)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(GRID)
    if mark is not None:
        ax.scatter([mark[0]], [mark[1]], s=55, facecolors="none",
                   edgecolors="white", linewidths=1.3)
    return im


def _style_cbar(cbar):
    cbar.ax.yaxis.set_tick_params(color=MUTED)
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color=FG)
    cbar.outline.set_edgecolor(GRID)
    cbar.set_label("reach probability", color=MUTED, fontsize=9)


def _finish(fig, path, footnote):
    fig.text(0.5, 0.015, footnote, color=MUTED, fontsize=8, ha="center")
    fig.savefig(path, facecolor=BG, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {os.path.relpath(path)}")


def _stats(prob):
    return {
        "mean": float(prob.mean()),
        "max": float(prob.max()),
        "area": int(np.count_nonzero(prob > 0.0)),
        "frac_high": float(np.mean(prob >= 0.5)),
    }


def reach_prob_by_ticks(building, params, n_runs, checkpoints, base_seed=0):
    """Ensemble reach probability accumulated up to each checkpoint tick.

    Returns {tick: [per-floor prob map]} where prob = fraction of runs in which
    the cell had ever been BURNING by that tick.
    """
    floors = building.num_floors
    acc = {t: [np.zeros(building.get_floor(f).get_grid_size()) for f in range(floors)]
           for t in checkpoints}
    max_t = max(checkpoints)
    cps = set(checkpoints)
    for i in range(n_runs):
        eng = CAEngine(building, params, base_seed + i)
        ever = [eng.states[f] == int(CellState.BURNING) for f in range(floors)]
        for t in range(1, max_t + 1):
            eng.step()
            for f in range(floors):
                ever[f] |= eng.states[f] == int(CellState.BURNING)
            if t in cps:
                for f in range(floors):
                    acc[t][f] += ever[f]
    return {t: [a / n_runs for a in acc[t]] for t in checkpoints}


# ---------------------------------------------------------------- figures -----
def fig1_spread():
    b = Building("v1")
    b.add_floor(Floor("1F", 20, 20, Material.WOOD))
    b.add_ignition(0, 10, 10)
    res = EnsembleRunner(b, OFF, n_runs=200, base_seed=0).run(max_ticks=50)
    prob = res.probability_maps[0]

    fig, ax = plt.subplots(figsize=(5.6, 5.4))
    fig.patch.set_facecolor(BG)
    im = _heatmap(ax, prob, "① Spread — WOOD 20×20, center ignition, N=200, t=50", mark=(10, 10))
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    _style_cbar(cbar)
    s = _stats(prob)
    _finish(fig, os.path.join(OUT_DIR, "v1_spread.png"),
            f"mean={s['mean']:.2f}  max={s['max']:.2f}  burned cells={s['area']}/400  "
            f"frac(p>=0.5)={s['frac_high']:.2f}")
    return s


def fig2_timeline():
    b = Building("v2")
    b.add_floor(Floor("1F", 20, 20, Material.WOOD))
    b.add_ignition(0, 10, 10)
    checkpoints = [5, 12, 20, 28]
    maps = reach_prob_by_ticks(b, OFF, n_runs=200, checkpoints=checkpoints, base_seed=0)

    fig, axes = plt.subplots(1, 4, figsize=(15.5, 4.4))
    fig.patch.set_facecolor(BG)
    im = None
    areas = []
    for ax, t in zip(axes, checkpoints):
        prob = maps[t][0]
        im = _heatmap(ax, prob, f"t = {t}", mark=(10, 10))
        areas.append(int(np.count_nonzero(prob > 0)))
    fig.suptitle("② Time evolution — cumulative reach probability by tick (WOOD, N=200)",
                 color=FG, fontsize=12, y=0.98)
    cbar = fig.colorbar(im, ax=axes, fraction=0.012, pad=0.01)
    _style_cbar(cbar)
    cps = "/".join(str(t) for t in checkpoints)
    burned = "/".join(str(a) for a in areas)
    _finish(fig, os.path.join(OUT_DIR, "v2_timeline.png"),
            f"burned cells at t={cps}: {burned} (of 400)")
    return areas


def _two_floor_building(ignite_floor):
    b = Building("v3")
    b.add_floor(Floor("1F", 20, 20, Material.WOOD))  # floor 0 (lower)
    b.add_floor(Floor("2F", 20, 20, Material.WOOD))  # floor 1 (upper)
    b.add_connection(ConnectionCell(0, 10, 10, 1, 10, 10, up_weight=0.9, down_weight=0.3))
    b.add_ignition(ignite_floor, 10, 10)
    return b


def fig3_chimney():
    res = EnsembleRunner(_two_floor_building(0), OFF, n_runs=200, base_seed=0).run(max_ticks=50)
    p_1f, p_2f = res.probability_maps[0], res.probability_maps[1]

    # Numeric up vs down asymmetry at the connection cell.
    p_up = res.get_probability(1, 10, 10)  # ignite lower -> upper target
    down = EnsembleRunner(_two_floor_building(1), OFF, n_runs=200, base_seed=0).run(max_ticks=50)
    p_down = down.get_probability(0, 10, 10)  # ignite upper -> lower target

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.4))
    fig.patch.set_facecolor(BG)
    _heatmap(axes[0], p_1f, "1F (ignition floor)", mark=(10, 10))
    im = _heatmap(axes[1], p_2f, "2F (via stairwell, upward)", mark=(10, 10))
    fig.suptitle("③ Chimney effect — 1F ignition, up_weight 0.9 > down_weight 0.3 (N=200, t=50)",
                 color=FG, fontsize=12, y=0.97)
    cbar = fig.colorbar(im, ax=axes, fraction=0.024, pad=0.02)
    _style_cbar(cbar)
    _finish(fig, os.path.join(OUT_DIR, "v3_chimney.png"),
            f"2F spread area={int(np.count_nonzero(p_2f>0))} cells   "
            f"connection-cell ignition prob:  upward={p_up:.2f}  vs  downward={p_down:.2f}")
    return {"2f_area": int(np.count_nonzero(p_2f > 0)), "p_up": p_up, "p_down": p_down,
            "2f_mean": float(p_2f.mean()), "1f_mean": float(p_1f.mean())}


def fig4_material():
    mid = 12  # PAPER is so flammable it fully saturates by ~t=18; sample early so the gradient shows.

    def run(mat):
        b = Building("v4")
        b.add_floor(Floor("1F", 20, 20, mat))
        b.add_ignition(0, 10, 10)
        return EnsembleRunner(b, OFF, n_runs=200, base_seed=0).run(max_ticks=mid).probability_maps[0]

    p_paper = run(Material.PAPER)
    p_concrete = run(Material.CONCRETE)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.4))
    fig.patch.set_facecolor(BG)
    _heatmap(axes[0], p_paper, "PAPER (low threshold, high multiplier)", mark=(10, 10))
    im = _heatmap(axes[1], p_concrete, "CONCRETE (non-flammable)", mark=(10, 10))
    fig.suptitle(f"④ Material contrast — same conditions (N=200, t={mid})", color=FG, fontsize=12, y=0.97)
    cbar = fig.colorbar(im, ax=axes, fraction=0.024, pad=0.02)
    _style_cbar(cbar)
    sp, sc = _stats(p_paper), _stats(p_concrete)
    _finish(fig, os.path.join(OUT_DIR, "v4_material.png"),
            f"PAPER: mean={sp['mean']:.2f} area={sp['area']}/400   |   "
            f"CONCRETE: mean={sc['mean']:.2f} area={sc['area']}/400")
    return sp, sc


def fig5_sprinkler():
    def build():
        b = Building("v5")
        f = Floor("1F", 20, 20, Material.TEXTILE)
        f.sprinkler[:, :] = True
        b.add_floor(f)
        b.add_ignition(0, 10, 10)
        return b

    mid = 25  # TEXTILE OFF saturates by t=50; sample mid-spread for a graded contrast.
    cooling = 1.0
    on = EnsembleRunner(
        build(), SimParameters(sprinkler_active=True, shutter_active=False, sprinkler_cooling=cooling),
        n_runs=200, base_seed=50,
    ).run(max_ticks=mid).probability_maps[0]
    off = EnsembleRunner(
        build(), SimParameters(sprinkler_active=False, shutter_active=False),
        n_runs=200, base_seed=50,
    ).run(max_ticks=mid).probability_maps[0]

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.4))
    fig.patch.set_facecolor(BG)
    _heatmap(axes[0], off, "Sprinkler OFF", mark=(10, 10))
    im = _heatmap(axes[1], on, f"Sprinkler ON (cooling={cooling})", mark=(10, 10))
    fig.suptitle(f"⑤ Sprinkler suppression — TEXTILE, same seed (N=200, t={mid})",
                 color=FG, fontsize=12, y=0.97)
    cbar = fig.colorbar(im, ax=axes, fraction=0.024, pad=0.02)
    _style_cbar(cbar)
    _finish(fig, os.path.join(OUT_DIR, "v5_sprinkler.png"),
            f"mean reach prob:  OFF={off.mean():.3f}  ->  ON={on.mean():.3f}  "
            f"(reduction {100*(1-on.mean()/max(off.mean(),1e-9)):.0f}%)")
    return {"off_mean": float(off.mean()), "on_mean": float(on.mean())}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("Rendering verification figures...")
    s1 = fig1_spread()
    a2 = fig2_timeline()
    s3 = fig3_chimney()
    sp, sc = fig4_material()
    s5 = fig5_sprinkler()

    print("\n===== STATS =====")
    print(f"[1] spread   mean={s1['mean']:.3f} max={s1['max']:.2f} area={s1['area']}/400 "
          f"frac>=0.5={s1['frac_high']:.2f}")
    print(f"[2] timeline burned cells t=5/12/20/28: {a2}")
    print(f"[3] chimney  1F mean={s3['1f_mean']:.3f}  2F mean={s3['2f_mean']:.3f}  "
          f"2F area={s3['2f_area']}  | conn ignite up={s3['p_up']:.2f} down={s3['p_down']:.2f}")
    print(f"[4] material PAPER mean={sp['mean']:.3f} area={sp['area']}  ||  "
          f"CONCRETE mean={sc['mean']:.3f} area={sc['area']}")
    print(f"[5] sprinkler OFF mean={s5['off_mean']:.3f} -> ON mean={s5['on_mean']:.3f}")


if __name__ == "__main__":
    main()
