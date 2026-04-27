import argparse
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.bat_preprocessing import add_frequency_columns, add_sequence_columns, load_bat_txt, remove_zero_artefacts


def format_hours(milliseconds: float) -> float:
    return milliseconds / 3_600_000


def summarize_zone(path: str, low_khz: float, high_khz: float, sequence_gap_ms: float) -> str:
    records, metadata = load_bat_txt(path)
    clean = remove_zero_artefacts(add_frequency_columns(records, metadata["bin_khz"]))
    clean = add_sequence_columns(clean, sequence_gap_ms, suffix="")
    mask = (clean["FME_kHz"] > low_khz) & (clean["FME_kHz"] < high_khz)
    zone = {key: value[mask] for key, value in clean.items()}
    sequences, sequence_counts = np.unique(zone["seq_id"], return_counts=True)
    snr = zone["SNR_dB"]
    fme = zone["FME_kHz"]
    time_ms = zone["time_ms"]
    duration_h = format_hours(float(time_ms.max() - time_ms.min()))
    top_order = np.argsort(sequence_counts)[::-1][:10]

    lines = [
        f"Analyse zone {low_khz:.1f}-{high_khz:.1f} kHz",
        f"Fichier              : {path}",
        f"Detections clean     : {clean['time_ms'].size}",
        f"Detections zone      : {time_ms.size} ({time_ms.size / clean['time_ms'].size:.2%})",
        f"FME mediane          : {np.median(fme):.2f} kHz",
        f"FME q10-q90          : {np.quantile(fme, 0.10):.2f}-{np.quantile(fme, 0.90):.2f} kHz",
        f"SNR median           : {np.median(snr):.1f} dB",
        f"SNR q10-q90          : {np.quantile(snr, 0.10):.1f}-{np.quantile(snr, 0.90):.1f} dB",
        f"Etalement temporel   : {duration_h:.2f} h",
        f"Premier timestamp    : {time_ms.min()} ms",
        f"Dernier timestamp    : {time_ms.max()} ms",
        f"Sequences touchees   : {sequences.size}",
        f"Detections/sequence  : median={np.median(sequence_counts):.1f}, max={sequence_counts.max()}",
        "",
        "Top sequences:",
    ]
    for seq_id, count in zip(sequences[top_order], sequence_counts[top_order]):
        seq_mask = zone["seq_id"] == seq_id
        seq_time = zone["time_ms"][seq_mask]
        seq_snr = zone["SNR_dB"][seq_mask]
        seq_fme = zone["FME_kHz"][seq_mask]
        lines.append(
            f"  seq={int(seq_id):5d} n={int(count):4d} "
            f"duration={seq_time.max() - seq_time.min():7.0f} ms "
            f"FME_med={np.median(seq_fme):6.2f} kHz "
            f"SNR_med={np.median(seq_snr):5.1f} dB"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse the weak 25 kHz FME mode in a DATA*.TXT file.")
    parser.add_argument("input", help="Input DATA*.TXT file")
    parser.add_argument("--low-khz", type=float, default=22.0, help="Lower FME bound")
    parser.add_argument("--high-khz", type=float, default=28.0, help="Upper FME bound")
    parser.add_argument("--sequence-gap-ms", type=float, default=100.0, help="Gap starting a new sequence")
    args = parser.parse_args()
    print(summarize_zone(args.input, args.low_khz, args.high_khz, args.sequence_gap_ms))


if __name__ == "__main__":
    main()
