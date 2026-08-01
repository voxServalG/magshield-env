from collections.abc import Callable
from typing import Literal

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from magshield_env.environment import (
    ActionConfig,
    DynamicLinearPlant,
    FixedLinearPlant,
    HardwareLimits,
    MagneticControlEnv,
    RewardConfig,
    Scenario,
)


def _hardware() -> HardwareLimits:
    return HardwareLimits(
        current_min_a=np.array([-2.0, -2.0]),
        current_max_a=np.array([2.0, 2.0]),
        slew_rate_a_per_s=np.array([1.0, 1.0]),
        resistance_ohm=np.array([2.0, 1.0]),
        voltage_max_v=np.array([4.0, 2.0]),
    )


def _reward(*, nominal: bool = False) -> RewardConfig:
    return RewardConfig(
        field_threshold_t=0.0,
        field_scale_t=1.0,
        field_weight=2.0,
        power_scale_w=1.0,
        power_weight=0.5,
        slew_scale_a=1.0,
        slew_weight=0.25,
        constraint_scale_a=1.0,
        constraint_weight=4.0,
        nominal_currents_a=np.array([0.0, 0.0]) if nominal else None,
        nominal_scale_a=1.0 if nominal else None,
        nominal_weight=0.25 if nominal else None,
    )


def _fixed_env(
    mode: Literal["project_and_report", "terminate"] = "project_and_report",
    *,
    nominal: bool = False,
) -> MagneticControlEnv:
    matrix = np.zeros((1, 3, 2), dtype=np.float64)
    matrix[0, 0, 0] = -1.0
    matrix[0, 1, 1] = -1.0
    return MagneticControlEnv(
        plant=FixedLinearPlant(matrix),
        hardware=_hardware(),
        scenario=Scenario(
            external_field_t=np.array([[1.0, 0.0, 0.0]]),
            episode_length=2,
        ),
        action_config=ActionConfig(delta_scale_a=np.array([1.0, 1.0]), constraint_mode=mode),
        reward_config=_reward(nominal=nominal),
        timestep_s=0.5,
        include_pose=False,
    )


def test_reset_and_step_follow_gymnasium_contract_and_reward_decomposition() -> None:
    env = _fixed_env(nominal=True)
    observation, reset_info = env.reset(seed=9)

    assert env.observation_space.contains(observation)
    assert env.action_space.contains(np.array([0.5, 0.0]))
    np.testing.assert_allclose(observation, np.array([1.0, 0.0, 0.0, 0.0, 0.0]))
    assert reset_info["scenario_frame"] == 0

    next_observation, reward, terminated, truncated, info = env.step(np.array([0.5, 0.0]))

    np.testing.assert_allclose(next_observation, np.array([0.5, 0.0, 0.0, 0.5, 0.0]))
    assert not terminated
    assert not truncated
    assert info["constraint"]["violated"] is False
    terms = info["reward_terms"]
    expected = -(
        terms["weighted_field_cost"]
        + terms["weighted_power_cost"]
        + terms["weighted_slew_cost"]
        + terms["weighted_constraint_cost"]
        + terms["weighted_nominal_cost"]
    )
    assert reward == pytest.approx(expected)

    _, _, _, truncated, _ = env.step(np.array([0.0, 0.0]))
    assert truncated
    with pytest.raises(RuntimeError, match="reset"):
        env.step(np.array([0.0, 0.0]))


def test_project_and_report_never_silently_clips() -> None:
    env = _fixed_env("project_and_report")
    env.reset(seed=1)

    _, reward, terminated, truncated, info = env.step(np.array([2.0, 0.0]))

    assert not terminated
    assert not truncated
    constraint = info["constraint"]
    assert constraint["violated"] is True
    assert constraint["projected"] is True
    np.testing.assert_allclose(constraint["proposed_currents_a"], [2.0, 0.0])
    np.testing.assert_allclose(constraint["applied_currents_a"], [0.5, 0.0])
    np.testing.assert_allclose(constraint["legal_current_max_a"], [0.5, 0.5])
    assert constraint["violation_a"][0] == pytest.approx(1.5)
    assert info["reward_terms"]["weighted_constraint_cost"] > 0.0
    assert reward < 0.0


def test_terminate_mode_rejects_action_without_changing_current() -> None:
    env = _fixed_env("terminate")
    initial_observation, _ = env.reset(seed=1)

    observation, _, terminated, truncated, info = env.step(np.array([2.0, 0.0]))

    assert terminated
    assert not truncated
    assert info["constraint"]["violated"] is True
    assert info["constraint"]["projected"] is False
    np.testing.assert_allclose(env.currents_a, np.zeros(2))
    np.testing.assert_allclose(observation, initial_observation)


def test_dynamic_plant_observation_includes_pose_and_uses_current_frame() -> None:
    calls: list[np.ndarray] = []

    def response(pose: np.ndarray) -> np.ndarray:
        calls.append(pose)
        matrix = np.zeros((1, 3, 2))
        matrix[0, 0, 0] = pose[0]
        return matrix

    env = MagneticControlEnv(
        plant=DynamicLinearPlant(response, point_count=1, channel_count=2),
        hardware=_hardware(),
        scenario=Scenario(
            external_field_t=np.zeros((2, 1, 3)),
            pose=np.array([[2.0], [3.0]]),
            episode_length=2,
        ),
        action_config=ActionConfig(delta_scale_a=np.ones(2), constraint_mode="project_and_report"),
        reward_config=_reward(),
        timestep_s=0.5,
        include_pose=True,
    )

    observation, _ = env.reset(seed=3)
    np.testing.assert_allclose(observation, [0.0, 0.0, 0.0, 0.0, 0.0, 2.0])
    observation, *_ = env.step(np.array([0.5, 0.0]))
    np.testing.assert_allclose(observation, [1.0, 0.0, 0.0, 0.5, 0.0, 2.0])
    env.step(np.array([0.0, 0.0]))
    np.testing.assert_allclose(calls[-1], [3.0])


def test_fixed_plant_allows_pose_as_observation_without_changing_response() -> None:
    matrix = np.zeros((1, 3, 2), dtype=np.float64)
    env = MagneticControlEnv(
        plant=FixedLinearPlant(matrix),
        hardware=_hardware(),
        scenario=Scenario(
            external_field_t=np.zeros((1, 3)),
            pose=np.array([1.0, 2.0, 3.0]),
            episode_length=1,
        ),
        action_config=ActionConfig(delta_scale_a=np.ones(2), constraint_mode="project_and_report"),
        reward_config=_reward(),
        timestep_s=0.5,
        include_pose=True,
    )

    observation, _ = env.reset(seed=3)

    np.testing.assert_allclose(observation[-3:], [1.0, 2.0, 3.0])


def test_observation_basis_projects_full_vector_residual() -> None:
    matrix = np.zeros((1, 3, 2), dtype=np.float64)
    basis = np.array([[[1.0, 0.0, 0.0]], [[0.0, 0.0, 2.0]]])
    env = MagneticControlEnv(
        plant=FixedLinearPlant(matrix),
        hardware=_hardware(),
        scenario=Scenario(
            external_field_t=np.array([[1.0, 2.0, 3.0]]),
            episode_length=1,
        ),
        action_config=ActionConfig(delta_scale_a=np.ones(2), constraint_mode="project_and_report"),
        reward_config=_reward(),
        timestep_s=0.5,
        observation_basis=basis,
        include_pose=False,
    )

    observation, _ = env.reset(seed=3)

    np.testing.assert_allclose(observation, [1.0, 6.0, 0.0, 0.0])
    assert env.observation_space.shape == (4,)


@pytest.mark.parametrize(
    "basis",
    [np.zeros((2, 2, 3)), np.array([[[np.nan, 0.0, 0.0]]])],
)
def test_observation_basis_rejects_wrong_point_count_or_nonfinite_values(
    basis: np.ndarray,
) -> None:
    with pytest.raises(ValueError, match="observation_basis"):
        MagneticControlEnv(
            plant=FixedLinearPlant(np.zeros((1, 3, 2))),
            hardware=_hardware(),
            scenario=Scenario(np.zeros((1, 3)), episode_length=1),
            action_config=ActionConfig(
                delta_scale_a=np.ones(2), constraint_mode="project_and_report"
            ),
            reward_config=_reward(),
            timestep_s=0.5,
            observation_basis=basis,
            include_pose=False,
        )


def test_seed_reproducibly_selects_random_trajectory_window() -> None:
    fields = np.zeros((6, 1, 3))
    fields[:, 0, 0] = np.arange(6)
    scenario = Scenario(fields, episode_length=2, random_start=True)
    matrix = np.zeros((1, 3, 2))

    def make() -> MagneticControlEnv:
        return MagneticControlEnv(
            plant=FixedLinearPlant(matrix),
            hardware=_hardware(),
            scenario=scenario,
            action_config=ActionConfig(
                delta_scale_a=np.ones(2), constraint_mode="project_and_report"
            ),
            reward_config=_reward(),
            timestep_s=0.5,
            include_pose=False,
        )

    first, first_info = make().reset(seed=1234)
    second, second_info = make().reset(seed=1234)
    np.testing.assert_array_equal(first, second)
    assert first_info["scenario_frame"] == second_info["scenario_frame"]


def test_point_weights_control_spatial_field_rms() -> None:
    env = MagneticControlEnv(
        plant=FixedLinearPlant(np.zeros((2, 3, 2), dtype=np.float64)),
        hardware=_hardware(),
        scenario=Scenario(
            external_field_t=np.array([[1.0, 0.0, 0.0], [3.0, 0.0, 0.0]]),
            episode_length=1,
        ),
        action_config=ActionConfig(delta_scale_a=np.ones(2), constraint_mode="project_and_report"),
        reward_config=_reward(),
        timestep_s=0.5,
        point_weights=np.array([3.0, 1.0]),
        include_pose=False,
    )

    _, info = env.reset(seed=3)
    _, _, _, _, step_info = env.step(np.zeros(2))

    assert info["field_rms_t"] == pytest.approx(np.sqrt(3.0))
    assert step_info["reward_terms"]["field_rms_t"] == pytest.approx(np.sqrt(3.0))


def test_field_rms_is_vector_magnitude_rms_and_weight_scale_invariant() -> None:
    def reset_rms(weights: np.ndarray) -> float:
        env = MagneticControlEnv(
            plant=FixedLinearPlant(np.zeros((2, 3, 2), dtype=np.float64)),
            hardware=_hardware(),
            scenario=Scenario(
                external_field_t=np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 0.0]]),
                episode_length=1,
            ),
            action_config=ActionConfig(
                delta_scale_a=np.ones(2), constraint_mode="project_and_report"
            ),
            reward_config=_reward(),
            timestep_s=0.5,
            point_weights=weights,
            include_pose=False,
        )
        _, info = env.reset(seed=3)
        return float(info["field_rms_t"])

    assert reset_rms(np.array([1.0, 1.0])) == pytest.approx(np.sqrt(1.5))
    assert reset_rms(np.array([7.0, 7.0])) == pytest.approx(np.sqrt(1.5))


@pytest.mark.parametrize(
    "weights",
    [np.array([1.0]), np.array([1.0, 0.0]), np.array([1.0, -1.0])],
)
def test_invalid_point_weights_are_rejected(weights: np.ndarray) -> None:
    with pytest.raises(ValueError, match="point_weights"):
        MagneticControlEnv(
            plant=FixedLinearPlant(np.zeros((2, 3, 2), dtype=np.float64)),
            hardware=_hardware(),
            scenario=Scenario(np.zeros((2, 3)), episode_length=1),
            action_config=ActionConfig(
                delta_scale_a=np.ones(2), constraint_mode="project_and_report"
            ),
            reward_config=_reward(),
            timestep_s=0.5,
            point_weights=weights,
            include_pose=False,
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ActionConfig(np.ones(2), "clip"),  # type: ignore[arg-type]
        lambda: RewardConfig(
            field_threshold_t=0.0,
            field_scale_t=1.0,
            field_weight=1.0,
            power_scale_w=1.0,
            power_weight=1.0,
            slew_scale_a=1.0,
            slew_weight=1.0,
            constraint_scale_a=1.0,
            constraint_weight=1.0,
            nominal_currents_a=np.zeros(2),
        ),
    ],
)
def test_behavior_configuration_rejects_implicit_or_unknown_choices(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(ValueError):
        factory()


def test_environment_passes_gymnasium_checker() -> None:
    check_env(_fixed_env(), skip_render_check=True)
