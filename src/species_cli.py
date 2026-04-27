import argparse

import numpy as np

try:
    from .bat_preprocessing import preprocess_bat_file
    from .species_clustering import SpeciesGMM, plot_gmm_fit
except ImportError:
    from bat_preprocessing import preprocess_bat_file
    from species_clustering import SpeciesGMM, plot_gmm_fit


def clustering_report(model: SpeciesGMM, fme_khz: np.ndarray, stats: dict[str, int | float]) -> str:
    params = model.params
    labels = model.predict(fme_khz)
    counts = np.bincount(labels, minlength=int(params["K"]))
    lines = [
        "Species GMM clustering report",
        f"Raw detections       : {stats['n_raw']}",
        f"Artefacts removed   : {stats['n_artefacts']}",
        f"Clean detections     : {stats['n_clean']}",
        f"Echoes removed       : {stats['n_echoes']}",
        f"No-echo detections   : {stats['n_no_echo']}",
        f"Social calls removed : {stats['n_social']} (FME <= {stats['fme_min_khz']:.2f} kHz)",
        f"Clustered detections : {stats['n_filtered']}",
        f"Sequences clean      : {stats['n_sequences']} (gap >= {stats['sequence_gap_ms']:.1f} ms)",
        f"Sequences no echo    : {stats['n_sequences_no_echo']}",
        f"FFT resolution       : {stats['bin_khz']:.6f} kHz/bin",
        f"Echo rule            : gap <= {stats['echo_gap_ms']:.1f} ms and |dFME| <= {stats['echo_fme_bins']:.1f} bins",
        f"K detection          : {params['K_detection_method']}",
        f"Selected K           : {params['K']}",
        f"KDE peaks            : {np.array2string(params['kde_peaks'], precision=3, separator=', ')} kHz",
        f"Thresholds           : {np.array2string(model.thresholds, precision=3, separator=', ')} kHz",
        "",
        "Clusters:",
    ]
    for label, count, mean, sigma, weight in zip(
        range(int(params["K"])),
        counts,
        params["means"],
        params["sigmas"],
        params["weights"],
    ):
        lines.append(
            f"  {label}: n={count:5d} ({count / fme_khz.size:6.2%}) "
            f"mean={mean:7.3f} kHz sigma={sigma:6.3f} kHz weight={weight:6.3f}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cluster bat species from 1D FME measurements.")
    parser.add_argument("input", help="Input DATA*.TXT file")
    parser.add_argument("-o", "--output", default="species_gmm_fit.png", help="Output plot path")
    parser.add_argument("--show", action="store_true", help="Show the plot interactively")
    parser.add_argument("--fme-min-khz", type=float, default=18.0, help="Minimum FME kept for clustering")
    parser.add_argument("--sequence-gap-ms", type=float, default=100.0, help="Gap starting a new sequence")
    parser.add_argument("--echo-gap-ms", type=float, default=10.0, help="Maximum gap for echo detection")
    parser.add_argument("--echo-fme-bins", type=float, default=1.0, help="Maximum FME bin delta for echo detection")
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
    model = SpeciesGMM(n_init=args.n_init, random_state=args.random_state).fit(fme)
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
