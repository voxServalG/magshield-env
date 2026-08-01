from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_committed_tui_evidence_covers_all_acceptance_states() -> None:
    evidence = ROOT / "docs" / "evidence" / "tui"
    expected = {
        *(f"step-{index}.svg" for index in range(1, 6)),
        "review-blocked.svg",
        "review-exported.svg",
    }

    actual = {path.name for path in evidence.glob("*.svg")}

    assert actual == expected
    for name in expected:
        text = (evidence / name).read_text(encoding="utf-8")
        assert text.startswith("<svg")
        assert "magshield-env" in text
