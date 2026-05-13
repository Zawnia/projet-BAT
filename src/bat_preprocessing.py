from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


EchoStrategy = Literal["drop_later", "best_snr"]


@dataclass(frozen=True)
class PreprocessingConfig:
    passage_gap_ms: float = 100.0
    echo_gap_ms: float = 10.0
    echo_fme_bins: float = 1.0
    fme_min_khz: float = 18.0
    min_passage_chirps: int = 1
    echo_strategy: EchoStrategy = "drop_later"


@dataclass(frozen=True)
class Chirp:
    time_ms: int
    posFME: int
    posFI: int
    posFT: int
    duree_bins: int
    SNR_dB: int
    FME_kHz: float
    FI_kHz: float
    FT_kHz: float
    gap_ms: float
    passage_id: int
    delta_FME_bins: float


@dataclass(frozen=True)
class Passage:
    """A dense acoustic time block, not necessarily one individual.

    A passage is the technical temporal segmentation unit; decomposing it into
    individuals belongs to the counting module.
    """

    passage_id: int
    chirps: tuple[Chirp, ...]
    start_time_ms: int
    end_time_ms: int
    n_chirps: int


@dataclass(frozen=True)
class BatPreprocessingResult:
    fme_khz: np.ndarray
    detections: dict[str, np.ndarray]
    stats: dict[str, int | float | str]
    passages: tuple[Passage, ...] = ()
    chirps_no_echo: tuple[Chirp, ...] = ()
    metadata: dict[str, float] | None = None


def preprocess_bat_file(
    path: str,
    fme_min_khz: float = 18.0,
    sequence_gap_ms: float = 100.0,
    echo_gap_ms: float = 10.0,
    echo_fme_bins: float = 1.0,
) -> BatPreprocessingResult:
    """Legacy-compatible preprocessing entrypoint for passage clustering."""
    return preprocess_passages(
        path,
        PreprocessingConfig(
            fme_min_khz=fme_min_khz,
            passage_gap_ms=sequence_gap_ms,
            echo_gap_ms=echo_gap_ms,
            echo_fme_bins=echo_fme_bins,
            echo_strategy="drop_later",
        ),
    )


def preprocess_passages(path: str, config: PreprocessingConfig | None = None) -> BatPreprocessingResult:
    config = config or PreprocessingConfig()
    records, metadata = load_bat_txt(path)
    data = add_frequency_columns(records, metadata["bin_khz"])
    clean = remove_zero_artefacts(data)
    sequenced = add_passage_columns(clean, config.passage_gap_ms, suffix="")
    no_echo, echo_mask = remove_echoes(
        sequenced,
        config.echo_gap_ms,
        config.echo_fme_bins,
        strategy=config.echo_strategy,
    )
    no_echo = add_passage_columns(no_echo, config.passage_gap_ms, suffix="2")
    cluster_mask = no_echo["FME_kHz"] > config.fme_min_khz
    cluster_data = filter_columns(no_echo, cluster_mask)
    passages = build_passages(cluster_data, min_chirps=config.min_passage_chirps)
    chirps_no_echo = tuple(chirp for passage in passages for chirp in passage.chirps)

    stats: dict[str, int | float | str] = {
        "n_raw": int(records["time_ms"].size),
        "n_artefacts": int(records["time_ms"].size - clean["time_ms"].size),
        "n_clean": int(clean["time_ms"].size),
        "n_echoes": int(echo_mask.sum()),
        "n_no_echo": int(no_echo["time_ms"].size),
        "n_filtered": int(cluster_data["time_ms"].size),
        "n_social": int(no_echo["time_ms"].size - cluster_data["time_ms"].size),
        "n_sequences": unique_count(sequenced.get("seq_id", np.array([], dtype=int))),
        "n_sequences_no_echo": unique_count(no_echo.get("seq_id2", np.array([], dtype=int))),
        "n_passages_detected": int(len(passages)),
        "fme_min_khz": float(config.fme_min_khz),
        "sequence_gap_ms": float(config.passage_gap_ms),
        "passage_gap_ms": float(config.passage_gap_ms),
        "echo_gap_ms": float(config.echo_gap_ms),
        "echo_fme_bins": float(config.echo_fme_bins),
        "echo_strategy": config.echo_strategy,
        "freq_khz_enreg": float(metadata["freq_khz_enreg"]),
        "lenfft": int(metadata["lenfft"]),
        "bin_khz": float(metadata["bin_khz"]),
    }
    return BatPreprocessingResult(
        fme_khz=cluster_data["FME_kHz"],
        detections=cluster_data,
        stats=stats,
        passages=passages,
        chirps_no_echo=chirps_no_echo,
        metadata=metadata,
    )


def load_bat_txt(path: str) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    with open(path, "r") as file:
        lines = file.readlines()

    freq_khz_enreg = float(next(line.split()[1] for line in lines if line.startswith("FREQ_KHZ_ENREG")))
    lenfft = float(next(line.split()[1] for line in lines if line.startswith("LENFFT")))
    start_idx = next(index for index, line in enumerate(lines) if line.strip() == "DATAASCII")
    rows = [
        [int(value) for value in line.split()]
        for line in lines[start_idx + 1 :]
        if len(line.split()) == 6 and all(value.isdigit() for value in line.split())
    ]
    values = np.asarray(rows, dtype=int)
    if values.size == 0:
        values = np.empty((0, 6), dtype=int)
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


def add_passage_columns(data: dict[str, np.ndarray], passage_gap_ms: float, suffix: str) -> dict[str, np.ndarray]:
    if data["time_ms"].size == 0:
        sorted_data = {key: value.copy() for key, value in data.items()}
        sorted_data[f"gap_ms{suffix}"] = np.array([], dtype=float)
        sorted_data[f"passage_id{suffix}"] = np.array([], dtype=int)
        sorted_data[f"seq_id{suffix}"] = np.array([], dtype=int)
        return sorted_data

    order = np.argsort(data["time_ms"], kind="stable")
    sorted_data = {key: value[order] for key, value in data.items()}
    gap_key = f"gap_ms{suffix}"
    passage_key = f"passage_id{suffix}"
    seq_key = f"seq_id{suffix}"
    gaps = np.empty(sorted_data["time_ms"].size, dtype=float)
    gaps[0] = np.nan
    gaps[1:] = np.diff(sorted_data["time_ms"])
    new_passage = np.isnan(gaps) | (gaps >= passage_gap_ms)
    passage_ids = np.cumsum(new_passage)
    sorted_data[gap_key] = gaps
    sorted_data[passage_key] = passage_ids
    sorted_data[seq_key] = passage_ids
    return sorted_data


def add_sequence_columns(data: dict[str, np.ndarray], sequence_gap_ms: float, suffix: str) -> dict[str, np.ndarray]:
    return add_passage_columns(data, sequence_gap_ms, suffix)


def remove_echoes(
    data: dict[str, np.ndarray],
    echo_gap_ms: float,
    echo_fme_bins: float,
    strategy: EchoStrategy = "drop_later",
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    if strategy == "drop_later":
        return remove_echoes_drop_later(data, echo_gap_ms, echo_fme_bins)
    if strategy == "best_snr":
        return remove_echoes_best_snr(data, echo_gap_ms, echo_fme_bins)
    raise ValueError("echo_strategy must be 'drop_later' or 'best_snr'")


def remove_echoes_drop_later(
    data: dict[str, np.ndarray],
    echo_gap_ms: float,
    echo_fme_bins: float,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    delta_fme = np.empty(data["posFME"].size, dtype=float)
    if data["posFME"].size:
        delta_fme[0] = np.nan
        delta_fme[1:] = np.abs(np.diff(data["posFME"]))
    echo_mask = (data["gap_ms"] <= echo_gap_ms) & (delta_fme <= echo_fme_bins)
    with_delta = data.copy()
    with_delta["delta_FME_bins"] = delta_fme
    return filter_columns(with_delta, ~echo_mask), echo_mask


def remove_echoes_best_snr(
    data: dict[str, np.ndarray],
    echo_gap_ms: float,
    echo_fme_bins: float,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    size = data["posFME"].size
    delta_fme = np.empty(size, dtype=float)
    if size:
        delta_fme[0] = np.nan
        delta_fme[1:] = np.abs(np.diff(data["posFME"]))

    keep = np.zeros(size, dtype=bool)
    echo_mask = np.zeros(size, dtype=bool)
    start = 0
    while start < size:
        end = start + 1
        while end < size and data["gap_ms"][end] <= echo_gap_ms and delta_fme[end] <= echo_fme_bins:
            end += 1
        group = np.arange(start, end)
        best = int(group[np.argmax(data["SNR_dB"][group])])
        keep[best] = True
        echo_mask[group[group != best]] = True
        start = end

    with_delta = data.copy()
    with_delta["delta_FME_bins"] = delta_fme
    return filter_columns(with_delta, keep), echo_mask


def build_passages(data: dict[str, np.ndarray], min_chirps: int = 1) -> tuple[Passage, ...]:
    if data["time_ms"].size == 0:
        return ()
    passage_key = "passage_id2" if "passage_id2" in data else "seq_id2"
    passages: list[Passage] = []
    for passage_id in np.unique(data[passage_key]):
        indices = np.flatnonzero(data[passage_key] == passage_id)
        if indices.size < min_chirps:
            continue
        chirps = tuple(chirp_from_columns(data, index, int(passage_id)) for index in indices)
        passages.append(
            Passage(
                passage_id=int(passage_id),
                chirps=chirps,
                start_time_ms=int(chirps[0].time_ms),
                end_time_ms=int(chirps[-1].time_ms),
                n_chirps=len(chirps),
            )
        )
    return tuple(passages)


def chirp_from_columns(data: dict[str, np.ndarray], index: int, passage_id: int) -> Chirp:
    return Chirp(
        time_ms=int(data["time_ms"][index]),
        posFME=int(data["posFME"][index]),
        posFI=int(data["posFI"][index]),
        posFT=int(data["posFT"][index]),
        duree_bins=int(data["duree_bins"][index]),
        SNR_dB=int(data["SNR_dB"][index]),
        FME_kHz=float(data["FME_kHz"][index]),
        FI_kHz=float(data["FI_kHz"][index]),
        FT_kHz=float(data["FT_kHz"][index]),
        gap_ms=float(data["gap_ms2"][index]),
        passage_id=passage_id,
        delta_FME_bins=float(data["delta_FME_bins"][index]),
    )


def filter_columns(data: dict[str, np.ndarray], mask: np.ndarray) -> dict[str, np.ndarray]:
    return {key: value[mask] for key, value in data.items()}


def unique_count(values: np.ndarray) -> int:
    return int(np.unique(values).size) if values.size else 0
