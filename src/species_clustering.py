from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy import optimize, signal, stats
from sklearn.mixture import GaussianMixture


FME_SPECIES_RULES: tuple[tuple[float, float, str], ...] = (
    (36.0, 39.0, "Pipistrellus kuhlii"),
    (42.0, 50.0, "Pipistrellus pipistrellus"),
    (52.0, 58.0, "Pipistrellus pygmaeus"),
    (24.0, 30.0, "Eptesicus serotinus"),
    (18.0, 24.0, "Nyctalus sp."),
    (10.0, 16.0, "Tadarida teniotis"),
)


def label_cluster(fme_median_khz: float) -> str:
    """Return the most likely species from a simple Marseille FME reference table."""
    for lower, upper, species in FME_SPECIES_RULES:
        if lower <= fme_median_khz <= upper:
            return species
    return "Indetermine"


def label_passage_species(fme_median_khz: float) -> str:
    """Return the dominant likely species for an acoustic passage."""
    return label_cluster(fme_median_khz)


class SpeciesGMM:
    def __init__(
        self,
        bandwidth_method: str | float = "scott",
        bandwidth_scale: float = 1.0,
        peak_prominence_ratio: float = 0.05,
        min_peak_distance_khz: float | None = None,
        max_components: int = 8,
        grid_size: int = 1000,
        n_init: int = 10,
        random_state: int = 42,
    ) -> None:
        if max_components < 1:
            raise ValueError("max_components must be at least 1")
        if grid_size < 3:
            raise ValueError("grid_size must be at least 3")
        self.bandwidth_method = bandwidth_method
        self.bandwidth_scale = bandwidth_scale
        self.peak_prominence_ratio = peak_prominence_ratio
        self.min_peak_distance_khz = min_peak_distance_khz
        self.max_components = max_components
        self.grid_size = grid_size
        self.n_init = n_init
        self.random_state = random_state
        self.model: GaussianMixture | None = None
        self.kde_grid_: np.ndarray | None = None
        self.kde_density_: np.ndarray | None = None
        self.kde_peaks_: np.ndarray | None = None
        self.order_: np.ndarray | None = None
        self.inverse_order_: np.ndarray | None = None

    def fit(self, fme_khz: np.ndarray) -> "SpeciesGMM":
        x_1d = np.asarray(fme_khz, dtype=float)
        x_1d = x_1d[np.isfinite(x_1d)]
        if x_1d.size < 2:
            raise ValueError("At least two finite FME values are required for clustering")

        x = x_1d.reshape(-1, 1)
        if np.allclose(x_1d.min(), x_1d.max()):
            self.kde_grid_ = np.array([x_1d[0]])
            self.kde_density_ = np.array([1.0])
            self.kde_peaks_ = np.array([x_1d[0]])
            self.model = GaussianMixture(
                n_components=1,
                n_init=self.n_init,
                random_state=self.random_state,
            ).fit(x)
            self.order_ = np.array([0])
            self.inverse_order_ = np.array([0])
            return self

        kde = stats.gaussian_kde(x_1d, bw_method=self._scaled_bandwidth_method())
        pad = max(0.5, (x_1d.max() - x_1d.min()) * 0.02)
        self.kde_grid_ = np.linspace(x_1d.min() - pad, x_1d.max() + pad, self.grid_size)
        self.kde_density_ = kde(self.kde_grid_)
        grid_step = self.kde_grid_[1] - self.kde_grid_[0]
        min_peak_distance = self.min_peak_distance_khz if self.min_peak_distance_khz is not None else kde.factor * x_1d.std(ddof=1)
        min_peak_distance_bins = max(1, int(round(min_peak_distance / grid_step)))
        peak_indices, _ = signal.find_peaks(
            self.kde_density_,
            prominence=self.kde_density_.max() * self.peak_prominence_ratio,
            distance=min_peak_distance_bins,
        )
        self.kde_peaks_ = self.kde_grid_[peak_indices]
        if self.kde_peaks_.size == 0:
            self.kde_peaks_ = np.array([self.kde_grid_[np.argmax(self.kde_density_)]])

        if self.kde_peaks_.size > self.max_components:
            peak_heights = self.kde_density_[peak_indices]
            keep = np.argsort(peak_heights)[-self.max_components :]
            self.kde_peaks_ = np.sort(self.kde_peaks_[keep])

        self.model = GaussianMixture(
            n_components=int(max(1, self.kde_peaks_.size)),
            n_init=self.n_init,
            random_state=self.random_state,
            means_init=np.sort(self.kde_peaks_).reshape(-1, 1),
        ).fit(x)
        self.order_ = np.argsort(self.model.means_.ravel())
        self.inverse_order_ = np.empty_like(self.order_)
        self.inverse_order_[self.order_] = np.arange(self.order_.size)
        return self

    def predict(self, fme_khz: np.ndarray) -> np.ndarray:
        labels = self._model.predict(np.asarray(fme_khz).reshape(-1, 1))
        return self._inverse_order[labels]

    def predict_proba(self, fme_khz: np.ndarray) -> np.ndarray:
        proba = self._model.predict_proba(np.asarray(fme_khz).reshape(-1, 1))
        return proba[:, self._order]

    @property
    def thresholds(self) -> np.ndarray:
        means = self.params["means"]
        return np.array([
            optimize.minimize_scalar(
                lambda value: self._mixture_density(np.array([value]))[0],
                bounds=(left, right),
                method="bounded",
            ).x
            for left, right in zip(means[:-1], means[1:])
        ])

    @property
    def params(self) -> dict[str, int | str | np.ndarray]:
        model = self._model
        order = self._order
        return {
            "K": int(model.n_components),
            "K_detection_method": "kde_find_peaks",
            "means": model.means_.ravel()[order],
            "sigmas": np.sqrt(model.covariances_.reshape(model.n_components, -1)[:, 0])[order],
            "weights": model.weights_[order],
            "kde_grid": self._kde_grid,
            "kde_density": self._kde_density,
            "kde_peaks": np.sort(self._kde_peaks),
        }

    @property
    def _model(self) -> GaussianMixture:
        assert self.model is not None
        return self.model

    @property
    def _order(self) -> np.ndarray:
        assert self.order_ is not None
        return self.order_

    @property
    def _inverse_order(self) -> np.ndarray:
        assert self.inverse_order_ is not None
        return self.inverse_order_

    @property
    def _kde_grid(self) -> np.ndarray:
        assert self.kde_grid_ is not None
        return self.kde_grid_

    @property
    def _kde_density(self) -> np.ndarray:
        assert self.kde_density_ is not None
        return self.kde_density_

    @property
    def _kde_peaks(self) -> np.ndarray:
        assert self.kde_peaks_ is not None
        return self.kde_peaks_

    def _mixture_density(self, x: np.ndarray) -> np.ndarray:
        params = self.params
        z = (x[:, None] - params["means"][None, :]) / params["sigmas"][None, :]
        densities = np.exp(-0.5 * z**2) / (params["sigmas"][None, :] * np.sqrt(2 * np.pi))
        return densities @ params["weights"]

    def _scaled_bandwidth_method(self) -> str | float | Callable[[stats.gaussian_kde], float]:
        if self.bandwidth_scale <= 0:
            raise ValueError("bandwidth_scale must be positive")
        if isinstance(self.bandwidth_method, str):
            method = self.bandwidth_method
            if method not in {"scott", "silverman"}:
                raise ValueError("bandwidth_method must be 'scott', 'silverman' or a positive float")

            def scaled(kde: stats.gaussian_kde) -> float:
                base = kde.scotts_factor() if method == "scott" else kde.silverman_factor()
                return base * self.bandwidth_scale

            return scaled
        return float(self.bandwidth_method) * self.bandwidth_scale


def plot_gmm_fit(model: SpeciesGMM, fme_khz: np.ndarray, ax: plt.Axes | None = None) -> plt.Axes:
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots()

    x = np.asarray(fme_khz)
    params = model.params
    grid = np.linspace(x.min(), x.max(), 1000)
    z = (grid[:, None] - params["means"][None, :]) / params["sigmas"][None, :]
    components = params["weights"][None, :] * np.exp(-0.5 * z**2) / (params["sigmas"][None, :] * np.sqrt(2 * np.pi))
    peak_y = np.interp(params["kde_peaks"], params["kde_grid"], params["kde_density"])

    ax.hist(x, bins=80, density=True, alpha=0.35, color="0.45")
    ax.plot(params["kde_grid"], params["kde_density"], color="0.35", linestyle="--", linewidth=1.5)
    ax.scatter(params["kde_peaks"], peak_y, color="0.1", marker="x", zorder=3)
    ax.plot(grid, components, linewidth=1.5)
    ax.plot(grid, components.sum(axis=1), color="black", linewidth=2)
    for threshold in model.thresholds:
        ax.axvline(threshold, color="red", linestyle="--", linewidth=1)
    ax.set_xlabel("FME (kHz)")
    ax.set_ylabel("Density")
    return ax
