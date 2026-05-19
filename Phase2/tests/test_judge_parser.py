import pytest

from judge.judge_parser import parse_judge_response


def test_parse_judge_response_accepts_valid_payload():
    payload = """
    {
      "behavior_summary": "The agent balances exploration and confirmation with moderate redundancy.",
      "key_patterns": [
        {
          "statement": "Confirmation behavior appears repeatedly.",
          "evidence": ["aggregate.step_type_frequency", "run_cards.step_trace"],
          "confidence": "high"
        }
      ],
      "weaknesses": [],
      "strengths": [],
      "recommendations": []
    }
    """

    result = parse_judge_response(payload)

    assert result["behavior_summary"].startswith("The agent")
    assert result["key_patterns"][0]["confidence"] == "high"


def test_parse_judge_response_rejects_indexed_evidence():
    payload = """
    {
      "behavior_summary": "test",
      "key_patterns": [
        {
          "statement": "bad evidence",
          "evidence": ["run_cards[0].step_trace[4]"],
          "confidence": "medium"
        }
      ],
      "weaknesses": [],
      "strengths": [],
      "recommendations": []
    }
    """

    with pytest.raises(ValueError):
        parse_judge_response(payload)


def test_parse_judge_response_rejects_unknown_top_level_fields():
    payload = """
    {
      "behavior_summary": "test",
      "key_patterns": [],
      "weaknesses": [],
      "strengths": [],
      "recommendations": [],
      "score": 10
    }
    """

    with pytest.raises(ValueError):
        parse_judge_response(payload)
