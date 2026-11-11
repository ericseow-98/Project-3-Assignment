"""Extract features for every labelled wafer and assign a lot-grouped, stratified train/test split.

Usage (from the project root, after src/prepare_data.py):
    python src/build_features.py

Input:  data/labelled.pkl
Output: data/features.parquet  (one row per wafer: ids, label, split, 69 features)
"""
import time
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from sklearn.model_selection import StratifiedGroupKFold

from features import FEATURE_NAMES, extract_features

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "labelled.pkl"
OUT_PATH = ROOT / "data" / "features.parquet"
TEST_FOLDS = 5          # 1 of 5 folds -> ~20% test
RANDOM_STATE = 42


def assign_split(df):
    """~20% of lots go to test; no lot appears in both sets; class mix kept similar."""
    sgkf = StratifiedGroupKFold(n_splits=TEST_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    _, test_idx = next(sgkf.split(df, df["failureType"], groups=df["lotName"]))
    split = np.full(len(df), "train", dtype=object)
    split[test_idx] = "test"
    return split


def main():
    df = pd.read_pickle(IN_PATH)
    print(f"Extracting {len(FEATURE_NAMES)} features from {len(df):,} wafers...")

    t0 = time.time()
    X = Parallel(n_jobs=-1, batch_size=256)(delayed(extract_features)(m) for m in df["waferMap"])
    print(f"Done in {time.time() - t0:.0f}s")

    out = pd.concat(
        [df[["lotName", "waferIndex", "dieSize", "failureType"]].reset_index(drop=True),
         pd.DataFrame(np.vstack(X), columns=FEATURE_NAMES)],
        axis=1,
    )
    out.insert(4, "split", assign_split(out))

    assert not set(out.loc[out.split == "train", "lotName"]) & set(out.loc[out.split == "test", "lotName"])
    assert np.isfinite(out[FEATURE_NAMES].to_numpy()).all()

    out.to_parquet(OUT_PATH, index=False)
    print(out["split"].value_counts().to_string())
    print(f"Saved {OUT_PATH}")


if __name__ == "__main__":
    main()
