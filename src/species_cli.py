import argparse

import numpy as np

try:
    from .bat_preprocessing import preprocess_bat_file
    from .species_clustering import SpeciesGMM, label_passage_species, plot_gmm_fit
except ImportError:
    from bat_preprocessing import preprocess_bat_file
    from species_clustering import SpeciesGMM, label_passage_species, plot_gmm_fit


def clustering_report(model: SpeciesGMM, fme_khz: np.ndarray, stats: dict[str, int | float]) -> str:
    params = model.params
    labels = model.predict(fme_khz)
    counts = np.bincount(labels, minlength=int(params["K"]))
    lines = [
        "Passage species GMM clustering report",
        f"Raw detections       : {stats['n_raw']}",
        f"Artefacts removed   : {stats['n_artefacts']}",
        f"Clean detections     : {stats['n_clean']}",
        f"Echoes removed       : {stats['n_echoes']}",
        f"No-echo detections   : {stats['n_no_echo']}",
        f"Social calls removed : {stats['n_social']} (FME <= {stats['fme_min_khz']:.2f} kHz)",
        f"Clustered detections : {stats['n_filtered']}",
        f"Passages clean       : {stats['n_sequences']} (gap >= {stats['passage_gap_ms']:.1f} ms)",
        f"Passages no echo     : {stats['n_sequences_no_echo']}",
        f"Passages clustered   : {stats['n_passages_detected']}",
        f"FFT resolution       : {stats['bin_khz']:.6f} kHz/bin",
        f"Echo rule            : gap <= {stats['echo_gap_ms']:.1f} ms and |dFME| <= {stats['echo_fme_bins']:.1f} bins",
        f"K detection          : {params['K_detection_method']}",
        f"Selected K           : {params['K']}",
        f"KDE peaks            : {np.array2string(params['kde_peaks'], precision=3, separator=', ')} kHz",
        f"Thresholds           : {np.array2string(model.thresholds, precision=3, separator=', ')} kHz",
        "",
        "Passage clusters:",
    ]
    for label, count, mean, sigma, weight in zip(
        range(int(params["K"])),
        counts,
        params["means"],
        params["sigmas"],
        params["weights"],
    ):
        cluster_fme = fme_khz[labels == label]
        median = float(np.median(cluster_fme)) if cluster_fme.size else float("nan")
        passage_species = label_passage_species(median)
        lines.append(
            f"  {label}: n={count:5d} ({count / fme_khz.size:6.2%}) "
            f"median={median:7.3f} kHz mean={mean:7.3f} kHz "
            f"sigma={sigma:6.3f} kHz weight={weight:6.3f} "
            f"passage_species={passage_species}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster dominant passage species from 1D FME measurements.")
    parser.add_argument("input", help="Input DATA*.TXT file")
    parser.add_argument("-o", "--output", default="species_gmm_fit.png", help="Output plot path")
    parser.add_argument("--show", action="store_true", help="Show the plot interactively")
    parser.add_argument("--fme-min-khz", type=float, default=18.0, help="Minimum FME kept for clustering")
    parser.add_argument("--sequence-gap-ms", type=float, default=100.0, help="Gap starting a new acoustic passage")
    parser.add_argument("--echo-gap-ms", type=float, default=10.0, help="Maximum gap for echo detection")
    parser.add_argument("--echo-fme-bins", type=float, default=1.0, help="Maximum FME bin delta for echo detection")
    parser.add_argument("--bandwidth-method", choices=["scott", "silverman"], default="scott", help="KDE bandwidth rule")
    parser.add_argument("--bandwidth-scale", type=float, default=1.0, help="Multiplier applied to the KDE bandwidth")
    parser.add_argument("--peak-prominence-ratio", type=float, default=0.05, help="Minimum KDE peak prominence as a ratio of max density")
    parser.add_argument("--min-peak-distance-khz", type=float, default=None, help="Minimum distance between KDE peaks in kHz")
    parser.add_argument("--max-components", type=int, default=8, help="Maximum number of GMM components allowed")
    parser.add_argument("--n-init", type=int, default=10, help="Number of GMM initializations")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    preprocessing = preprocess_bat_file(
        args.input,
        fme_min_khz=args.fme_min_khz,
        sequence_gap_ms=args.sequence_gap_ms,
        echo_gap_ms=args.echo_gap_ms,
        echo_fme_bins=args.echo_fme_bins,
    )
    fme = preprocessing.fme_khz
    model = SpeciesGMM(
        bandwidth_method=args.bandwidth_method,
        bandwidth_scale=args.bandwidth_scale,
        peak_prominence_ratio=args.peak_prominence_ratio,
        min_peak_distance_khz=args.min_peak_distance_khz,
        max_components=args.max_components,
        n_init=args.n_init,
        random_state=args.random_state,
    ).fit(fme)
    print(clustering_report(model, fme, preprocessing.stats))

    ax = plot_gmm_fit(model, fme)
    ax.set_title(f"Species GMM fit - K={model.params['K']}")
    ax.figure.tight_layout()
    ax.figure.savefig(args.output, dpi=140)
    print(f"\nPlot saved           : {args.output}")
    if args.show:
        ax.figure.show()


if __name__ == "__main__":
    main()
