import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.bat_preprocessing import PreprocessingConfig, preprocess_bat_file, preprocess_passages


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


class BatPreprocessingTests(unittest.TestCase):
    def test_parses_filters_sorts_and_segments_passages(self) -> None:
        path = write_sensor_file([
            (220, 100, 103, 97, 6, 25),
            (0, 0, 0, 0, 0, 0),
            (0, 97, 100, 94, 6, 26),
            (80, 98, 101, 95, 6, 26),
        ])
        try:
            result = preprocess_passages(path, PreprocessingConfig(passage_gap_ms=100, echo_strategy="drop_later"))
        finally:
            Path(path).unlink()

        self.assertEqual(result.stats["n_raw"], 4)
        self.assertEqual(result.stats["n_artefacts"], 1)
        self.assertEqual(result.detections["time_ms"].tolist(), [0, 80, 220])
        self.assertEqual(result.stats["n_passages_detected"], 2)
        self.assertEqual([passage.n_chirps for passage in result.passages], [2, 1])

    def test_drop_later_echo_strategy_preserves_first_chirp(self) -> None:
        path = write_sensor_file([
            (0, 97, 100, 94, 6, 20),
            (5, 98, 101, 95, 6, 30),
            (100, 97, 100, 94, 6, 25),
        ])
        try:
            result = preprocess_passages(path, PreprocessingConfig(echo_strategy="drop_later"))
        finally:
            Path(path).unlink()

        self.assertEqual(result.stats["n_echoes"], 1)
        self.assertEqual(result.detections["time_ms"].tolist(), [0, 100])
        self.assertEqual(result.detections["SNR_dB"].tolist(), [20, 25])

    def test_best_snr_echo_strategy_keeps_best_snr_chirp(self) -> None:
        path = write_sensor_file([
            (0, 97, 100, 94, 6, 20),
            (5, 98, 101, 95, 6, 30),
            (100, 97, 100, 94, 6, 25),
        ])
        try:
            result = preprocess_passages(path, PreprocessingConfig(echo_strategy="best_snr"))
        finally:
            Path(path).unlink()

        self.assertEqual(result.stats["n_echoes"], 1)
        self.assertEqual(result.detections["time_ms"].tolist(), [5, 100])
        self.assertEqual(result.detections["SNR_dB"].tolist(), [30, 25])

    def test_legacy_entrypoint_matches_passage_preprocessing_drop_later(self) -> None:
        path = write_sensor_file([
            (0, 97, 100, 94, 6, 26),
            (5, 98, 101, 95, 6, 26),
            (130, 136, 140, 132, 5, 24),
        ])
        try:
            legacy = preprocess_bat_file(path)
            refactored = preprocess_passages(path, PreprocessingConfig(echo_strategy="drop_later"))
        finally:
            Path(path).unlink()

        self.assertTrue(np.array_equal(legacy.detections["time_ms"], refactored.detections["time_ms"]))
        self.assertTrue(np.allclose(legacy.fme_khz, refactored.fme_khz, rtol=0, atol=1e-12))
        for key, value in legacy.stats.items():
            other = refactored.stats[key]
            if isinstance(value, float):
                self.assertTrue(math.isclose(value, other, rel_tol=0, abs_tol=1e-12))
            else:
                self.assertEqual(value, other)


if __name__ == "__main__":
    unittest.main()
