from __future__ import annotations

import csv
import importlib
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    from .bat_preprocessing import PreprocessingConfig, preprocess_passages
    from .individual_counting import IndividualTrack, SpeciesSplitConfig, TrackingConfig
except ImportError:
    from bat_preprocessing import PreprocessingConfig, preprocess_passages
    from individual_counting import IndividualTrack, SpeciesSplitConfig, TrackingConfig


SENSOR_SAMPLE_KHZ = 200
FFT_LENGTH = 512
FFT_OVERLAP = 2
SNR_MIN_DB = 19
BIN_KHZ = SENSOR_SAMPLE_KHZ / FFT_LENGTH
WINDOW_MS = FFT_LENGTH / FFT_OVERLAP / SENSOR_SAMPLE_KHZ
DEFAULT_SEEDS = {"dev": 20260511, "test": 20260512}
DISCRETE_CASES = (
    "single_clean",
    "same_species_distinct_ici",
    "same_species_half_ici",
    "many_superposed",
    "different_species_superposed",
    "strong_echoes",
    "filtered_low_noise",
    "short_passages",
    "feeding_buzz",
    "close_fme_and_ici",
)
SWEEP_VALUES = tuple(range(10, 101, 10))


@dataclass(frozen=True)
class SensorRow:
    time_ms: int
    posFME: int
    posFI: int
    posFT: int
    duree_bins: int
    snr_db: int


@dataclass(frozen=True)
class TruthIndividual:
    dataset: str
    scenario_id: str
    case_type: str
    replicate_id: int
    individual_id: str
    species: str
    start_ms: int
    end_ms: int
    expected_count: int
    n_chirps: int
    fme_khz: float
    ici_ms: float
    phase: str
    notes: str


@dataclass(frozen=True)
class ScenarioWindow:
    dataset: str
    scenario_id: str
    case_type: str
    replicate_id: int
    start_ms: int
    end_ms: int
    expected_count: int
    parameter_name: str
    parameter_value: float


@dataclass(frozen=True)
class GenerationResult:
    dataset: str
    rows: tuple[SensorRow, ...]
    truth: tuple[TruthIndividual, ...]
    scenarios: tuple[ScenarioWindow, ...]
    seed: int


@dataclass(frozen=True)
class TrackAssignment:
    track_id: str
    scenario_id: str
    case_type: str
    n_chirps: int
    matched_chirps: int
    assignment_status: str
    start_time_ms: int
    end_time_ms: int
    passage_species: str


@dataclass(frozen=True)
class ScenarioMetric:
    dataset: str
    scenario_id: str
    case_type: str
    replicate_id: int
    parameter_name: str
    parameter_value: float
    expected_count: int
    detected_count: int
    signed_error: int
    absolute_error: int
    squared_error: int
    exact_match: bool
    undercount: bool
    overcount: bool


@dataclass(frozen=True)
class SummaryMetric:
    group: str
    n_scenarios: int
    bias_mean: float
    bias_ci_low: float
    bias_ci_high: float
    mae: float
    mae_ci_low: float
    mae_ci_high: float
    rmse: float
    exact_rate: float
    exact_ci_low: float
    exact_ci_high: float
    undercount_rate: float
    overcount_rate: float


SPECIES = {
    "kuhl": {"name": "Pipistrellus kuhlii", "fme": 37.0, "fi_offset": 4.0, "ft_offset": 2.0, "ici": 170.0},
    "common": {"name": "Pipistrellus pipistrellus", "fme": 46.5, "fi_offset": 4.0, "ft_offset": 2.0, "ici": 125.0},
    "pygmy": {"name": "Pipistrellus pygmaeus", "fme": 55.0, "fi_offset": 4.0, "ft_offset": 2.0, "ici": 115.0},
    "serotine": {"name": "Eptesicus serotinus", "fme": 27.0, "fi_offset": 8.0, "ft_offset": 3.0, "ici": 260.0},
    "noctule": {"name": "Nyctalus sp.", "fme": 22.0, "fi_offset": 8.0, "ft_offset": 3.0, "ici": 260.0},
}


def generate_validation_dataset(
    dataset: str = "dev",
    n_replicates: int = 100,
    seed: int | None = None,
    sweep_replicates: int | None = None,
) -> GenerationResult:
    if dataset not in {"dev", "test"}:
        raise ValueError("dataset must be 'dev' or 'test'")
    seed = DEFAULT_SEEDS[dataset] if seed is None else seed
    sweep_replicates = max(1, n_replicates // 5) if sweep_replicates is None else sweep_replicates
    rng = np.random.default_rng(seed)
    rows: list[SensorRow] = []
    truth: list[TruthIndividual] = []
    scenarios: list[ScenarioWindow] = []
    cursor_ms = 0

    for case_type in DISCRETE_CASES:
        for replicate_id in range(1, n_replicates + 1):
            cursor_ms = _append_scenario(dataset, case_type, replicate_id, cursor_ms, rng, rows, truth, scenarios)

    for delta_ms in SWEEP_VALUES:
        for replicate_id in range(1, sweep_replicates + 1):
            cursor_ms = _append_scenario(
                dataset,
                "ici_sweep",
                replicate_id,
                cursor_ms,
                rng,
                rows,
                truth,
                scenarios,
                parameter_name="ici_delta_ms",
                parameter_value=float(delta_ms),
            )
    for delta_bins in range(1, 11):
        for replicate_id in range(1, sweep_replicates + 1):
            cursor_ms = _append_scenario(
                dataset,
                "fme_sweep",
                replicate_id,
                cursor_ms,
                rng,
                rows,
                truth,
                scenarios,
                parameter_name="fme_delta_bins",
                parameter_value=float(delta_bins),
            )

    rows.sort(key=lambda row: row.time_ms)
    return GenerationResult(dataset, tuple(rows), tuple(truth), tuple(scenarios), seed)


def _append_scenario(
    dataset: str,
    case_type: str,
    replicate_id: int,
    cursor_ms: int,
    rng: np.random.Generator,
    rows: list[SensorRow],
    truth: list[TruthIndividual],
    scenarios: list[ScenarioWindow],
    parameter_name: str = "",
    parameter_value: float = math.nan,
) -> int:
    if parameter_name:
        parameter_slug = f"{parameter_name}-{parameter_value:g}".replace(".", "p")
        scenario_id = f"{dataset}-{case_type}-{parameter_slug}-{replicate_id:04d}"
    else:
        scenario_id = f"{dataset}-{case_type}-{replicate_id:04d}"
    start_ms = cursor_ms + int(rng.integers(850, 1300))
    specs = _scenario_specs(case_type, rng, parameter_value)
    expected_count = sum(1 for spec in specs if not spec.get("noise", False))
    scenario_start = start_ms
    scenario_end = start_ms

    for index, spec in enumerate(specs, start=1):
        individual_id = f"{scenario_id}-ind-{index:02d}"
        generated = _generate_individual_rows(start_ms, spec, rng, individual_id)
        rows.extend(generated)
        real_rows = [row for row in generated if not spec.get("noise", False)]
        if real_rows and not spec.get("noise", False):
            individual_start = min(row.time_ms for row in real_rows)
            individual_end = max(row.time_ms for row in real_rows)
            scenario_start = min(scenario_start, individual_start)
            scenario_end = max(scenario_end, individual_end)
            truth.append(
                TruthIndividual(
                    dataset=dataset,
                    scenario_id=scenario_id,
                    case_type=case_type,
                    replicate_id=replicate_id,
                    individual_id=individual_id,
                    species=str(spec["species"]),
                    start_ms=individual_start,
                    end_ms=individual_end,
                    expected_count=expected_count,
                    n_chirps=int(spec["n_chirps"]),
                    fme_khz=float(spec["fme_khz"]),
                    ici_ms=float(spec["ici_ms"]),
                    phase=str(spec["phase"]),
                    notes=_scenario_notes(case_type, parameter_name, parameter_value),
                )
            )

    if expected_count == 0:
        scenario_end = start_ms + 250
    scenarios.append(
        ScenarioWindow(
            dataset=dataset,
            scenario_id=scenario_id,
            case_type=case_type,
            replicate_id=replicate_id,
            start_ms=scenario_start - 20,
            end_ms=scenario_end + 20,
            expected_count=expected_count,
            parameter_name=parameter_name,
            parameter_value=parameter_value,
        )
    )
    return scenario_end + 1200


def _scenario_specs(case_type: str, rng: np.random.Generator, parameter_value: float) -> list[dict[str, object]]:
    base = _individual_spec("kuhl", rng)
    if case_type == "single_clean":
        return [base]
    if case_type == "same_species_distinct_ici":
        return [base, {**_individual_spec("kuhl", rng), "start_offset_ms": 25, "ici_ms": base["ici_ms"] * 1.45}]
    if case_type == "same_species_half_ici":
        return [base, {**_individual_spec("kuhl", rng), "start_offset_ms": base["ici_ms"] / 2, "ici_ms": base["ici_ms"]}]
    if case_type == "many_superposed":
        count = int(rng.integers(3, 6))
        return [{**_individual_spec("common", rng), "start_offset_ms": int(rng.integers(0, 80))} for _ in range(count)]
    if case_type == "different_species_superposed":
        return [
            _individual_spec("kuhl", rng),
            {**_individual_spec("pygmy", rng), "start_offset_ms": 35},
            {**_individual_spec("serotine", rng), "start_offset_ms": 70},
        ]
    if case_type == "strong_echoes":
        return [{**base, "echo_probability": 0.75, "echo_snr_loss": 3}]
    if case_type == "filtered_low_noise":
        return [base, {**_individual_spec("noctule", rng), "noise": True, "fme_khz": 14.0, "n_chirps": 8}]
    if case_type == "short_passages":
        return [{**base, "n_chirps": 2}, {**_individual_spec("common", rng), "n_chirps": 2, "start_offset_ms": 40}]
    if case_type == "feeding_buzz":
        return [{**base, "phase": "feeding_buzz", "ici_ms": 32.0, "n_chirps": int(rng.integers(12, 26))}]
    if case_type == "close_fme_and_ici":
        return [base, {**_individual_spec("kuhl", rng), "start_offset_ms": 35, "ici_ms": base["ici_ms"] * 1.08, "fme_khz": base["fme_khz"] + BIN_KHZ}]
    if case_type == "ici_sweep":
        delta = float(parameter_value)
        return [base, {**_individual_spec("kuhl", rng), "start_offset_ms": 25, "ici_ms": base["ici_ms"] + delta}]
    if case_type == "fme_sweep":
        delta_khz = float(parameter_value) * BIN_KHZ
        return [base, {**_individual_spec("kuhl", rng), "start_offset_ms": 35, "fme_khz": base["fme_khz"] + delta_khz}]
    raise ValueError(f"Unknown case_type: {case_type}")


def _individual_spec(species_id: str, rng: np.random.Generator) -> dict[str, object]:
    species = SPECIES[species_id]
    ici = float(species["ici"]) * float(rng.uniform(0.8, 1.2))
    fme = float(species["fme"]) + float(rng.normal(0, BIN_KHZ * 2))
    return {
        "species": species["name"],
        "fme_khz": fme,
        "fi_khz": fme + float(species["fi_offset"]),
        "ft_khz": max(5.0, fme - float(species["ft_offset"])),
        "ici_ms": ici,
        "n_chirps": int(rng.integers(10, 51)),
        "jitter_ratio": float(rng.uniform(0.06, 0.22)),
        "snr_mean": float(rng.uniform(24, 36)),
        "snr_std": float(rng.uniform(1.5, 5.0)),
        "duration_ms": float(rng.uniform(4, 10)),
        "phase": "transit",
        "start_offset_ms": 0.0,
        "echo_probability": float(rng.uniform(0.0, 0.2)),
        "echo_snr_loss": 7.0,
        "noise": False,
    }


def _generate_individual_rows(
    scenario_start_ms: int,
    spec: dict[str, object],
    rng: np.random.Generator,
    individual_id: str,
) -> list[SensorRow]:
    del individual_id
    rows: list[SensorRow] = []
    current = scenario_start_ms + int(round(float(spec.get("start_offset_ms", 0.0))))
    for _ in range(int(spec["n_chirps"])):
        fme = max(5.0, float(rng.normal(float(spec["fme_khz"]), BIN_KHZ)))
        fi = max(fme, float(rng.normal(float(spec["fi_khz"]), BIN_KHZ)))
        ft = min(fme, float(rng.normal(float(spec["ft_khz"]), BIN_KHZ)))
        snr = int(round(np.clip(rng.normal(float(spec["snr_mean"]), float(spec["snr_std"])), SNR_MIN_DB, 40)))
        row = SensorRow(current, khz_to_bin(fme), khz_to_bin(fi), khz_to_bin(ft), duration_ms_to_windows(float(spec["duration_ms"])), snr)
        rows.append(row)
        if rng.random() < float(spec["echo_probability"]):
            delay = int(rng.integers(1, 11))
            delta = int(rng.integers(-1, 2))
            rows.append(
                SensorRow(
                    current + delay,
                    int(np.clip(row.posFME + delta, 0, 255)),
                    int(np.clip(row.posFI + delta, 0, 255)),
                    int(np.clip(row.posFT + delta, 0, 255)),
                    row.duree_bins,
                    int(max(SNR_MIN_DB, row.snr_db - float(spec["echo_snr_loss"]))),
                )
            )
        ici = max(4.0, rng.normal(float(spec["ici_ms"]), float(spec["ici_ms"]) * float(spec["jitter_ratio"])))
        current += int(round(ici))
    return rows


def write_generation_outputs(result: GenerationResult, output_dir: str | Path = "data/simulated") -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    txt_path = output / f"DATA_DUMMY_{result.dataset}.TXT"
    truth_path = output / f"DATA_DUMMY_{result.dataset}_truth.csv"
    write_sensor_txt(txt_path, result.rows)
    write_truth_csv(truth_path, result.truth)
    return txt_path, truth_path


def write_sensor_txt(path: str | Path, rows: Iterable[SensorRow]) -> None:
    rows = tuple(sorted(rows, key=lambda row: row.time_ms))
    lines = [
        "DETECTDATA",
        f"FREQ_KHZ_ENREG {SENSOR_SAMPLE_KHZ}",
        f"LENFFT {FFT_LENGTH}",
        f"OVERLAP {FFT_OVERLAP}",
        f"SNRMIN {SNR_MIN_DB}",
        f"detectData_nbsig {len(rows)}",
        f"nbsig_detect {len(rows)}",
        "temps_ms_fin_prec 0",
        "RAW-ASCII 1",
        "time_ms posFME posFI posFT posDUREE SNRdB",
        "raw: uint32 uint8 uint8 uint8 uint8 uint8",
        "",
        "DATAASCII",
    ]
    lines.extend(sensor_row_to_text(row) for row in rows)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def write_truth_csv(path: str | Path, truth: Iterable[TruthIndividual]) -> None:
    rows = tuple(truth)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(TruthIndividual.__dataclass_fields__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def read_truth_csv(path: str | Path) -> tuple[TruthIndividual, ...]:
    with Path(path).open(newline="", encoding="utf-8") as file:
        rows = []
        for item in csv.DictReader(file):
            rows.append(
                TruthIndividual(
                    dataset=item["dataset"],
                    scenario_id=item["scenario_id"],
                    case_type=item["case_type"],
                    replicate_id=int(item["replicate_id"]),
                    individual_id=item["individual_id"],
                    species=item["species"],
                    start_ms=int(item["start_ms"]),
                    end_ms=int(item["end_ms"]),
                    expected_count=int(item["expected_count"]),
                    n_chirps=int(item["n_chirps"]),
                    fme_khz=float(item["fme_khz"]),
                    ici_ms=float(item["ici_ms"]),
                    phase=item["phase"],
                    notes=item["notes"],
                )
            )
    return tuple(rows)


def scenarios_from_truth(truth: Iterable[TruthIndividual]) -> tuple[ScenarioWindow, ...]:
    grouped: dict[str, list[TruthIndividual]] = {}
    for row in truth:
        grouped.setdefault(row.scenario_id, []).append(row)
    scenarios = []
    for scenario_id, rows in grouped.items():
        first = rows[0]
        parameter_name, parameter_value = _parse_parameter_from_notes(first.notes)
        scenarios.append(
            ScenarioWindow(
                dataset=first.dataset,
                scenario_id=scenario_id,
                case_type=first.case_type,
                replicate_id=first.replicate_id,
                start_ms=min(row.start_ms for row in rows) - 20,
                end_ms=max(row.end_ms for row in rows) + 20,
                expected_count=first.expected_count,
                parameter_name=parameter_name,
                parameter_value=parameter_value,
            )
        )
    return tuple(sorted(scenarios, key=lambda scenario: scenario.start_ms))


def evaluate_dataset(
    txt_path: str | Path,
    truth_path: str | Path,
    tracker_module: str = "src.individual_counting",
    output_dir: str | Path = "data/processed",
    plot_dir: str | Path = "plots/counting",
    dataset: str | None = None,
    bootstrap_seed: int = 20260511,
) -> tuple[tuple[ScenarioMetric, ...], tuple[SummaryMetric, ...], tuple[TrackAssignment, ...]]:
    truth = read_truth_csv(truth_path)
    scenarios = scenarios_from_truth(truth)
    preprocessing = preprocess_passages(
        str(txt_path),
        PreprocessingConfig(
            passage_gap_ms=100.0,
            echo_gap_ms=10.0,
            echo_fme_bins=1.0,
            fme_min_khz=18.0,
            min_passage_chirps=1,
            echo_strategy="best_snr",
        ),
    )
    result = run_tracker(preprocessing.passages, tracker_module)
    assignments = assign_tracks_to_scenarios(result.tracks, scenarios)
    metrics = compute_scenario_metrics(scenarios, assignments)
    summary = summarize_metrics(metrics, seed=bootstrap_seed)
    name = dataset or (truth[0].dataset if truth else "validation")
    write_evaluation_outputs(name, metrics, summary, assignments, output_dir)
    plot_validation_outputs(name, metrics, summary, plot_dir)
    return metrics, summary, assignments


def run_tracker(passages, tracker_module: str):
    module = importlib.import_module(tracker_module)
    count_individuals = getattr(module, "count_individuals")
    split_config_cls = getattr(module, "SpeciesSplitConfig", SpeciesSplitConfig)
    tracking_config_cls = getattr(module, "TrackingConfig", TrackingConfig)
    return count_individuals(passages, split_config_cls(), tracking_config_cls())


def assign_tracks_to_scenarios(
    tracks: Iterable[IndividualTrack],
    scenarios: Iterable[ScenarioWindow],
) -> tuple[TrackAssignment, ...]:
    scenario_list = tuple(scenarios)
    assignments = []
    for track in tracks:
        counts = []
        for scenario in scenario_list:
            matched = sum(1 for chirp in track.chirps if scenario.start_ms <= chirp.time_ms <= scenario.end_ms)
            if matched:
                counts.append((matched, scenario))
        if not counts:
            assignments.append(
                TrackAssignment(
                    track_id=track.track_id,
                    scenario_id="UNASSIGNED",
                    case_type="false_positive",
                    n_chirps=track.n_chirps,
                    matched_chirps=0,
                    assignment_status="unassigned_false_positive",
                    start_time_ms=track.start_time_ms,
                    end_time_ms=track.end_time_ms,
                    passage_species=track.passage_species,
                )
            )
            continue
        counts.sort(key=lambda item: item[0], reverse=True)
        best_count, best_scenario = counts[0]
        status = "assigned"
        if len(counts) > 1:
            status = "ambiguous_majority"
        if best_count < math.ceil(track.n_chirps / 2):
            status = "ambiguous_no_majority"
        assignments.append(
            TrackAssignment(
                track_id=track.track_id,
                scenario_id=best_scenario.scenario_id,
                case_type=best_scenario.case_type,
                n_chirps=track.n_chirps,
                matched_chirps=best_count,
                assignment_status=status,
                start_time_ms=track.start_time_ms,
                end_time_ms=track.end_time_ms,
                passage_species=track.passage_species,
            )
        )
    return tuple(assignments)


def compute_scenario_metrics(
    scenarios: Iterable[ScenarioWindow],
    assignments: Iterable[TrackAssignment],
) -> tuple[ScenarioMetric, ...]:
    assigned_counts: dict[str, int] = {}
    for assignment in assignments:
        if assignment.scenario_id == "UNASSIGNED":
            continue
        assigned_counts[assignment.scenario_id] = assigned_counts.get(assignment.scenario_id, 0) + 1
    metrics = []
    for scenario in scenarios:
        detected = assigned_counts.get(scenario.scenario_id, 0)
        signed_error = detected - scenario.expected_count
        metrics.append(
            ScenarioMetric(
                dataset=scenario.dataset,
                scenario_id=scenario.scenario_id,
                case_type=scenario.case_type,
                replicate_id=scenario.replicate_id,
                parameter_name=scenario.parameter_name,
                parameter_value=scenario.parameter_value,
                expected_count=scenario.expected_count,
                detected_count=detected,
                signed_error=signed_error,
                absolute_error=abs(signed_error),
                squared_error=signed_error * signed_error,
                exact_match=signed_error == 0,
                undercount=signed_error < 0,
                overcount=signed_error > 0,
            )
        )
    return tuple(metrics)


def summarize_metrics(
    metrics: Iterable[ScenarioMetric],
    seed: int = 20260511,
    bootstrap_samples: int = 1000,
) -> tuple[SummaryMetric, ...]:
    metric_list = tuple(metrics)
    groups = {"global": metric_list}
    for case_type in sorted({metric.case_type for metric in metric_list}):
        groups[case_type] = [metric for metric in metric_list if metric.case_type == case_type]
    return tuple(_summary_for_group(name, rows, seed, bootstrap_samples) for name, rows in groups.items() if rows)


def _summary_for_group(name: str, rows: list[ScenarioMetric] | tuple[ScenarioMetric, ...], seed: int, bootstrap_samples: int) -> SummaryMetric:
    signed = np.array([row.signed_error for row in rows], dtype=float)
    absolute = np.array([row.absolute_error for row in rows], dtype=float)
    squared = np.array([row.squared_error for row in rows], dtype=float)
    exact = np.array([row.exact_match for row in rows], dtype=float)
    under = np.array([row.undercount for row in rows], dtype=float)
    over = np.array([row.overcount for row in rows], dtype=float)
    bias_ci = bootstrap_ci(signed, np.mean, seed, bootstrap_samples)
    mae_ci = bootstrap_ci(absolute, np.mean, seed + 1, bootstrap_samples)
    exact_ci = bootstrap_ci(exact, np.mean, seed + 2, bootstrap_samples)
    return SummaryMetric(
        group=name,
        n_scenarios=len(rows),
        bias_mean=float(np.mean(signed)),
        bias_ci_low=bias_ci[0],
        bias_ci_high=bias_ci[1],
        mae=float(np.mean(absolute)),
        mae_ci_low=mae_ci[0],
        mae_ci_high=mae_ci[1],
        rmse=float(np.sqrt(np.mean(squared))),
        exact_rate=float(np.mean(exact)),
        exact_ci_low=exact_ci[0],
        exact_ci_high=exact_ci[1],
        undercount_rate=float(np.mean(under)),
        overcount_rate=float(np.mean(over)),
    )


def bootstrap_ci(
    values: np.ndarray,
    statistic,
    seed: int = 20260511,
    samples: int = 1000,
    alpha: float = 0.05,
) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return (math.nan, math.nan)
    rng = np.random.default_rng(seed)
    estimates = np.empty(samples, dtype=float)
    for index in range(samples):
        sample = rng.choice(values, size=values.size, replace=True)
        estimates[index] = float(statistic(sample))
    return (float(np.quantile(estimates, alpha / 2)), float(np.quantile(estimates, 1 - alpha / 2)))


def write_evaluation_outputs(
    dataset: str,
    metrics: Iterable[ScenarioMetric],
    summary: Iterable[SummaryMetric],
    assignments: Iterable[TrackAssignment],
    output_dir: str | Path = "data/processed",
) -> tuple[Path, Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics_path = output / f"validation_{dataset}_metrics_by_scenario.csv"
    summary_path = output / f"validation_{dataset}_summary_by_case.csv"
    assignments_path = output / f"validation_{dataset}_track_assignments.csv"
    _write_dataclass_csv(metrics_path, metrics, ScenarioMetric)
    _write_dataclass_csv(summary_path, summary, SummaryMetric)
    _write_dataclass_csv(assignments_path, assignments, TrackAssignment)
    return metrics_path, summary_path, assignments_path


def plot_validation_outputs(
    dataset: str,
    metrics: Iterable[ScenarioMetric],
    summary: Iterable[SummaryMetric],
    plot_dir: str | Path = "plots/counting",
) -> tuple[Path, ...]:
    import matplotlib.pyplot as plt

    output = Path(plot_dir)
    output.mkdir(parents=True, exist_ok=True)
    metric_list = tuple(metrics)
    summary_by_group = {row.group: row for row in summary}
    case_summaries = [row for row in summary_by_group.values() if row.group != "global" and not row.group.endswith("_sweep")]
    paths: list[Path] = []

    if case_summaries:
        labels = [row.group for row in case_summaries]
        x = np.arange(len(labels))
        fig, ax = plt.subplots(figsize=(12, 5))
        y = np.array([row.mae for row in case_summaries])
        yerr = np.array([[row.mae - row.mae_ci_low for row in case_summaries], [row.mae_ci_high - row.mae for row in case_summaries]])
        ax.bar(x, y, yerr=yerr, capsize=4, color="0.35")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right")
        ax.set_ylabel("Mean absolute count error")
        ax.set_title(f"Counting MAE by scenario type ({dataset})")
        ax.grid(True, axis="y", alpha=0.25)
        path = output / f"validation_{dataset}_count_error.png"
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)
        paths.append(path)

        fig, ax = plt.subplots(figsize=(12, 5))
        y = np.array([row.exact_rate for row in case_summaries])
        yerr = np.array([[row.exact_rate - row.exact_ci_low for row in case_summaries], [row.exact_ci_high - row.exact_rate for row in case_summaries]])
        ax.bar(x, y, yerr=yerr, capsize=4, color="0.45")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right")
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Exact count rate")
        ax.set_title(f"Exact counting rate by scenario type ({dataset})")
        ax.grid(True, axis="y", alpha=0.25)
        path = output / f"validation_{dataset}_exact_rate.png"
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)
        paths.append(path)

    fig, ax = plt.subplots(figsize=(6, 6))
    expected = [row.expected_count for row in metric_list]
    detected = [row.detected_count for row in metric_list]
    ax.scatter(expected, detected, alpha=0.35, s=18)
    upper = max(expected + detected + [1])
    ax.plot([0, upper], [0, upper], color="black", linestyle="--", linewidth=1)
    ax.set_xlabel("Simulated individuals")
    ax.set_ylabel("Detected tracks")
    ax.set_title(f"Expected vs detected counts ({dataset})")
    ax.grid(True, alpha=0.25)
    path = output / f"validation_{dataset}_expected_vs_detected.png"
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths.append(path)

    for case_type, parameter_name, filename in [
        ("ici_sweep", "ici_delta_ms", "ici_sweep"),
        ("fme_sweep", "fme_delta_bins", "fme_sweep"),
    ]:
        sweep = [row for row in metric_list if row.case_type == case_type]
        if sweep:
            path = output / f"validation_{dataset}_{filename}.png"
            _plot_sweep(path, sweep, parameter_name, dataset)
            paths.append(path)

    fig, ax = plt.subplots(figsize=(8, 4))
    errors = [row.signed_error for row in metric_list]
    bins = np.arange(min(errors + [0]) - 0.5, max(errors + [0]) + 1.5, 1)
    ax.hist(errors, bins=bins, color="0.4", alpha=0.85)
    ax.axvline(0, color="black", linestyle="--", linewidth=1)
    ax.set_xlabel("Detected - simulated")
    ax.set_ylabel("Scenario count")
    ax.set_title(f"Signed count error distribution ({dataset})")
    ax.grid(True, axis="y", alpha=0.25)
    path = output / f"validation_{dataset}_signed_error_hist.png"
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    paths.append(path)
    return tuple(paths)


def _plot_sweep(path: Path, metrics: list[ScenarioMetric], parameter_name: str, dataset: str) -> None:
    import matplotlib.pyplot as plt

    values = sorted({row.parameter_value for row in metrics if np.isfinite(row.parameter_value)})
    mae = []
    exact = []
    for value in values:
        rows = [row for row in metrics if row.parameter_value == value]
        mae.append(float(np.mean([row.absolute_error for row in rows])))
        exact.append(float(np.mean([row.exact_match for row in rows])))
    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    ax1.plot(values, mae, marker="o", color="0.2", label="MAE")
    ax1.set_xlabel(parameter_name)
    ax1.set_ylabel("Mean absolute count error")
    ax1.grid(True, alpha=0.25)
    ax2 = ax1.twinx()
    ax2.plot(values, exact, marker="s", color="0.55", label="Exact rate")
    ax2.set_ylim(0, 1.05)
    ax2.set_ylabel("Exact count rate")
    ax1.set_title(f"Counting robustness: {parameter_name} ({dataset})")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def profile_runtime(
    dataset: str = "dev",
    n_replicates: int = 5,
    tracker_module: str = "src.individual_counting",
) -> dict[str, float]:
    start = time.perf_counter()
    result = generate_validation_dataset(dataset=dataset, n_replicates=n_replicates, sweep_replicates=max(1, n_replicates // 5))
    generation_sec = time.perf_counter() - start
    tmp = Path("data/processed") / "_validation_profile.TXT"
    write_sensor_txt(tmp, result.rows)
    start_eval = time.perf_counter()
    preprocessing = preprocess_passages(
        str(tmp),
        PreprocessingConfig(echo_strategy="best_snr", min_passage_chirps=1),
    )
    run_tracker(preprocessing.passages, tracker_module)
    evaluation_sec = time.perf_counter() - start_eval
    try:
        tmp.unlink()
    except OSError:
        pass
    scenario_count = len(result.scenarios)
    per_scenario = (generation_sec + evaluation_sec) / max(1, scenario_count)
    return {
        "n_scenarios": float(scenario_count),
        "n_rows": float(len(result.rows)),
        "generation_sec": generation_sec,
        "evaluation_sec": evaluation_sec,
        "sec_per_scenario": per_scenario,
        "estimated_1000_scenarios_sec": per_scenario * 1000,
    }


def _write_dataclass_csv(path: Path, rows: Iterable[object], cls: type) -> None:
    rows = tuple(rows)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(cls.__dataclass_fields__.keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def _parse_parameter_from_notes(notes: str) -> tuple[str, float]:
    if "=" not in notes:
        return "", math.nan
    key, raw_value = notes.split("=", 1)
    try:
        return key, float(raw_value)
    except ValueError:
        return "", math.nan


def _scenario_notes(case_type: str, parameter_name: str, parameter_value: float) -> str:
    del case_type
    if parameter_name:
        return f"{parameter_name}={parameter_value:g}"
    return ""


def sensor_row_to_text(row: SensorRow) -> str:
    return f"{row.time_ms} {row.posFME} {row.posFI} {row.posFT} {row.duree_bins} {row.snr_db}"


def khz_to_bin(khz: float) -> int:
    return int(np.clip(round(khz / BIN_KHZ), 0, 255))


def duration_ms_to_windows(duration_ms: float) -> int:
    return max(1, int(round(duration_ms / WINDOW_MS)))
