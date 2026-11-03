import pandas as pd
import numpy as np

from src.feature_index import build_compact_feature_index


def test_build_compact_feature_index_basic():
    # Construct simple dataframe
    n = 100
    rng = np.random.default_rng(0)
    # low cardinality feature
    f_low = np.random.choice([0, 1], size=n)
    # high skew feature
    f_skew = np.concatenate(
        [rng.exponential(scale=1.0, size=95), rng.exponential(scale=10.0, size=5)])
    # redundant feature (copy of skew)
    f_red = f_skew * 1.0
    labels = np.array(["BENIGN"] * 80 + ["ATTACK"] * 20)

    df = pd.DataFrame({"low_card": f_low, "skewed": f_skew,
                      "red": f_red, "Label": labels})

    idx = build_compact_feature_index(df)

    assert "low_card" in idx and "skewed" in idx and "red" in idx

    # low_card should show low unique values
    assert idx["low_card"]["unique_values"] <= 3
    assert "cardinality_ratio" in idx["low_card"]

    # skewed should include a skewness value
    assert idx["skewed"]["skewness"] is not None

    # redundancy: red and skewed should be flagged as partners
    red_partners = [p["feature"] for p in idx["red"]["redundancy"]]
    assert "skewed" in red_partners or "red" in red_partners
