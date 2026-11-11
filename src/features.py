"""Turn a variable-size wafer map into a fixed-length feature vector.

Wafer map encoding: 0 = no die, 1 = good die, 2 = defective die.

All features are ratios or normalised positions, so wafers of any size are comparable.
Feature groups:
    global    - overall defect density, wafer size
    ring      - defect density in 4 concentric rings (centre -> edge)
    edge      - defect density in 4 edge quadrants + asymmetry (Edge-Ring vs Edge-Loc)
    grid      - defect density in a 3x3 grid over the wafer (where a local blob sits)
    radon     - Radon transform profiles (lines -> Scratch, rings/blobs -> Edge-Ring/Center)
    geom      - shape of the largest connected defect cluster
"""
import numpy as np
from scipy.interpolate import interp1d
from skimage import measure
from skimage.transform import radon

N_RADON_ANGLES = 60
N_RADON_POINTS = 20
RING_EDGES = [0.0, 0.25, 0.5, 0.75, np.inf]
EDGE_START = 0.75  # normalised radius where the "edge" zone begins

GEOM_NAMES = ["n_clusters_per_die", "largest_area_frac", "largest_share_of_defects",
              "largest_perimeter_norm", "largest_major_axis_norm", "largest_eccentricity",
              "largest_solidity", "largest_extent", "largest_dist_from_centre"]

FEATURE_NAMES = (
    ["log_n_die", "density"]
    + [f"ring_{i}" for i in range(4)]
    + ["edge_top", "edge_right", "edge_bottom", "edge_left", "edge_asymmetry"]
    + [f"grid_{r}{c}" for r in range(3) for c in range(3)]
    + [f"radon_mean_{i:02d}" for i in range(N_RADON_POINTS)]
    + [f"radon_std_{i:02d}" for i in range(N_RADON_POINTS)]
    + GEOM_NAMES
)


def _rate(bad, mask):
    n = mask.sum()
    return (bad & mask).sum() / n if n else 0.0


def _coords(on):
    """Normalised coordinates (y, x in [-1, 1]) and radius, centred on the dies' bounding box."""
    rows, cols = np.nonzero(on)
    cy, cx = (rows.min() + rows.max()) / 2, (cols.min() + cols.max()) / 2
    hy = max((rows.max() - rows.min()) / 2, 1)
    hx = max((cols.max() - cols.min()) / 2, 1)
    r, c = np.indices(on.shape)
    y, x = (r - cy) / hy, (c - cx) / hx
    return y, x, np.hypot(y, x), (cy, cx, hy, hx)


def _resample(profile, n=N_RADON_POINTS):
    return interp1d(np.linspace(0, 1, len(profile)), profile)(np.linspace(0, 1, n))


def radon_features(on, bad):
    # Divide by the transform of the wafer outline, so each value is the defect *fraction*
    # along a projection line rather than a raw count (which would scale with wafer size).
    theta = np.linspace(0, 180, N_RADON_ANGLES, endpoint=False)
    sino_bad = radon(bad.astype(float), theta=theta, circle=False)
    sino_on = radon(on.astype(float), theta=theta, circle=False)
    frac = np.divide(sino_bad, sino_on, out=np.zeros_like(sino_bad), where=sino_on > 0.5)
    return _resample(frac.mean(axis=1)), _resample(frac.std(axis=1))


def geometry_features(bad, n_die, centre):
    labels = measure.label(bad, connectivity=2)
    props = measure.regionprops(labels)
    if not props:
        return [0.0] * len(GEOM_NAMES)
    p = max(props, key=lambda q: q.area)
    cy, cx, hy, hx = centre
    diameter = 2 * max(hy, hx)
    return [
        len(props) / n_die,
        p.area / n_die,
        p.area / bad.sum(),
        p.perimeter / np.sqrt(n_die),
        p.axis_major_length / diameter,
        p.eccentricity,
        p.solidity,
        p.extent,
        np.hypot((p.centroid[0] - cy) / hy, (p.centroid[1] - cx) / hx),
    ]


def extract_features(wafer_map):
    m = np.asarray(wafer_map)
    on, bad = m > 0, m == 2
    n_die = int(on.sum())
    y, x, dist, centre = _coords(on)

    feats = [np.log(n_die), bad.sum() / n_die]

    feats += [_rate(bad, on & (dist >= lo) & (dist < hi))
              for lo, hi in zip(RING_EDGES[:-1], RING_EDGES[1:])]

    edge = on & (dist >= EDGE_START)
    angle = np.arctan2(-y, x)  # 0 = right, pi/2 = top
    quadrants = [
        np.abs(angle - np.pi / 2) <= np.pi / 4,                      # top
        np.abs(angle) < np.pi / 4,                                    # right
        np.abs(angle + np.pi / 2) <= np.pi / 4,                      # bottom
        np.abs(np.abs(angle) - np.pi) < np.pi / 4,                    # left
    ]
    edge_rates = [_rate(bad, edge & q) for q in quadrants]
    feats += edge_rates + [max(edge_rates) - min(edge_rates)]

    bins = [-np.inf, -1 / 3, 1 / 3, np.inf]
    for r in range(3):
        for c in range(3):
            cell = on & (y >= bins[r]) & (y < bins[r + 1]) & (x >= bins[c]) & (x < bins[c + 1])
            feats.append(_rate(bad, cell))

    r_mean, r_std = radon_features(on, bad)
    feats += list(r_mean) + list(r_std)

    feats += geometry_features(bad, n_die, centre)
    return np.asarray(feats, dtype=np.float32)
