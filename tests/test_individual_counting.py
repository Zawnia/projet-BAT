import tempfile
import unittest
from pathlib import Path

from src.bat_preprocessing import PreprocessingConfig, preprocess_passages
from src.individual_counting import SpeciesSplitConfig, TrackingConfig, count_individuals


def write_sensor_file(rows: list[tuple[int, int, int, int, int, int]]) -> str:
    text = "\r\n".join(
        [
            "DETECTDATA",
            "FREQ_KHZ_ENREG 200",
            "LENFFT 512",
            "OVERLAP 2",
            "SNRMIN 19",
            f"detectData_nbsig {len(rows)}",
            f"nbsig_detect {len(rows)}",
            "temps_ms_fin_prec 0",
            "RAW-ASCII 1",
            "time_ms posFME posFI posFT posDUREE SNRdB",
            "raw: uint32 uint8 uint8 uint8 uint8 uint8",
            "",
            "DATAASCII",
            *[" ".join(map(str, row)) for row in rows],
        ]
    )
    handle = tempfile.NamedTemporaryFile("w", suffix=".TXT", delete=False)
    handle.write(text)
    handle.close()
    return handle.name


def preprocess_rows(rows: list[tuple[int, int, int, int, int, int]]):
    path = write_sensor_file(rows)
    try:
        return preprocess_passages(
            path,
            PreprocessingConfig(
                passage_gap_ms=250,
                fme_min_khz=18,
                min_passage_chirps=1,
                echo_strategy="best_snr",
            ),
        )
    finally:
        Path(path).unlink()


class IndividualCountingTests(unittest.TestCase):
    def test_unimodal_regular_passage_counts_one_track(self) -> None:
        rows = [(index * 100, 97, 100, 94, 6, 28) for index in range(12)]
        preprocessing = preprocess_rows(rows)

        result = count_individuals(
            preprocessing.passages,
            SpeciesSplitConfig(min_chirps_for_kde=15),
            TrackingConfig(min_track_chirps=3),
        )

        self.assertEqual(result.summary["n_individuals_estimated"], 1)
        self.assertEqual(result.tracks[0].n_chirps, 12)
        self.assertFalse(result.tracks[0].suspicious_short_ici)

    def test_two_species_in_one_passage_are_split_before_tracking(self) -> None:
        rows = []
        for index in range(18):
            rows.append((index * 100, 97, 100, 94, 6, 28))
            rows.append((index * 100 + 45, 136, 140, 132, 6, 28))
        preprocessing = preprocess_rows(rows)

        result = count_individuals(
            preprocessing.passages,
            SpeciesSplitConfig(
                min_chirps_for_kde=15,
                bandwidth_scale=0.55,
                min_peak_distance_khz=5.0,
                peak_prominence_ratio=0.01,
            ),
            TrackingConfig(min_track_chirps=3),
        )

        self.assertEqual(result.summary["n_individuals_estimated"], 2)
        self.assertEqual({track.passage_species for track in result.tracks}, {"Pipistrellus kuhlii", "Pipistrellus pygmaeus"})

    def test_short_track_is_not_counted(self) -> None:
        rows = [
            (0, 97, 100, 94, 6, 28),
            (100, 97, 100, 94, 6, 28),
            (200, 97, 100, 94, 6, 28),
            (50, 99, 102, 96, 6, 28),
            (180, 99, 102, 96, 6, 28),
        ]
        preprocessing = preprocess_rows(rows)

        result = count_individuals(preprocessing.passages, tracking_config=TrackingConfig(min_track_chirps=3))

        self.assertEqual(result.summary["n_individuals_estimated"], 1)
        self.assertEqual(result.tracks[0].n_chirps, 3)

    def test_short_ici_track_is_flagged_suspicious(self) -> None:
        rows = [(index * 35, 97, 100, 94, 6, 28) for index in range(8)]
        preprocessing = preprocess_rows(rows)

        result = count_individuals(
            preprocessing.passages,
            SpeciesSplitConfig(min_chirps_for_kde=15),
            TrackingConfig(bootstrap_ici_ms=35, min_track_chirps=3, suspicious_short_ici_ms=45),
        )

        self.assertEqual(result.summary["n_individuals_estimated"], 1)
        self.assertTrue(result.tracks[0].suspicious_short_ici)

    def test_end_to_end_two_same_species_individuals_with_distinct_cadences(self) -> None:
        rows = []
        time_a = 0
        for index in range(30):
            jitter = [-10, 0, 10, 5, -5][index % 5]
            rows.append((time_a, 97, 100, 94, 6, 29))
            time_a += 100 + jitter
        time_b = 0
        for index in range(25):
            jitter = [-13, 0, 13, 7, -7][index % 5]
            rows.append((time_b, 99, 102, 96, 6, 27))
            time_b += 130 + jitter
        preprocessing = preprocess_rows(rows)

        result = count_individuals(
            preprocessing.passages,
            SpeciesSplitConfig(min_chirps_for_kde=15),
            TrackingConfig(ici_tolerance_ratio=0.35, fme_tolerance_bins=2, min_track_chirps=3),
        )

        self.assertEqual(result.summary["n_individuals_estimated"], 2)
        self.assertEqual(sorted(track.n_chirps for track in result.tracks), [25, 30])


if __name__ == "__main__":
    unittest.main()
