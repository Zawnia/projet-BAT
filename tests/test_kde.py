"""
Test de validation : mean-shift sur KDE pour détecter le nombre de modes
dans la distribution FME de DATA00.TXT.

Objectif : vérifier que la méthode KDE + find_peaks détecte 2 ou 3 modes
cohérents avec la vérité visuelle (~37.5 et ~53 kHz, éventuellement ~25 kHz)
avant de refactorer species_clustering.py.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
from scipy.signal import find_peaks
from pathlib import Path

# ===========================================================================
# CHARGEMENT DES DONNÉES
# ===========================================================================
DATA_PATH = Path(__file__).parent.parent / "data" / "raw" / "DATA00.TXT"

FREQ_KHZ_ENREG = 200
LENFFT = 512
BIN_KHZ = FREQ_KHZ_ENREG / LENFFT

with open(DATA_PATH, "r") as f:
    lines = f.readlines()

start_idx = next(i for i, l in enumerate(lines) if l.strip() == "DATAASCII")
data_lines = lines[start_idx + 3:]

records = []
for line in data_lines:
    parts = line.strip().split()
    if len(parts) == 6:
        records.append([int(x) for x in parts])

df = pd.DataFrame(records, columns=["time_ms", "posFME", "posFI", "posFT", "posDUREE", "SNRdB"])
df["FME_kHz"] = df["posFME"] * BIN_KHZ

# Filtrage : artefacts + sociaux
mask_artefact = (df["posFME"] == 0) & (df["SNRdB"] == 0) & (df["posDUREE"] == 0)
df_clean = df[~mask_artefact].copy()
fme = df_clean[df_clean["FME_kHz"] > 18]["FME_kHz"].values

print(f"Détections analysées : {len(fme)}")
print(f"FME : min={fme.min():.1f}, max={fme.max():.1f}, median={np.median(fme):.1f} kHz\n")

# ===========================================================================
# TEST DE LA MÉTHODE KDE + FIND_PEAKS
# ===========================================================================
# On teste plusieurs combinaisons (bandwidth_method, prominence_ratio)
# pour voir la sensibilité aux paramètres.

bandwidth_methods = ["scott", "silverman"]
prominence_ratios = [0.05, 0.10]

grid = np.linspace(fme.min(), fme.max(), 1000)

fig, axes = plt.subplots(len(bandwidth_methods), len(prominence_ratios),
                         figsize=(14, 8), sharex=True)
fig.suptitle("Validation KDE + find_peaks — détection des modes FME", fontsize=13)

results = []

for i, bw in enumerate(bandwidth_methods):
    kde = gaussian_kde(fme, bw_method=bw)
    density = kde(grid)

    for j, prom_ratio in enumerate(prominence_ratios):
        prominence = density.max() * prom_ratio
        peaks, properties = find_peaks(density, prominence=prominence)
        peak_positions = grid[peaks]
        peak_heights = density[peaks]

        ax = axes[i, j]
        ax.hist(fme, bins=80, density=True, color="lightgray", alpha=0.6, label="Histogramme")
        ax.plot(grid, density, "k-", lw=1.5, label=f"KDE ({bw})")
        ax.plot(peak_positions, peak_heights, "rv", markersize=12, label=f"Pics ({len(peaks)})")
        for pos in peak_positions:
            ax.axvline(pos, color="red", linestyle="--", alpha=0.4)

        ax.set_title(f"bw='{bw}', prominence={prom_ratio*100:.0f}% du max → {len(peaks)} modes")
        ax.set_xlabel("FME (kHz)")
        ax.set_ylabel("Densité")
        ax.legend(fontsize=8)

        results.append({
            "bandwidth": bw,
            "prominence_ratio": prom_ratio,
            "n_peaks": len(peaks),
            "positions_kHz": np.round(peak_positions, 2).tolist(),
            "heights": np.round(peak_heights, 4).tolist(),
        })

plt.tight_layout()
plt.savefig("test_kde_validation.png", dpi=120)
plt.close()

# ===========================================================================
# RÉSUMÉ DES RÉSULTATS
# ===========================================================================
print("="*70)
print("RÉSULTATS — détection de modes par KDE + find_peaks")
print("="*70)
for r in results:
    print(f"\n  bw='{r['bandwidth']}', prominence={r['prominence_ratio']*100:.0f}% du max")
    print(f"    → {r['n_peaks']} modes détectés")
    print(f"    → positions (kHz) : {r['positions_kHz']}")
    print(f"    → hauteurs        : {r['heights']}")

print("\n" + "="*70)
print("CRITÈRE DE DÉCISION")
print("="*70)
print("  ✓ Refactor validé si : 2 ou 3 modes cohérents avec ~37.5 et ~53 kHz")
print("    (éventuellement ~25 kHz comme 3ème mode)")
print("  ✗ Refactor à reconsidérer si : >4 modes ou positions aberrantes")
print("\n→ Voir test_kde_validation.png pour inspection visuelle")