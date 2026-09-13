"""The control benchmark runs in CI: reconstruction measured against a
committed OpenAPI spec, with the planted discrepancy caught and zero secrets
in store or exports."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "targets" / "control"))

import score  # noqa: E402


def test_control_benchmark_gates():
    result = score.run()
    assert result["endpoint_recall"] >= 0.95, result
    assert result["endpoint_precision"] >= 0.95, result
    assert result["secrets_leaked"] == 0, "fixture credential reached the store or an export"
    assert result["spec_discrepancy_flagged"] is True, (
        "the planted created_at/created_ts divergence must be flagged by the reconstruction"
    )
    # the reconstruction follows behavior, not the (wrong) documentation
    assert "created_ts" in result["observed_properties"]
    assert "created_at" not in result["observed_properties"]
    # the session was actually observed, both sides
    assert result["requests_recorded"] >= 8
    assert result["responses_recorded"] >= 8
