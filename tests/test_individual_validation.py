import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.bat_preprocessing import Chirp, PreprocessingConfig, preprocess_passages
from src.individual_counting import IndividualTrack
from src.individual_validation import (
    ScenarioWindow,
    TrackAssignment,
    assign_tracks_to_scenarios,
    bootstrap_ci,
    compute_scenario_metrics,
    generate_validation_dataset,
    scenarios_from_truth,
    write_generation_outputs,
)


def make_chirp(time_ms: int) -> Chirp:
    return Chirp(
        time_ms=time_ms,
        posFME=97,
        posFI=100,
        posFT=94,
        duree_bins=6,
        SNR_dB=28,
        FME_kHz=37.89,
        FI_kHz=39.06,
        FT_kHz=36.72,
        gap_ms=100.0,
        passage_id=1,
        delta_FME_bins=0.0,
    )


def make_track(track_id: str, times: list[int]) -> IndividualTrack:
    chirps = tuple(make_chirp(time_ms) for time_ms in times)
    return IndividualTrack(
        track_id=track_id,
        passage_id=1,
        packet_id="1:0",
        passage_species="Pipistrellus kuhlii",
        chirps=chirps,
        start_time_ms=times[0],
        end_time_ms=times[-1],
        n_chirps=len(chirps),
        fme_median_khz=37.89,
        ici_median_ms=100.0,
        suspicious_short_ici=False,
    )


class IndividualValidationTests(unittest.TestCase):
    def test_generated_sensor_txt_is_readable_by_preprocessing(self) -> None:
        result = generate_validation_dataset("dev", n_replicates=1, seed=123, sweep_replicates=1)
        with tempfile.TemporaryDirectory() as directory:
            txt_path, truth_path = write_generation_outputs(result, directory)
            preprocessing = preprocess_passages(
                str(txt_path),
                PreprocessingConfig(echo_strategy="best_snr", fme_min_khz=18.0, min_passage_chirps=1),
            )

            self.assertGreater(preprocessing.stats["n_raw"], 0)
            self.assertTrue(txt_path.read_text(encoding="utf-8").startswith("DETECTDATA"))
            self.assertTrue(truth_path.exists())
            self.assertGreaterEqual(preprocessing.stats["n_raw"], sum(row.n_chirps for row in result.truth))

    def test_generation_includes_sweeps_and_truth_scenarios(self) -> None:
        result = generate_validation_dataset("test", n_replicates=1, seed=456, sweep_replicates=1)
        case_types = {scenario.case_type for scenario in result.scenarios}
        scenarios = scenarios_from_truth(result.truth)

        self.assertIn("ici_sweep", case_types)
        self.assertIn("fme_sweep", case_types)
        self.assertTrue(any(scenario.parameter_name == "ici_delta_ms" for scenario in scenarios))
        self.assertTrue(any(scenario.parameter_name == "fme_delta_bins" for scenario in scenarios))
        self.assertEqual(len(scenarios), len(result.scenarios))

    def test_assign_tracks_marks_ambiguous_and_false_positive(self) -> None:
        scenarios = (
            ScenarioWindow("dev", "s1", "case_a", 1, 0, 250, 1, "", np.nan),
            ScenarioWindow("dev", "s2", "case_b", 1, 200, 500, 1, "", np.nan),
        )
        tracks = (
            make_track("track-1", [10, 100, 220, 240]),
            make_track("track-2", [900, 1000, 1100]),
        )

        assignments = assign_tracks_to_scenarios(tracks, scenarios)

        self.assertEqual(assignments[0].scenario_id, "s1")
        self.assertEqual(assignments[0].assignment_status, "ambiguous_majority")
        self.assertEqual(assignments[1].scenario_id, "UNASSIGNED")
        self.assertEqual(assignments[1].assignment_status, "unassigned_false_positive")

    def test_compute_metrics_on_manual_scenarios(self) -> None:
        scenarios = (
            ScenarioWindow("dev", "s1", "case_a", 1, 0, 100, 1, "", np.nan),
            ScenarioWindow("dev", "s2", "case_a", 2, 200, 300, 2, "", np.nan),
            ScenarioWindow("dev", "s3", "case_b", 1, 400, 500, 1, "", np.nan),
        )
        assignments = (
            TrackAssignment("t1", "s1", "case_a", 4, 4, "assigned", 0, 80, "sp"),
            TrackAssignment("t2", "s2", "case_a", 4, 4, "assigned", 200, 280, "sp"),
            TrackAssignment("t3", "s2", "case_a", 4, 4, "assigned", 210, 290, "sp"),
            TrackAssignment("t4", "s2", "case_a", 4, 4, "assigned", 220, 295, "sp"),
            TrackAssignment("t5", "UNASSIGNED", "false_positive", 4, 0, "unassigned_false_positive", 900, 990, "sp"),
        )

        metrics = compute_scenario_metrics(scenarios, assignments)

        self.assertEqual([metric.detected_count for metric in metrics], [1, 3, 0])
        self.assertEqual([metric.signed_error for metric in metrics], [0, 1, -1])
        self.assertEqual([metric.absolute_error for metric in metrics], [0, 1, 1])
        self.assertEqual([metric.exact_match for metric in metrics], [True, False, False])

    def test_bootstrap_is_deterministic(self) -> None:
        values = np.array([0.0, 1.0, 2.0, 3.0])
        first = bootstrap_ci(values, np.mean, seed=42, samples=200)
        second = bootstrap_ci(values, np.mean, seed=42, samples=200)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
