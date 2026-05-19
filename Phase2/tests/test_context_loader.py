import pytest

from judge.context_loader import get_judge_partition_context


@pytest.mark.parametrize(
    ("partition_name", "expected_phrase", "unexpected_phrase"),
    [
        (
            "Monday-WorkingHours.csv",
            "normal user traffic and heterogeneous, non-attack behavior",
            "repeated login attempts and structured repetition",
        ),
        (
            "Tuesday-WorkingHours-FTP-Patator.csv",
            "repeated login attempts and structured repetition",
            "saturation, spikes, and load",
        ),
        (
            "Wednesday-workingHours-DDos.csv",
            "saturation, spikes, and load",
            "multi-stage attack and post-compromise behavior",
        ),
        (
            "Friday-WorkingHours-Afternoon-PortScan.csv",
            "scanning behavior with high repetition",
            "application-layer attacks such as XSS, SQLi, or brute force on forms",
        ),
        (
            "Thursday-Morning-WebAttacks.csv",
            "application-layer attacks such as XSS, SQLi, or brute force on forms",
            "normal user traffic and heterogeneous, non-attack behavior",
        ),
        (
            "Thursday-Afternoon-Infiltration.csv",
            "multi-stage attack and post-compromise behavior",
            "scanning behavior with high repetition",
        ),
    ],
)
def test_get_judge_partition_context_maps_known_partitions(
    partition_name, expected_phrase, unexpected_phrase
):
    context = get_judge_partition_context(partition_name)

    assert expected_phrase in context
    assert unexpected_phrase not in context


def test_get_judge_partition_context_prefers_attack_tokens_in_ambiguous_names():
    context = get_judge_partition_context("Monday-WorkingHours-DDos.csv")

    assert "saturation, spikes, and load" in context
    assert "normal user traffic and heterogeneous, non-attack behavior" not in context


def test_get_judge_partition_context_uses_generic_fallback_for_unknown_partitions():
    context = get_judge_partition_context("mystery_partition.csv")

    assert "network traffic without a reliable phenomenon label" in context
    assert "application-layer attacks such as XSS, SQLi, or brute force on forms" not in context


def test_get_judge_partition_context_is_deterministic_after_normalization():
    reference = get_judge_partition_context(
        "Friday-WorkingHours-Afternoon-DDos.csv")

    assert reference == get_judge_partition_context(
        "friday_workinghours_afternoon_ddos")
    assert reference == get_judge_partition_context(
        "Friday.WorkingHours.Afternoon.DDos.CSV")
