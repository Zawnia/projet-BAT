"""
Script principal : lance une simulation et valide vs DATA00 réel.
"""

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

from bat_simulator import (
    NightConfig,
    NightSimulator,
    OutputFormatter,
    SPECIES_DEFAULTS,
    BIN_TO_KHZ,
)


def load_real_data(path: str) -> pd.DataFrame:
    """Charge DATA00.TXT réel."""
    lines = open(path).readlines()
    start = None
    for i, l in enumerate(lines):
        if l.strip().startswith("DATAASCII"):
            start = i + 1
            break
    data = []
    for l in lines[start:]:
        l = l.strip()
        if l:
            parts = l.split()
            if len(parts) == 6:
                data.append([int(x) for x in parts])
    df = pd.DataFrame(
        data, columns=["time_ms", "posFME", "posFI", "posFT", "posDUREE", "SNRdB"]
    )
    # Clean
    df = df[(df["posFME"] > 0) & (df["SNRdB"] > 0) & (df["posDUREE"] > 0)]
    df["FME_kHz"] = df["posFME"] * BIN_TO_KHZ
    return df


def compare_distributions(real: pd.DataFrame, sim: pd.DataFrame, output_path: str):
    """Génère des plots comparatifs réel vs simulé."""
    # Filtrer artefacts du sim
    sim_clean = sim[(sim["posFME"] > 0) & (sim["SNRdB"] > 0)].copy()
    sim_clean["FME_kHz"] = sim_clean["posFME"] * BIN_TO_KHZ

    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    fig.suptitle("Validation : Réel vs Simulé", fontsize=14, fontweight="bold")

    # 1. FME
    ax = axes[0, 0]
    ax.hist(
        real["FME_kHz"],
        bins=80,
        density=True,
        alpha=0.6,
        color="steelblue",
        label="Réel",
    )
    ax.hist(
        sim_clean["FME_kHz"],
        bins=80,
        density=True,
        alpha=0.6,
        color="coral",
        label="Simulé",
    )
    ax.set_xlabel("FME (kHz)")
    ax.set_title("Distribution FME")
    ax.legend()

    # 2. SNR
    ax = axes[0, 1]
    ax.hist(
        real["SNRdB"],
        bins=range(19, 72),
        density=True,
        alpha=0.6,
        color="steelblue",
        label="Réel",
    )
    ax.hist(
        sim_clean["SNRdB"],
        bins=range(19, 72),
        density=True,
        alpha=0.6,
        color="coral",
        label="Simulé",
    )
    ax.set_xlabel("SNR (dB)")
    ax.set_title("Distribution SNR")
    ax.legend()

    # 3. Durée
    ax = axes[0, 2]
    ax.hist(
        real["posDUREE"],
        bins=range(1, 30),
        density=True,
        alpha=0.6,
        color="steelblue",
        label="Réel",
    )
    ax.hist(
        sim_clean["posDUREE"],
        bins=range(1, 30),
        density=True,
        alpha=0.6,
        color="coral",
        label="Simulé",
    )
    ax.set_xlabel("Durée (bins FFT)")
    ax.set_title("Distribution Durée")
    ax.legend()

    # 4. Gaps (log)
    real_gaps = real["time_ms"].diff().dropna()
    sim_gaps = sim_clean["time_ms"].diff().dropna()
    bins_log = np.logspace(0, 7, 80)
    ax = axes[1, 0]
    ax.hist(
        real_gaps[real_gaps > 0],
        bins=bins_log,
        density=True,
        alpha=0.6,
        color="steelblue",
        label="Réel",
    )
    ax.hist(
        sim_gaps[sim_gaps > 0],
        bins=bins_log,
        density=True,
        alpha=0.6,
        color="coral",
        label="Simulé",
    )
    ax.set_xscale("log")
    ax.set_xlabel("Gap (ms)")
    ax.set_title("Distribution gaps (log)")
    ax.legend()

    # 5. FI vs FT
    ax = axes[1, 1]
    ax.scatter(
        real["posFI"] * BIN_TO_KHZ,
        real["posFT"] * BIN_TO_KHZ,
        s=0.5,
        alpha=0.2,
        c="steelblue",
        label="Réel",
    )
    ax.scatter(
        sim_clean["posFI"] * BIN_TO_KHZ,
        sim_clean["posFT"] * BIN_TO_KHZ,
        s=0.5,
        alpha=0.2,
        c="coral",
        label="Simulé",
    )
    ax.plot([10, 100], [10, 100], "k--", alpha=0.3)
    ax.set_xlabel("FI (kHz)")
    ax.set_ylabel("FT (kHz)")
    ax.set_title("FI vs FT")
    ax.legend(markerscale=10)

    # 6. FME vs temps
    ax = axes[1, 2]
    t_real = real["time_ms"] / 3.6e6
    t_sim = sim_clean["time_ms"] / 3.6e6
    ax.scatter(t_real, real["FME_kHz"], s=0.3, alpha=0.2, c="steelblue", label="Réel")
    ax.scatter(t_sim, sim_clean["FME_kHz"], s=0.3, alpha=0.2, c="coral", label="Simulé")
    ax.set_xlabel("Temps (heures)")
    ax.set_ylabel("FME (kHz)")
    ax.set_title("FME vs Temps")
    ax.legend(markerscale=10)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    print(f"Saved comparison: {output_path}")


def print_summary_comparison(real: pd.DataFrame, sim: pd.DataFrame):
    """Affiche un résumé chiffré de la comparaison."""
    sim_clean = sim[(sim["posFME"] > 0) & (sim["SNRdB"] > 0)].copy()
    sim_clean["FME_kHz"] = sim_clean["posFME"] * BIN_TO_KHZ

    real_gaps = real["time_ms"].diff().dropna()
    sim_gaps = sim_clean["time_ms"].diff().dropna()

    print("\n" + "=" * 60)
    print("COMPARAISON RÉEL vs SIMULÉ")
    print("=" * 60)
    fmt = "  {:<25s} {:>10s} {:>10s}"
    print(fmt.format("Métrique", "Réel", "Simulé"))
    print("-" * 50)
    print(fmt.format("Nb détections (clean)", str(len(real)), str(len(sim_clean))))
    print(
        fmt.format(
            "FME mean (kHz)",
            f"{real['FME_kHz'].mean():.1f}",
            f"{sim_clean['FME_kHz'].mean():.1f}",
        )
    )
    print(
        fmt.format(
            "FME std (kHz)",
            f"{real['FME_kHz'].std():.1f}",
            f"{sim_clean['FME_kHz'].std():.1f}",
        )
    )
    print(
        fmt.format(
            "SNR median",
            f"{real['SNRdB'].median():.0f}",
            f"{sim_clean['SNRdB'].median():.0f}",
        )
    )
    print(
        fmt.format(
            "Durée median (bins)",
            f"{real['posDUREE'].median():.0f}",
            f"{sim_clean['posDUREE'].median():.0f}",
        )
    )
    print(
        fmt.format(
            "Gap median (ms)", f"{real_gaps.median():.0f}", f"{sim_gaps.median():.0f}"
        )
    )
    print(
        fmt.format("Gap mean (ms)", f"{real_gaps.mean():.0f}", f"{sim_gaps.mean():.0f}")
    )

    # Échos
    for label, df, gaps in [("Réel", real, real_gaps), ("Simulé", sim_clean, sim_gaps)]:
        echo_count = ((gaps <= 10) & (df["posFME"].diff().abs() <= 1)).sum()
        print(
            f"  Échos (gap<=10ms, ΔFME<=1) {label}: {echo_count} "
            f"({echo_count / len(df) * 100:.1f}%)"
        )


if __name__ == "__main__":
    config = NightConfig(
        duration_hours=11.0,
        specimens_per_species=[3, 2],
        seed=42,
    )

    real_path = os.path.join(SCRIPT_DIR, "data", "raw", "DATA00.TXT")
    sim_data_path = os.path.join(SCRIPT_DIR, "SIM_DATA.TXT")
    sim_gt_path = os.path.join(SCRIPT_DIR, "SIM_GROUND_TRUTH.csv")
    validation_path = os.path.join(SCRIPT_DIR, "validation.png")

    if os.path.exists(real_path):
        sim = NightSimulator(config, real_data_path=real_path)
    else:
        print(f"[Avertissement] {real_path} non trouvé — échos non calibrés")
        sim = NightSimulator(config)
    df_sim = sim.simulate()

    OutputFormatter.write_data_txt(df_sim, sim_data_path)
    OutputFormatter.write_ground_truth(df_sim, sim_gt_path)
    print("\nFichiers écrits: SIM_DATA.TXT + SIM_GROUND_TRUTH.csv")

    if os.path.exists(real_path):
        df_real = load_real_data(real_path)
        print_summary_comparison(df_real, df_sim)
        compare_distributions(df_real, df_sim, validation_path)
    else:
        print(f"[Avertissement] Validation impossible: {real_path} non trouvé")
