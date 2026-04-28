import unittest

import numpy as np

from src.species_clustering import SpeciesGMM, label_cluster


class SpeciesGMMTests(unittest.TestCase):
    def test_kde_peaks_drive_component_count_on_skewed_modes(self) -> None:
        rng = np.random.default_rng(7)
        low_mode = 30 + rng.gamma(shape=2.0, scale=2.0, size=350)
        high_mode = 50 + rng.gamma(shape=2.0, scale=1.8, size=300)
        fme = np.concatenate([low_mode, high_mode])

        model = SpeciesGMM(
            bandwidth_method="scott",
            bandwidth_scale=1.15,
            peak_prominence_ratio=0.08,
            min_peak_distance_khz=5.0,
            random_state=7,
        ).fit(fme)

        self.assertEqual(model.params["K"], 2)
        self.assertEqual(model.params["kde_peaks"].size, 2)

    def test_no_detected_peak_falls_back_to_density_maximum(self) -> None:
        rng = np.random.default_rng(11)
        fme = rng.normal(loc=42.0, scale=1.5, size=200)

        model = SpeciesGMM(peak_prominence_ratio=2.0, random_state=11).fit(fme)

        self.assertEqual(model.params["K"], 1)
        self.assertEqual(model.params["kde_peaks"].size, 1)

    def test_max_components_caps_detected_peaks(self) -> None:
        rng = np.random.default_rng(13)
        fme = np.concatenate([
            rng.normal(loc=25.0, scale=0.8, size=150),
            rng.normal(loc=40.0, scale=0.8, size=150),
            rng.normal(loc=55.0, scale=0.8, size=150),
        ])

        model = SpeciesGMM(max_components=2, min_peak_distance_khz=3.0, random_state=13).fit(fme)

        self.assertEqual(model.params["K"], 2)
        self.assertEqual(model.params["kde_peaks"].size, 2)

    def test_label_cluster_uses_fme_reference_ranges(self) -> None:
        self.assertEqual(label_cluster(38.7), "Pipistrellus kuhlii")
        self.assertEqual(label_cluster(45.0), "Pipistrellus pipistrellus")
        self.assertEqual(label_cluster(55.0), "Pipistrellus pygmaeus")
        self.assertEqual(label_cluster(27.0), "Eptesicus serotinus")
        self.assertEqual(label_cluster(20.0), "Nyctalus sp.")
        self.assertEqual(label_cluster(13.0), "Tadarida teniotis")
        self.assertEqual(label_cluster(33.0), "Indetermine")


if __name__ == "__main__":
    unittest.main()
