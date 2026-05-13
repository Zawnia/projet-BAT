import argparse
import csv
from pathlib import Path

import numpy as np

try:
    from .bat_preprocessing import PreprocessingConfig, preprocess_passages
    from .individual_counting import CountingResult, SpeciesSplitConfig, TrackingConfig, count_individuals
except ImportError:
    from bat_preprocessing import PreprocessingConfig, preprocess_passages
    from individual_counting import CountingResult, SpeciesSplitConfig, TrackingConfig, count_individuals


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate individual bat tracks inside acoustic passages.")
    parser.add_argument("input", help="Input DATA*.TXT file")
    parser.add_argument("--fme-min-khz", type=float, default=18.0, help="Minimum FME kept for counting")
    parser.add_argument("--passage-gap-ms", type=float, default=100.0, help="Gap starting a new acoustic passage")
    parser.add_argument("--echo-gap-ms", type=float, default=10.0, help="Maximum gap for echo detection")
    parser.add_argument("--echo-fme-bins", type=float, default=1.0, help="Maximum FME bin delta for echo detection")
    parser.add_argument("--min-passage-chirps", type=int, default=3, help="Minimum chirps kept in a passage")
    parser.add_argument("--min-chirps-for-kde", type=int, default=15, help="Minimum chirps before intra-passage KDE species split")
    parser.add_argument("--ici-tolerance-ratio", type=float, default=0.30, help="Relative ICI tolerance for track assignment")
    parser.add_argument("--fme-tolerance-bins", type=float, default=2.0, help="FME tolerance in FFT bins for track assignment")
    parser.add_argument("--track-expiry-n-ici", type=float, default=3.0, help="Close a track after this many predicted ICIs")
    parser.add_argument("--min-track-chirps", type=int, default=3, help="Minimum chirps for a counted track")
    parser.add_argument("--bootstrap-ici-ms", type=float, default=100.0, help="Nominal ICI for newborn tracks")
    parser.add_argument("--suspicious-short-ici-ms", type=float, default=45.0, help="Flag tracks below this median ICI")
    parser.add_argument("--tracks-csv", default=None, help="Optional CSV export path for estimated tracks")
    parser.add_argument("--report-output", default=None, help="Optional text report export path")
    parser.add_argument("--plot-output", default=None, help="Optional PNG path for a counting summary plot")
    parser.add_argument("--plot-window-sec", type=float, default=30.0, help="Dense activity zoom window for the plot")
    parser.add_argument("--plot-window-min", type=float, default=None, help="Deprecated alias for --plot-window-sec / 60")
    args = parser.parse_args()

    preprocessing = preprocess_passages(
        args.input,
        PreprocessingConfig(
            passage_gap_ms=args.passage_gap_ms,
            echo_gap_ms=args.echo_gap_ms,
            echo_fme_bins=args.echo_fme_bins,
            fme_min_khz=args.fme_min_khz,
            min_passage_chirps=args.min_passage_chirps,
            echo_strategy="best_snr",
        ),
    )
    result = count_individuals(
        preprocessing.passages,
        SpeciesSplitConfig(min_chirps_for_kde=args.min_chirps_for_kde),
        TrackingConfig(
            ici_tolerance_ratio=args.ici_tolerance_ratio,
            fme_tolerance_bins=args.fme_tolerance_bins,
            track_expiry_n_ici=args.track_expiry_n_ici,
            min_track_chirps=args.min_track_chirps,
            bootstrap_ici_ms=args.bootstrap_ici_ms,
            suspicious_short_ici_ms=args.suspicious_short_ici_ms,
        ),
    )

    report = format_counting_report(result)
    print(report)
    if args.report_output:
        write_text(args.report_output, report)
        print(f"\nText report saved     : {args.report_output}")
    if args.tracks_csv:
        write_tracks_csv(args.tracks_csv, result)
        print(f"Tracks CSV saved      : {args.tracks_csv}")
    if args.plot_output:
        plot_window_sec = args.plot_window_min * 60 if args.plot_window_min is not None else args.plot_window_sec
        plot_tracks(args.plot_output, result, args.suspicious_short_ici_ms, plot_window_sec)
        print(f"Track plot saved      : {args.plot_output}")


def format_counting_report(result: CountingResult) -> str:
    lines = [
        "Individual counting report",
        "==========================",
        "",
        "Summary",
        f"  Passages detected       : {result.summary['n_passages_detected']}",
        f"  Individuals estimated   : {result.summary['n_individuals_estimated']}",
        f"  Suspicious short ICI    : {result.summary['n_suspicious_short_ici_tracks']}",
        "",
        "Individuals by species",
    ]
    by_species = result.summary["individuals_by_species"]
    if by_species:
        for species, count in sorted(by_species.items()):
            lines.append(f"  {species}: {count}")
    else:
        lines.append("  None")

    lines.extend([
        "",
        "Tracks",
        "  track_id    passage  species                       chirps  start_ms  end_ms    FME_kHz  ICI_ms  flags",
        "  ----------  -------  ----------------------------  ------  --------  --------  -------  ------  --------------------",
    ])
    if not result.tracks:
        lines.append("  No counted tracks")
    for track in result.tracks:
        flags = "suspicious_short_ici" if track.suspicious_short_ici else "-"
        lines.append(
            f"  {track.track_id:<10}  {track.passage_id:>7}  "
            f"{track.passage_species:<28.28}  {track.n_chirps:>6}  "
            f"{track.start_time_ms:>8}  {track.end_time_ms:>8}  "
            f"{track.fme_median_khz:>7.2f}  {track.ici_median_ms:>6.1f}  {flags}"
        )
    return "\n".join(lines)


def write_text(path: str, text: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8")


def write_tracks_csv(path: str, result: CountingResult) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            "track_id",
            "passage_id",
            "packet_id",
            "passage_species",
            "start_time_ms",
            "end_time_ms",
            "n_chirps",
            "fme_median_khz",
            "ici_median_ms",
            "suspicious_short_ici",
        ])
        for track in result.tracks:
            writer.writerow([
                track.track_id,
                track.passage_id,
                track.packet_id,
                track.passage_species,
                track.start_time_ms,
                track.end_time_ms,
                track.n_chirps,
                f"{track.fme_median_khz:.6f}",
                f"{track.ici_median_ms:.6f}",
                str(track.suspicious_short_ici).lower(),
            ])


def plot_tracks(
    path: str,
    result: CountingResult,
    suspicious_short_ici_ms: float = 45.0,
    zoom_window_sec: float = 30.0,
) -> None:
    import matplotlib.pyplot as plt

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)

    tracks = sorted(result.tracks, key=lambda track: (track.start_time_ms, track.passage_id, track.track_id))
    figure = plt.figure(figsize=(13, 10.5))
    grid = figure.add_gridspec(3, 1, height_ratios=[1.5, 2.5, 1.3], hspace=0.44)
    activity_ax = figure.add_subplot(grid[0])
    zoom_ax = figure.add_subplot(grid[1])
    ici_ax = figure.add_subplot(grid[2])

    species = sorted({track.passage_species for track in tracks})
    colors = plt.cm.tab10.colors
    species_colors = {name: colors[index % len(colors)] for index, name in enumerate(species)}

    plot_activity_stack(activity_ax, tracks, species, species_colors)

    zoom_start_ms, zoom_end_ms = densest_time_window(tracks, zoom_window_sec * 1000)
    zoom_tracks = [
        track
        for track in tracks
        if any(zoom_start_ms <= chirp.time_ms <= zoom_end_ms for chirp in track.chirps)
    ]
    for y, track in enumerate(zoom_tracks, start=1):
        color = species_colors[track.passage_species]
        chirps = [chirp for chirp in track.chirps if zoom_start_ms <= chirp.time_ms <= zoom_end_ms]
        times_s = [(chirp.time_ms - zoom_start_ms) / 1000 for chirp in chirps]
        zoom_ax.scatter(times_s, [y] * len(chirps), color=color, s=24, alpha=0.86)
        if len(times_s) >= 2:
            zoom_ax.plot(times_s, [y] * len(times_s), color=color, linewidth=0.8, alpha=0.55)
        if track.suspicious_short_ici:
            zoom_ax.scatter(times_s, [y] * len(chirps), marker="x", s=32, color="black", zorder=4)

    zoom_ax.set_title(
        f"Densest {zoom_window_sec:g} s window: multi-track chirp raster "
        f"({zoom_start_ms / 3_600_000:.2f} h to {zoom_end_ms / 3_600_000:.2f} h)"
    )
    zoom_ax.set_xlabel("Seconds from zoom window start")
    zoom_ax.set_ylabel("Estimated track")
    zoom_ax.grid(True, alpha=0.25)
    if zoom_tracks:
        zoom_ax.set_ylim(0, len(zoom_tracks) + 1)
        zoom_ax.set_yticks(range(1, len(zoom_tracks) + 1))
        zoom_ax.set_yticklabels([short_track_label(track) for track in zoom_tracks], fontsize=7)
    ici_values = [
        float(delta)
        for track in tracks
        for delta in np.diff([chirp.time_ms for chirp in track.chirps])
        if delta > 0
    ]
    if ici_values:
        upper = max(180, min(250, max(ici_values)))
        ici_ax.hist(ici_values, bins=np.linspace(0, upper, 36), color="0.35", alpha=0.8)
    ici_ax.axvline(suspicious_short_ici_ms, color="red", linestyle="--", linewidth=1, label="short ICI threshold")
    ici_ax.set_title("Within-track ICI distribution")
    ici_ax.set_xlabel("ICI between consecutive chirps in one track (ms)")
    ici_ax.set_ylabel("Chirp interval count")
    ici_ax.grid(True, alpha=0.25)
    ici_ax.legend(loc="best", fontsize=8)

    figure.suptitle(
        f"Individual counting summary: {result.summary['n_individuals_estimated']} tracks, "
        f"{result.summary['n_passages_detected']} passages",
        fontsize=13,
        y=0.985,
    )
    figure.subplots_adjust(top=0.93, bottom=0.07, left=0.08, right=0.98)
    figure.savefig(output, dpi=140)
    plt.close(figure)


def plot_activity_stack(activity_ax, tracks: list, species: list[str], species_colors: dict[str, tuple]) -> None:
    activity_ax.set_title("Estimated simultaneous activity by species")
    activity_ax.set_xlabel("Time (h)")
    activity_ax.set_ylabel("Active tracks")
    activity_ax.grid(True, axis="x", alpha=0.25)
    if not tracks:
        return

    start = min(track.start_time_ms for track in tracks)
    end = max(track.end_time_ms for track in tracks)
    bin_ms = choose_activity_bin_ms(end - start)
    edges = np.arange(start, end + bin_ms, bin_ms)
    if edges.size < 2:
        edges = np.array([start, end + 1])
    centers_h = ((edges[:-1] + edges[1:]) / 2) / 3_600_000
    values = []
    for species_name in species:
        counts = np.zeros(edges.size - 1, dtype=float)
        for track in tracks:
            if track.passage_species != species_name:
                continue
            active = (edges[:-1] <= track.end_time_ms) & (edges[1:] >= track.start_time_ms)
            counts[active] += 1
        values.append(counts)

    activity_ax.stackplot(
        centers_h,
        values,
        labels=species,
        colors=[species_colors[name] for name in species],
        alpha=0.82,
    )
    if species:
        activity_ax.legend(loc="upper right", fontsize=8, title="Species")


def choose_activity_bin_ms(duration_ms: int) -> int:
    if duration_ms <= 10 * 60_000:
        return 5_000
    if duration_ms <= 2 * 3_600_000:
        return 60_000
    return 5 * 60_000


def short_track_label(track) -> str:
    species_code = "".join(part[:1] for part in track.passage_species.split()[:2]) or "?"
    return f"{track.track_id.replace('track-', 't')}/{species_code}/n{track.n_chirps}"


def densest_time_window(tracks: list, window_ms: float) -> tuple[float, float]:
    chirp_times = sorted(chirp.time_ms for track in tracks for chirp in track.chirps)
    if not chirp_times:
        return 0.0, max(1.0, window_ms)
    best_start = chirp_times[0]
    best_count = 0
    right = 0
    for left, start in enumerate(chirp_times):
        while right < len(chirp_times) and chirp_times[right] <= start + window_ms:
            right += 1
        count = right - left
        if count > best_count:
            best_count = count
            best_start = start
    return float(best_start), float(best_start + window_ms)


if __name__ == "__main__":
    main()
