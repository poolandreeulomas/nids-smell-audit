import pandas as pd
import numpy as np

from src.feature_index import build_compact_feature_index, get_candidate_features


def _build_df_fixture():
    n = 100
    rng = np.random.default_rng(1)
    f_low = np.random.choice([0, 1], size=n)
    f_skew = np.concatenate(
        [rng.exponential(scale=1.0, size=95), rng.exponential(scale=10.0, size=5)])
    f_red = f_skew * 1.0
    labels = np.array(["BENIGN"] * 80 + ["ATTACK"] * 20)
    df = pd.DataFrame({"low_card": f_low, "skewed": f_skew,
                      "red": f_red, "Label": labels})
    return df


def test_get_candidate_features_low_cardinality():
    df = _build_df_fixture()
    summaries = build_compact_feature_index(df)
    cands = get_candidate_features("low cardinality", summaries=summaries)
    assert isinstance(cands, list) and cands
    # first candidate should be low_card
    assert cands[0]["feature_name"] == "low_card"
    assert any("unique_values" in s or s.startswith("unique_values")
               or s.startswith("cardinality_ratio") for s in cands[0]["signals"])


def test_get_candidate_features_high_skew_and_redundancy():
    df = _build_df_fixture()
    summaries = build_compact_feature_index(df)
    skew_cands = get_candidate_features("high skew", summaries=summaries)
    assert skew_cands and any(
        c["feature_name"] == "skewed" for c in skew_cands)

    red_cands = get_candidate_features("redundancy", summaries=summaries)
    assert isinstance(red_cands, list)
    # red should appear with a redundancy signal mentioning skewed or red
    assert any(c["feature_name"] == "red" or any(
        "redundant_with" in s for s in c["signals"]) for c in red_cands)
