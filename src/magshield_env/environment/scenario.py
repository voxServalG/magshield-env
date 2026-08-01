"""External-field and pose trajectories."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class Scenario:
    """Provide exogenous field and pose frames for one episode.

    ``external_field_t`` is either one static ``[point, 3]`` field or a
    ``[frame, point, 3]`` recording. ``pose`` follows the same static/trajectory
    convention with shapes ``[component]`` or ``[frame, component]``.
    ``episode_length`` bounds each episode, while ``random_start`` uses the
    Gymnasium reset seed to choose a reproducible contiguous window.
    """

    external_field_t: FloatArray
    episode_length: int
    pose: FloatArray | None = None
    random_start: bool = False

    def __post_init__(self) -> None:
        field = np.asarray(self.external_field_t, dtype=np.float64)
        if field.ndim not in (2, 3) or field.shape[-1] != 3:
            raise ValueError("external_field_t must have shape [point, 3] or [frame, point, 3]")
        if field.shape[-2] == 0 or (field.ndim == 3 and field.shape[0] == 0):
            raise ValueError("external_field_t must contain points and frames")
        if not np.all(np.isfinite(field)):
            raise ValueError("external_field_t must contain only finite values")
        if not isinstance(self.episode_length, int) or self.episode_length <= 0:
            raise ValueError("episode_length must be a positive integer")
        object.__setattr__(self, "external_field_t", field.copy())

        if self.pose is not None:
            pose = np.asarray(self.pose, dtype=np.float64)
            if pose.ndim not in (1, 2) or pose.shape[-1] == 0:
                raise ValueError("pose must have shape [component] or [frame, component]")
            if pose.ndim == 2 and pose.shape[0] == 0:
                raise ValueError("pose trajectory must contain frames")
            if not np.all(np.isfinite(pose)):
                raise ValueError("pose must contain only finite values")
            object.__setattr__(self, "pose", pose.copy())

        trajectory_lengths = self._trajectory_lengths()
        if trajectory_lengths and len(set(trajectory_lengths)) != 1:
            raise ValueError("field and pose trajectories must have equal frame counts")
        if trajectory_lengths and self.episode_length > trajectory_lengths[0]:
            raise ValueError("episode_length exceeds the available trajectory frames")
        if self.random_start and not trajectory_lengths:
            raise ValueError("random_start requires a field or pose trajectory")

    @property
    def point_count(self) -> int:
        return int(self.external_field_t.shape[-2])

    @property
    def pose_size(self) -> int:
        return 0 if self.pose is None else int(self.pose.shape[-1])

    @property
    def total_frames(self) -> int | None:
        lengths = self._trajectory_lengths()
        return None if not lengths else lengths[0]

    def choose_start(self, rng: np.random.Generator) -> int:
        if not self.random_start:
            return 0
        total_frames = self.total_frames
        if total_frames is None:
            raise RuntimeError("random_start scenario has no trajectory")
        max_start = total_frames - self.episode_length
        return int(rng.integers(0, max_start + 1))

    def frame(self, index: int) -> tuple[FloatArray, FloatArray | None]:
        if index < 0:
            raise ValueError("frame index must be non-negative")
        field = (
            self.external_field_t
            if self.external_field_t.ndim == 2
            else self.external_field_t[index]
        )
        pose = None if self.pose is None else self.pose if self.pose.ndim == 1 else self.pose[index]
        return field, pose

    def _trajectory_lengths(self) -> list[int]:
        lengths: list[int] = []
        if self.external_field_t.ndim == 3:
            lengths.append(int(self.external_field_t.shape[0]))
        if self.pose is not None and self.pose.ndim == 2:
            lengths.append(int(self.pose.shape[0]))
        return lengths
