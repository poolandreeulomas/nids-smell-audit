from data.validation import validate_feature_name


def test_validate_feature_name_accepts_common_abbreviated_aliases():
    valid_features = [
        "Total Fwd Packets",
        "Total Backward Packets",
        "Total Length of Fwd Packets",
    ]

    canonical = validate_feature_name("Total Bwd Packets", valid_features)

    assert canonical == "Total Backward Packets"
