"""Gymnasium environment for linear magnetic-field control."""

from __future__ import annotations

from typing import Any, cast

import gymnasium as gym
import numpy as np
from gymnasium import spaces
from numpy.typing import ArrayLike, NDArray

from .config import ActionConfig, RewardConfig
from .hardware import HardwareLimits, _channel_array
from .plant import LinearPlant
from .scenario import Scenario

FloatArray = NDArray[np.float64]


class MagneticControlEnv(gym.Env[FloatArray, FloatArray]):
    """Expose a validated linear magnetic plant through Gymnasium.

    ``plant`` maps the current vector to a full vector field, while ``scenario``
    supplies the external field and optional geometry pose. ``hardware`` and
    ``timestep_s`` derive the next legal current interval. ``action_config``
    converts normalized current deltas and chooses an explicit violation path;
    ``reward_config`` scores the residual and electrical costs. ``point_weights``
    defines how sampled locations contribute to the spatial field error. The
    optional ``observation_basis`` projects the full residual onto explicitly declared
    ``[basis, point, component]`` weights; otherwise every residual component
    is observed. ``initial_currents_a`` seeds each episode, and ``include_pose``
    controls whether the scenario pose is appended. Together these members
    produce observations containing field information, last applied currents,
    and optionally pose, with no implicit clipping or fallback.
    """

    metadata: dict[str, list[str]] = {"render_modes": []}  # noqa: RUF012

    def __init__(
        self,
        *,
        plant: LinearPlant,
        hardware: HardwareLimits,
        scenario: Scenario,
        action_config: ActionConfig,
        reward_config: RewardConfig,
        timestep_s: float,
        point_weights: ArrayLike | None = None,
        observation_basis: ArrayLike | None = None,
        initial_currents_a: ArrayLike | None = None,
        include_pose: bool = True,
    ) -> None:
        super().__init__()
        if not isinstance(plant, LinearPlant):
            raise TypeError("plant must implement the LinearPlant protocol")
        if not np.isfinite(timestep_s) or timestep_s <= 0.0:
            raise ValueError("timestep_s must be finite and strictly positive")
        if plant.point_count != scenario.point_count:
            raise ValueError("plant and scenario point counts differ")
        if plant.channel_count != hardware.channel_count:
            raise ValueError("plant and hardware channel counts differ")
        if action_config.delta_scale_a.size != hardware.channel_count:
            raise ValueError("action delta scale has the wrong channel count")
        nominal = reward_config.nominal_currents_a
        if nominal is not None and nominal.size != hardware.channel_count:
            raise ValueError("nominal currents have the wrong channel count")
        if include_pose and scenario.pose is None:
            raise ValueError("include_pose=True requires a scenario pose")

        if initial_currents_a is None:
            initial = np.zeros(hardware.channel_count, dtype=np.float64)
        else:
            initial = _channel_array(initial_currents_a, name="initial_currents_a")
        if initial.size != hardware.channel_count:
            raise ValueError("initial currents have the wrong channel count")
        initial_lower, initial_upper = hardware.legal_current_interval(initial, timestep_s)
        absolute_lower = np.maximum(
            hardware.current_min_a,
            -hardware.voltage_max_v / hardware.resistance_ohm,
        )
        absolute_upper = np.minimum(
            hardware.current_max_a,
            hardware.voltage_max_v / hardware.resistance_ohm,
        )
        if np.any(initial < absolute_lower) or np.any(initial > absolute_upper):
            raise ValueError("initial currents violate absolute hardware limits")
        if np.any(initial_lower > initial_upper):
            raise ValueError("initial currents have no legal next-step interval")

        self.plant = plant
        self.hardware = hardware
        self.scenario = scenario
        self.action_config = action_config
        self.reward_config = reward_config
        self.timestep_s = float(timestep_s)
        if point_weights is None:
            weights = np.ones(plant.point_count, dtype=np.float64)
        else:
            weights = _channel_array(point_weights, name="point_weights")
        if weights.size != plant.point_count:
            raise ValueError("point_weights must contain one value per sampled point")
        if np.any(weights <= 0.0):
            raise ValueError("point_weights must be strictly positive")
        self.point_weights = weights.copy()
        if observation_basis is None:
            self.observation_basis: FloatArray | None = None
            field_observation_size = 3 * plant.point_count
        else:
            basis = np.asarray(observation_basis, dtype=np.float64)
            if basis.ndim != 3 or basis.shape[0] == 0:
                raise ValueError("observation_basis must have shape [basis, point, component]")
            if basis.shape[1:] != (plant.point_count, 3):
                raise ValueError(
                    "observation_basis point and component dimensions do not match the plant"
                )
            if not np.all(np.isfinite(basis)):
                raise ValueError("observation_basis must contain only finite values")
            self.observation_basis = basis.copy()
            field_observation_size = int(basis.shape[0])
        self.initial_currents_a = initial.copy()
        self.include_pose = bool(include_pose)

        channel_count = hardware.channel_count
        observation_size = field_observation_size + channel_count
        if self.include_pose:
            observation_size += scenario.pose_size
        self.action_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(channel_count,),
            dtype=np.float64,
        )
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(observation_size,),
            dtype=np.float64,
        )
        self._currents_a = self.initial_currents_a.copy()
        self._episode_step = 0
        self._start_frame = 0
        self._needs_reset = True

    @property
    def currents_a(self) -> FloatArray:
        """Return a copy of the last currents successfully applied."""

        return self._currents_a.copy()

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[FloatArray, dict[str, Any]]:
        super().reset(seed=seed)
        if options:
            unknown = set(options) - {"initial_currents_a", "start_frame"}
            if unknown:
                raise ValueError(f"unknown reset options: {sorted(unknown)}")
        options = options or {}

        currents = options.get("initial_currents_a", self.initial_currents_a)
        currents_array = _channel_array(currents, name="initial_currents_a")
        if currents_array.size != self.hardware.channel_count:
            raise ValueError("reset initial currents have the wrong channel count")
        absolute_lower = np.maximum(
            self.hardware.current_min_a,
            -self.hardware.voltage_max_v / self.hardware.resistance_ohm,
        )
        absolute_upper = np.minimum(
            self.hardware.current_max_a,
            self.hardware.voltage_max_v / self.hardware.resistance_ohm,
        )
        if np.any(currents_array < absolute_lower) or np.any(currents_array > absolute_upper):
            raise ValueError("reset initial currents violate hardware limits")

        if "start_frame" in options:
            start_frame = options["start_frame"]
            if not isinstance(start_frame, int) or start_frame < 0:
                raise ValueError("start_frame must be a non-negative integer")
            total = self.scenario.total_frames
            if total is None and start_frame != 0:
                raise ValueError("a static scenario only supports start_frame=0")
            if total is not None and start_frame + self.scenario.episode_length > total:
                raise ValueError("start_frame does not leave a complete episode")
            self._start_frame = start_frame
        else:
            self._start_frame = self.scenario.choose_start(self.np_random)

        self._currents_a = currents_array.copy()
        self._episode_step = 0
        self._needs_reset = False
        field, pose = self.scenario.frame(self._start_frame)
        residual = self._residual_field(field, pose, self._currents_a)
        observation = self._observation(residual, self._currents_a, pose)
        info = self._base_info(residual, pose, self._start_frame)
        info["reset_seed"] = seed
        return observation, info

    def step(self, action: FloatArray) -> tuple[FloatArray, float, bool, bool, dict[str, Any]]:
        if self._needs_reset:
            raise RuntimeError("reset() must be called before step()")
        action_array = np.asarray(action, dtype=np.float64)
        if action_array.shape != self.action_space.shape:
            raise ValueError(
                f"action must have shape {self.action_space.shape}, got {action_array.shape}"
            )
        if not np.all(np.isfinite(action_array)):
            raise ValueError("action must contain only finite values")

        frame_index = self._start_frame + self._episode_step
        external_field, pose = self.scenario.frame(frame_index)
        lower, upper = self.hardware.legal_current_interval(self._currents_a, self.timestep_s)
        raw_delta = action_array * self.action_config.delta_scale_a
        proposed = self._currents_a + raw_delta
        normalized_violation = np.maximum(np.abs(action_array) - 1.0, 0.0)
        current_violation = np.maximum(lower - proposed, 0.0) + np.maximum(proposed - upper, 0.0)
        violation_a = np.maximum(
            current_violation,
            normalized_violation * self.action_config.delta_scale_a,
        )
        violated = bool(np.any(violation_a > 0.0))

        previous = self._currents_a.copy()
        terminated = False
        if violated and self.action_config.constraint_mode == "terminate":
            applied = previous
            terminated = True
        elif violated:
            normalized_target = previous + (
                np.clip(action_array, -1.0, 1.0) * self.action_config.delta_scale_a
            )
            applied = np.clip(normalized_target, lower, upper)
        else:
            applied = proposed
        self._currents_a = applied.copy()

        residual = self._residual_field(external_field, pose, applied)
        reward, reward_terms = self._reward(
            residual=residual,
            previous_currents=previous,
            applied_currents=applied,
            violation_a=violation_a,
        )
        self._episode_step += 1
        truncated = not terminated and self._episode_step >= self.scenario.episode_length
        self._needs_reset = terminated or truncated

        observation = self._observation(residual, applied, pose)
        info = self._base_info(residual, pose, frame_index)
        info["reward_terms"] = reward_terms
        info["constraint"] = {
            "mode": self.action_config.constraint_mode,
            "violated": violated,
            "projected": violated and self.action_config.constraint_mode == "project_and_report",
            "normalized_action": action_array.copy(),
            "proposed_currents_a": proposed.copy(),
            "applied_currents_a": applied.copy(),
            "legal_current_min_a": lower.copy(),
            "legal_current_max_a": upper.copy(),
            "lower_margin_a": applied - lower,
            "upper_margin_a": upper - applied,
            "violation_a": violation_a.copy(),
        }
        return observation, reward, terminated, truncated, info

    def _residual_field(
        self,
        external_field: FloatArray,
        pose: FloatArray | None,
        currents: FloatArray,
    ) -> FloatArray:
        response = self.plant.response_matrix(pose)
        coil_field = cast(
            FloatArray,
            np.einsum("pcm,m->pc", response, currents, optimize=True),
        )
        residual = external_field + coil_field
        if not np.all(np.isfinite(residual)):
            raise ValueError("computed residual field contains non-finite values")
        return residual

    def _observation(
        self,
        residual: FloatArray,
        currents: FloatArray,
        pose: FloatArray | None,
    ) -> FloatArray:
        if self.observation_basis is None:
            field_observation = residual.reshape(-1)
        else:
            field_observation = cast(
                FloatArray,
                np.einsum(
                    "kpc,pc->k",
                    self.observation_basis,
                    residual,
                    optimize=True,
                ),
            )
        parts = [field_observation, currents]
        if self.include_pose:
            if pose is None:
                raise RuntimeError("pose observation requested without a pose")
            parts.append(pose)
        observation = np.concatenate(parts, dtype=np.float64)
        if not self.observation_space.contains(observation):
            raise RuntimeError("constructed observation violates observation_space")
        return observation

    def _reward(
        self,
        *,
        residual: FloatArray,
        previous_currents: FloatArray,
        applied_currents: FloatArray,
        violation_a: FloatArray,
    ) -> tuple[float, dict[str, float]]:
        config = self.reward_config
        field_rms_t = self._field_rms(residual)
        field_excess = max(field_rms_t - config.field_threshold_t, 0.0)
        field_cost = field_excess / config.field_scale_t
        power_w = float(np.sum(np.square(applied_currents) * self.hardware.resistance_ohm))
        power_cost = power_w / config.power_scale_w
        slew_rms_a = float(np.sqrt(np.mean(np.square(applied_currents - previous_currents))))
        slew_cost = slew_rms_a / config.slew_scale_a
        violation_rms_a = float(np.sqrt(np.mean(np.square(violation_a))))
        constraint_cost = violation_rms_a / config.constraint_scale_a

        weighted_field = config.field_weight * field_cost
        weighted_power = config.power_weight * power_cost
        weighted_slew = config.slew_weight * slew_cost
        weighted_constraint = config.constraint_weight * constraint_cost
        total_cost = weighted_field + weighted_power + weighted_slew + weighted_constraint
        terms = {
            "field_rms_t": field_rms_t,
            "field_excess_t": field_excess,
            "field_cost": field_cost,
            "weighted_field_cost": weighted_field,
            "power_w": power_w,
            "power_cost": power_cost,
            "weighted_power_cost": weighted_power,
            "slew_rms_a": slew_rms_a,
            "slew_cost": slew_cost,
            "weighted_slew_cost": weighted_slew,
            "constraint_violation_rms_a": violation_rms_a,
            "constraint_cost": constraint_cost,
            "weighted_constraint_cost": weighted_constraint,
        }
        nominal = config.nominal_currents_a
        if nominal is not None:
            if config.nominal_scale_a is None or config.nominal_weight is None:
                raise RuntimeError("nominal reward configuration is incomplete")
            nominal_rms_a = float(np.sqrt(np.mean(np.square(applied_currents - nominal))))
            nominal_cost = nominal_rms_a / config.nominal_scale_a
            weighted_nominal = config.nominal_weight * nominal_cost
            total_cost += weighted_nominal
            terms.update(
                {
                    "nominal_deviation_rms_a": nominal_rms_a,
                    "nominal_cost": nominal_cost,
                    "weighted_nominal_cost": weighted_nominal,
                }
            )
        terms["total_cost"] = total_cost
        return -float(total_cost), terms

    def _base_info(
        self, residual: FloatArray, pose: FloatArray | None, frame_index: int
    ) -> dict[str, Any]:
        return {
            "episode_step": self._episode_step,
            "scenario_frame": frame_index,
            "currents_a": self._currents_a.copy(),
            "residual_field_t": residual.copy(),
            "field_rms_t": self._field_rms(residual),
            "pose": None if pose is None else pose.copy(),
        }

    def _field_rms(self, residual: FloatArray) -> float:
        squared_magnitude = np.sum(np.square(residual), axis=1)
        weighted_mean_vector_square = np.sum(
            self.point_weights * squared_magnitude
        ) / np.sum(self.point_weights)
        return float(np.sqrt(weighted_mean_vector_square))
