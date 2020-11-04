"""
(*)~---------------------------------------------------------------------------
Pupil - eye tracking platform
Copyright (C) 2012-2019 Pupil Labs

Distributed under the terms of the GNU
Lesser General Public License (LGPL v3.0).
See COPYING and COPYING.LESSER for license details.
---------------------------------------------------------------------------~(*)
"""
import abc
import typing as T

import numpy as np

from ..geometry.primitives import Circle
from ..observation import Observation, ObservationStorage
from ..camera import CameraModel


class AbstractTwoSphereModel(abc.ABC):
    @abc.abstractmethod
    def __init__(
        self,
        camera: CameraModel,
        storage_cls: T.Type[ObservationStorage] = None,
        storage_kwargs: T.Dict = None,
    ):
        raise NotImplementedError

    @abc.abstractmethod
    def add_observation(self, observation: Observation):
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def n_observations(self) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    def set_sphere_center(self, new_sphere_center: np.ndarray):
        raise NotImplementedError

    @abc.abstractmethod
    def estimate_sphere_center(
        self,
        from_2d: T.Optional[np.ndarray] = None,
        prior_3d: T.Optional[np.ndarray] = None,
        prior_strength: float = 0.0,
    ) -> T.Tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError

    @abc.abstractmethod
    def estimate_sphere_center_2d(self) -> np.ndarray:
        raise NotImplementedError

    @abc.abstractmethod
    def estimate_sphere_center_3d(
        self,
        sphere_center_2d: np.ndarray,
        prior_3d: T.Optional[np.ndarray] = None,
        prior_strength=0.0,
    ) -> np.ndarray:
        raise NotImplementedError

    # GAZE PREDICTION
    @abc.abstractmethod
    def _extract_unproject_disambiguate(self, pupil_datum: T.Dict) -> Circle:
        raise NotImplementedError

    @abc.abstractmethod
    def _disambiguate_circle_3d_pair(
        self, circle_3d_pair: T.Tuple[Circle, Circle]
    ) -> Circle:
        raise NotImplementedError

    @abc.abstractmethod
    def predict_pupil_circle(
        self, observation: Observation, use_unprojection: bool = False
    ) -> Circle:
        raise NotImplementedError

    @abc.abstractmethod
    def apply_refraction_correction(self, pupil_circle: Circle) -> Circle:
        raise NotImplementedError

    @abc.abstractmethod
    def cleanup(self):
        raise NotImplementedError
