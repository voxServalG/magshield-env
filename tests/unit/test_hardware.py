import numpy as np
import pytest

from magshield_env.environment import HardwareLimits


def test_legal_interval_intersects_current_slew_and_resistive_voltage() -> None:
    hardware = HardwareLimits(
        current_min_a=np.array([-2.0, -4.0]),
        current_max_a=np.array([2.0, 4.0]),
        slew_rate_a_per_s=np.array([1.0, 4.0]),
        resistance_ohm=np.array([2.0, 1.0]),
        voltage_max_v=np.array([1.0, 3.0]),
    )

    lower, upper = hardware.legal_current_interval(
        previous_currents_a=np.array([0.4, -2.5]), timestep_s=0.5
    )

    np.testing.assert_allclose(lower, np.array([-0.1, -3.0]))
    np.testing.assert_allclose(upper, np.array([0.5, -0.5]))


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("current_max_a", np.array([-3.0, 4.0]), "current_min_a"),
        ("slew_rate_a_per_s", np.array([0.0, 1.0]), "strictly positive"),
        ("resistance_ohm", np.array([1.0, 0.0]), "strictly positive"),
        ("voltage_max_v", np.array([1.0, np.nan]), "finite"),
    ],
)
def test_hardware_rejects_invalid_contracts(
    field: str, replacement: np.ndarray, message: str
) -> None:
    values = {
        "current_min_a": np.array([-2.0, -4.0]),
        "current_max_a": np.array([2.0, 4.0]),
        "slew_rate_a_per_s": np.array([1.0, 4.0]),
        "resistance_ohm": np.array([2.0, 1.0]),
        "voltage_max_v": np.array([1.0, 3.0]),
    }
    values[field] = replacement

    with pytest.raises(ValueError, match=message):
        HardwareLimits(**values)
