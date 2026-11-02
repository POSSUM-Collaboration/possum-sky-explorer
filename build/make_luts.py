"""Colormap lookup tables (256 x RGB) for the viewer. Needs matplotlib + cmasher."""
import numpy as np

NAMES = ["RdBu_r", "coolwarm", "viridis", "magma", "inferno", "plasma",
         "cividis", "turbo", "Spectral_r", "cmr.rainforest", "cmr.ember",
         "cmr.iceburn", "cmr.wildfire", "Greys", "twilight"]

def make_luts(names=NAMES):
    import matplotlib
    import cmasher  # noqa: F401  (registers the cmr.* maps)
    luts = {}
    for name in names:
        c = matplotlib.colormaps[name]
        luts[name] = (np.array([c(i / 255.0)[:3] for i in range(256)]) * 255).round().astype(int).tolist()
    return luts

if __name__ == "__main__":
    import json, sys
    json.dump(make_luts(), open(sys.argv[1] if len(sys.argv) > 1 else "luts.json", "w"), separators=(",", ":"))
