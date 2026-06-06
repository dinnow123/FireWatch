"""Single source of truth for the FireWatch risk colormap.

The probability-to-color mapping (low risk = dark teal, mid = yellow, high =
red) is defined ONCE here as ``RISK_STOPS`` and consumed two ways so the
verification figures and the live UI can never drift apart:

- ``risk_colormap()`` builds a matplotlib ``LinearSegmentedColormap`` for the
  verification script (``verify_engine.py``) and any other matplotlib plot.
- ``risk_rgb(p)`` returns a plain ``(r, g, b)`` 0-255 tuple by interpolating the
  same stops in pure Python, so the QPainter-based UI widgets can build a
  ``QColor`` without pulling in matplotlib.

Both paths interpolate linearly in RGB over the identical ``RISK_STOPS``, which
is exactly what ``LinearSegmentedColormap.from_list`` does, so the two consumers
produce the same gradient.
"""

from __future__ import annotations

# Canonical risk gradient: position in [0, 1] -> hex color.
# low risk -> dark teal, mid -> yellow, high -> red.
RISK_STOPS: list[tuple[float, str]] = [
    (0.00, "#0b2b30"),
    (0.30, "#178a8f"),
    (0.55, "#f2d43d"),
    (0.78, "#f0871f"),
    (1.00, "#e23030"),
]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# Pre-parsed (position, (r, g, b)) stops for fast pure-Python interpolation.
_RGB_STOPS: list[tuple[float, tuple[int, int, int]]] = [
    (pos, _hex_to_rgb(color)) for pos, color in RISK_STOPS
]


def risk_colormap(name: str = "firewatch_risk"):
    """Return the risk gradient as a matplotlib ``LinearSegmentedColormap``.

    matplotlib is imported lazily so importing this module from the UI (which
    only needs ``risk_rgb``) does not require matplotlib to be installed.
    """
    from matplotlib.colors import LinearSegmentedColormap

    return LinearSegmentedColormap.from_list(name, RISK_STOPS)


def risk_rgb(p: float) -> tuple[int, int, int]:
    """Interpolate ``RISK_STOPS`` at probability ``p`` -> ``(r, g, b)`` 0-255."""
    if p <= 0.0:
        return _RGB_STOPS[0][1]
    if p >= 1.0:
        return _RGB_STOPS[-1][1]
    for (p0, c0), (p1, c1) in zip(_RGB_STOPS, _RGB_STOPS[1:]):
        if p0 <= p <= p1:
            t = (p - p0) / (p1 - p0)
            return (
                round(c0[0] + (c1[0] - c0[0]) * t),
                round(c0[1] + (c1[1] - c0[1]) * t),
                round(c0[2] + (c1[2] - c0[2]) * t),
            )
    return _RGB_STOPS[-1][1]
