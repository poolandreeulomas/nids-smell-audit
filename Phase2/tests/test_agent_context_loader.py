from pathlib import Path

from prompts import context_loader
from prompts.context_loader import get_agent_partition_context


def test_get_agent_partition_context_maps_known_partitions():
    assert "normal user activity" in get_agent_partition_context(
        "Monday-WorkingHours.csv")
    assert "repeated authentication attempts" in get_agent_partition_context(
        "Tuesday-WorkingHours-FTP-Patator.csv"
    )
    assert "high-volume traffic patterns" in get_agent_partition_context(
        "Wednesday-WorkingHours-DDos.csv"
    )
    assert "application-layer interactions" in get_agent_partition_context(
        "Thursday-Morning-WebAttacks.csv"
    )
    assert "multi-stage activity" in get_agent_partition_context(
        "Thursday-Afternoon-Infiltration.csv"
    )
    assert "coordinated and repetitive activity" in get_agent_partition_context(
        "Friday-WorkingHours-Afternoon-PortScan.csv"
    )


def test_get_agent_partition_context_uses_judge_priority_for_ambiguous_names():
    context = get_agent_partition_context("Monday-WorkingHours-DDos.csv")

    assert "high-volume traffic patterns" in context
    assert "normal user activity" not in context


def test_get_agent_partition_context_returns_empty_for_unknown_partitions():
    assert get_agent_partition_context("mystery_partition.csv") == ""


def test_get_agent_partition_context_is_deterministic_after_normalization():
    reference = get_agent_partition_context("Thursday-Morning-WebAttacks.csv")

    assert reference == get_agent_partition_context(
        "thursday_morning_webattacks")
    assert reference == get_agent_partition_context(
        "Thursday.Morning.WebAttacks.CSV")


def test_context_files_are_cached_after_first_read(monkeypatch):
    context_loader._read_context_file.cache_clear()
    target_path = context_loader._CONTEXT_DIR / "ddos.txt"
    read_calls: list[Path] = []
    original_read_text = Path.read_text

    def _counting_read_text(self: Path, *args, **kwargs):
        if self == target_path:
            read_calls.append(self)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read_text)

    first = get_agent_partition_context("Wednesday-WorkingHours-DDos.csv")
    second = get_agent_partition_context("Wednesday-WorkingHours-DDos.csv")

    assert first == second
    assert len(read_calls) == 1
