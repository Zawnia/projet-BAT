from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BatPreprocessingResult:
    fme_khz: np.ndarray
    detections: dict[str, np.ndarray]
    stats: dict[str, int | float]


def preprocess_bat_file(
    path: str,
    fme_min_khz: float = 18.0,
    sequence_gap_ms: float = 100.0,
    echo_gap_ms: float = 10.0,
    echo_fme_bins: float = 1.0,
) -> BatPreprocessingResult:
    records, metadata = load_bat_txt(path)
    data = add_frequency_columns(records, metadata["bin_khz"])
    clean = remove_zero_artefacts(data)
    sequenced = add_sequence_columns(clean, sequence_gap_ms, suffix="")
    no_echo, echo_mask = remove_echoes(sequenced, echo_gap_ms, echo_fme_bins)
    no_echo = add_sequence_columns(no_echo, sequence_gap_ms, suffix="2")
    cluster_mask = no_echo["FME_kHz"] > fme_min_khz
    cluster_data = filter_columns(no_echo, cluster_mask)

    stats = {
        "n_raw": int(records["time_ms"].size),
        "n_artefacts": int(records["time_ms"].size - clean["time_ms"].size),
        "n_clean": int(clean["time_ms"].size),
        "n_echoes": int(echo_mask.sum()),
        "n_no_echo": int(no_echo["time_ms"].size),
        "n_filtered": int(cluster_data["time_ms"].size),
        "n_social": int(no_echo["time_ms"].size - cluster_data["time_ms"].size),
        "n_sequences": int(np.unique(sequenced["seq_id"]).size),
        "n_sequences_no_echo": int(np.unique(no_echo["seq_id2"]).size),
        "fme_min_khz": float(fme_min_khz),
        "sequence_gap_ms": float(sequence_gap_ms),
        "echo_gap_ms": float(echo_gap_ms),
        "echo_fme_bins": float(echo_fme_bins),
        "freq_khz_enreg": float(metadata["freq_khz_enreg"]),
        "lenfft": int(metadata["lenfft"]),
        "bin_khz": float(metadata["bin_khz"]),
    }
    return BatPreprocessingResult(fme_khz=cluster_data["FME_kHz"], detections=cluster_data, stats=stats)


def load_bat_txt(path: str) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    with open(path, "r") as file:
        lines = file.readlines()

    freq_khz_enreg = float(next(line.split()[1] for line in lines if line.startswith("FREQ_KHZ_ENREG")))
    lenfft = float(next(line.split()[1] for line in lines if line.startswith("LENFFT")))
    start_idx = next(index for index, line in enumerate(lines) if line.strip() == "DATAASCII")
    values = np.array([
        [int(value) for value in line.split()]
        for line in lines[start_idx + 3:]
        if len(line.split()) == 6
    ])
    records = {
        "time_ms": values[:, 0],
        "posFME": values[:, 1],
        "posFI": values[:, 2],
        "posFT": values[:, 3],
        "duree_bins": values[:, 4],
        "SNR_dB": values[:, 5],
    }
    metadata = {
        "freq_khz_enreg": float(freq_khz_enreg),
        "lenfft": float(lenfft),
        "bin_khz": float(freq_khz_enreg / lenfft),
    }
    return records, metadata


def add_frequency_columns(records: dict[str, np.ndarray], bin_khz: float) -> dict[str, np.ndarray]:
    data = records.copy()
    data["FME_kHz"] = data["posFME"] * bin_khz
    data["FI_kHz"] = data["posFI"] * bin_khz
    data["FT_kHz"] = data["posFT"] * bin_khz
    return data


def remove_zero_artefacts(data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    mask = ~((data["posFME"] == 0) & (data["SNR_dB"] == 0) & (data["duree_bins"] == 0))
    return filter_columns(data, mask)


def add_sequence_columns(data: dict[str, np.ndarray], sequence_gap_ms: float, suffix: str) -> dict[str, np.ndarray]:
    order = np.argsort(data["time_ms"])
    sorted_data = {key: value[order] for key, value in data.items()}
    gap_key = f"gap_ms{suffix}"
    seq_key = f"seq_id{suffix}"
    gaps = np.empty(sorted_data["time_ms"].size, dtype=float)
    gaps[0] = np.nan
    gaps[1:] = np.diff(sorted_data["time_ms"])
    new_sequence = np.isnan(gaps) | (gaps >= sequence_gap_ms)
    sorted_data[gap_key] = gaps
    sorted_data[seq_key] = np.cumsum(new_sequence)
    return sorted_data


def remove_echoes(
    data: dict[str, np.ndarray],
    echo_gap_ms: float,
    echo_fme_bins: float,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    delta_fme = np.empty(data["posFME"].size, dtype=float)
    delta_fme[0] = np.nan
    delta_fme[1:] = np.abs(np.diff(data["posFME"]))
    echo_mask = (data["gap_ms"] <= echo_gap_ms) & (delta_fme <= echo_fme_bins)
    with_delta = data.copy()
    with_delta["delta_FME_bins"] = delta_fme
    return filter_columns(with_delta, ~echo_mask), echo_mask


def filter_columns(data: dict[str, np.ndarray], mask: np.ndarray) -> dict[str, np.ndarray]:
    return {key: value[mask] for key, value in data.items()}
