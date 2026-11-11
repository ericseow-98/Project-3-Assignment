"""Load the raw WM-811K pickle, keep labelled wafers only, and save a smaller file.

Usage (from the project root):
    python src/prepare_data.py

Input:  LSWMD.pkl            (raw Kaggle file, Python 2 pickle, ~2 GB)
Output: data/labelled.pkl    (labelled wafers only, modern pickle)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pandas.core.indexes
from pandas.compat import pickle_compat

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "LSWMD.pkl"
OUT_PATH = ROOT / "data" / "labelled.pkl"


def load_raw(path=RAW_PATH):
    # The file was pickled under Python 2 with an old pandas, so it needs the
    # old module path aliased and latin1 decoding.
    sys.modules["pandas.indexes"] = pandas.core.indexes
    with open(path, "rb") as f:
        return pickle_compat.Unpickler(f, encoding="latin1").load()


def unwrap(x):
    """Labels are stored as nested arrays like [['Center']]; empty means unlabelled."""
    return x[0][0] if len(x) > 0 else None


def main():
    df = load_raw()
    print(f"Raw: {df.shape[0]:,} wafers, {df['lotName'].nunique():,} lots")

    df["failureType"] = df["failureType"].apply(unwrap)
    df["trianTestLabel"] = df["trianTestLabel"].apply(unwrap)
    df = df.rename(columns={"trianTestLabel": "trainTestLabel"})

    df = df[df["failureType"].notna()].reset_index(drop=True)
    df["waferIndex"] = df["waferIndex"].astype(int)
    df["waferMap"] = df["waferMap"].apply(lambda m: np.asarray(m, dtype=np.uint8))
    df["n_rows"] = df["waferMap"].apply(lambda m: m.shape[0])
    df["n_cols"] = df["waferMap"].apply(lambda m: m.shape[1])

    print(f"Labelled: {df.shape[0]:,} wafers, {df['lotName'].nunique():,} lots")
    print(df["failureType"].value_counts().to_string())

    OUT_PATH.parent.mkdir(exist_ok=True)
    df.to_pickle(OUT_PATH)
    print(f"Saved {OUT_PATH} ({OUT_PATH.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
