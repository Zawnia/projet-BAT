from __future__ import annotations

from dataclasses import dataclass
from itertools import count

import numpy as np

try:
    from .bat_preprocessing import Chirp, Passage
    from .species_clustering import SpeciesGMM, label_passage_species
except ImportError:
    from bat_preprocessing import Chirp, Passage
    from species_clustering import SpeciesGMM, label_passage_species


@dataclass(frozen=True)
class SpeciesSplitConfig:
    min_chirps_for_kde: int = 15
    max_components: int = 4
    bandwidth_method: str = "scott"
    bandwidth_scale: float = 1.35
    peak_prominence_ratio: float = 0.12
    min_peak_distance_khz: float | None = 4.0
    random_state: int = 42


@dataclass(frozen=True)
class TrackingConfig:
    ici_tolerance_ratio: float = 0.30
    fme_tolerance_bins: float = 2.0
    track_expiry_n_ici: float = 3.0
    min_track_chirps: int = 3
    bootstrap_ici_ms: float = 100.0
    suspicious_short_ici_ms: float = 45.0


@dataclass(frozen=True)
class SpeciesPacket:
    passage_id: int
    packet_id: str
    passage_species: str
    chirps: tuple[Chirp, ...]


@dataclass(frozen=True)
class IndividualTrack:
    track_id: str
    passage_id: int
    packet_id: str
    passage_species: str
    chirps: tuple[Chirp, ...]
    start_time_ms: int
    end_time_ms: int
    n_chirps: int
    fme_median_khz: float
    ici_median_ms: float
    suspicious_short_ici: bool


@dataclass(frozen=True)
class CountingResult:
    tracks: tuple[IndividualTrack, ...]
    packets: tuple[SpeciesPacket, ...]
    summary: dict[str, int | dict[str, int] | list[int]]


@dataclass
class _OpenTrack:
    track_id: str
    chirps: list[Chirp]

    @property
    def last_chirp(self) -> Chirp:
        return self.chirps[-1]

    def predicted_ici_ms(self, config: TrackingConfig) -> float:
        if len(self.chirps) < 2:
            return config.bootstrap_ici_ms
        return float(np.median(np.diff([chirp.time_ms for chirp in self.chirps])))

    def fme_center_bins(self) -> float:
        return float(np.median([chirp.posFME for chirp in self.chirps]))


def count_individuals(
    passages: tuple[Passage, ...] | list[Passage],
    split_config: SpeciesSplitConfig | None = None,
    tracking_config: TrackingConfig | None = None,
) -> CountingResult:
    split_config = split_config or SpeciesSplitConfig()
    tracking_config = tracking_config or TrackingConfig()
    packets: list[SpeciesPacket] = []
    tracks: list[IndividualTrack] = []
    track_ids = count(1)

    for passage in passages:
        passage_packets = split_passage_species(passage, split_config)
        packets.extend(passage_packets)
        for packet in passage_packets:
            tracks.extend(track_packet(packet, tracking_config, track_ids))

    counted_tracks = tuple(track for track in tracks if track.n_chirps >= tracking_config.min_track_chirps)
    by_species: dict[str, int] = {}
    for track in counted_tracks:
        by_species[track.passage_species] = by_species.get(track.passage_species, 0) + 1

    return CountingResult(
        tracks=counted_tracks,
        packets=tuple(packets),
        summary={
            "n_passages_detected": len(passages),
            "n_individuals_estimated": len(counted_tracks),
            "n_suspicious_short_ici_tracks": sum(track.suspicious_short_ici for track in counted_tracks),
            "individuals_by_species": by_species,
            "n_chirps_in_track": [track.n_chirps for track in counted_tracks],
        },
    )


def split_passage_species(passage: Passage, config: SpeciesSplitConfig | None = None) -> tuple[SpeciesPacket, ...]:
    config = config or SpeciesSplitConfig()
    chirps = tuple(sorted(passage.chirps, key=lambda chirp: chirp.time_ms))
    if len(chirps) == 0:
        return ()

    if len(chirps) < config.min_chirps_for_kde:
        return (make_species_packet(passage.passage_id, "0", chirps),)

    fme = np.array([chirp.FME_kHz for chirp in chirps], dtype=float)
    if np.allclose(fme.min(), fme.max()):
        return (make_species_packet(passage.passage_id, "0", chirps),)

    try:
        model = SpeciesGMM(
            bandwidth_method=config.bandwidth_method,
            bandwidth_scale=config.bandwidth_scale,
            peak_prominence_ratio=config.peak_prominence_ratio,
            min_peak_distance_khz=config.min_peak_distance_khz,
            max_components=config.max_components,
            random_state=config.random_state,
        ).fit(fme)
    except ValueError:
        return (make_species_packet(passage.passage_id, "0", chirps),)

    labels = model.predict(fme)
    packets = []
    for label in range(int(model.params["K"])):
        group = tuple(chirp for chirp, chirp_label in zip(chirps, labels) if chirp_label == label)
        if group:
            packets.append(make_species_packet(passage.passage_id, str(label), group))
    return tuple(packets) if packets else (make_species_packet(passage.passage_id, "0", chirps),)


def make_species_packet(passage_id: int, packet_id: str, chirps: tuple[Chirp, ...]) -> SpeciesPacket:
    fme_median = float(np.median([chirp.FME_kHz for chirp in chirps]))
    return SpeciesPacket(
        passage_id=passage_id,
        packet_id=f"{passage_id}:{packet_id}",
        passage_species=label_passage_species(fme_median),
        chirps=chirps,
    )


def track_packet(
    packet: SpeciesPacket,
    config: TrackingConfig,
    track_ids: count | None = None,
) -> tuple[IndividualTrack, ...]:
    track_ids = track_ids or count(1)
    open_tracks: list[_OpenTrack] = []
    closed_tracks: list[_OpenTrack] = []

    for chirp in sorted(packet.chirps, key=lambda item: item.time_ms):
        still_open: list[_OpenTrack] = []
        for track in open_tracks:
            elapsed = chirp.time_ms - track.last_chirp.time_ms
            if elapsed <= config.track_expiry_n_ici * track.predicted_ici_ms(config):
                still_open.append(track)
            else:
                closed_tracks.append(track)
        open_tracks = still_open

        candidates = [
            (compatibility_score(chirp, track, config), track)
            for track in open_tracks
            if is_compatible(chirp, track, config)
        ]
        if candidates:
            _, best_track = min(candidates, key=lambda item: item[0])
            best_track.chirps.append(chirp)
        else:
            open_tracks.append(_OpenTrack(track_id=f"track-{next(track_ids):04d}", chirps=[chirp]))

    closed_tracks.extend(open_tracks)
    return tuple(finalize_track(track, packet, config) for track in closed_tracks)


def is_compatible(chirp: Chirp, track: _OpenTrack, config: TrackingConfig) -> bool:
    delta_time = chirp.time_ms - track.last_chirp.time_ms
    if delta_time <= 0:
        return False
    predicted_ici = track.predicted_ici_ms(config)
    time_tolerance = max(1.0, predicted_ici * config.ici_tolerance_ratio)
    fme_delta_bins = abs(chirp.posFME - track.fme_center_bins())
    return abs(delta_time - predicted_ici) <= time_tolerance and fme_delta_bins <= config.fme_tolerance_bins


def compatibility_score(chirp: Chirp, track: _OpenTrack, config: TrackingConfig) -> float:
    predicted_ici = track.predicted_ici_ms(config)
    time_tolerance = max(1.0, predicted_ici * config.ici_tolerance_ratio)
    time_error = abs((chirp.time_ms - track.last_chirp.time_ms) - predicted_ici) / time_tolerance
    fme_error = abs(chirp.posFME - track.fme_center_bins()) / max(1.0, config.fme_tolerance_bins)
    return time_error + fme_error


def finalize_track(track: _OpenTrack, packet: SpeciesPacket, config: TrackingConfig) -> IndividualTrack:
    chirps = tuple(sorted(track.chirps, key=lambda item: item.time_ms))
    times = np.array([chirp.time_ms for chirp in chirps], dtype=float)
    ici_median = float(np.median(np.diff(times))) if times.size > 1 else float("nan")
    fme_median = float(np.median([chirp.FME_kHz for chirp in chirps]))
    suspicious = bool(np.isfinite(ici_median) and ici_median < config.suspicious_short_ici_ms)
    return IndividualTrack(
        track_id=track.track_id,
        passage_id=packet.passage_id,
        packet_id=packet.packet_id,
        passage_species=packet.passage_species,
        chirps=chirps,
        start_time_ms=int(chirps[0].time_ms),
        end_time_ms=int(chirps[-1].time_ms),
        n_chirps=len(chirps),
        fme_median_khz=fme_median,
        ici_median_ms=ici_median,
        suspicious_short_ici=suspicious,
    )
