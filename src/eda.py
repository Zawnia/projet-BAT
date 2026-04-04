"""
EDA — Signaux acoustiques chauves-souris (DATA00.TXT)
======================================================
Script pédagogique : chaque bloc est autonome et commenté.
On comprend POURQUOI on trace chaque chose avant de le tracer.

Structure :
  0. Chargement et conversion des unités
  1. Filtrage des artefacts
  2. Distribution FME  →  combien de groupes / espèces ?
  3. Distribution des gaps inter-détections  →  structure temporelle
  4. Séquençage (gap > seuil = nouvelle séquence)
  5. Détection des échos intra-séquence
  6. Stabilité FME intra-séquence  →  est-ce que la FME d'un individu est stable ?
  7. Scatter FI vs FT coloré par FME  →  forme du chirp en L
  8. FME au fil du temps  →  y a-t-il des changements d'activité ?
  9. Distribution SNR  →  qualité globale du capteur
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pathlib import Path

# ===========================================================================
# 0. CHARGEMENT ET CONVERSION
# ===========================================================================
# Le fichier a un header variable (lignes texte avant "DATAASCII").
# On saute tout jusqu'à "DATAASCII" puis on lit le CSV.

DATA_PATH = Path(__file__).parent.parent / "data" / "raw" / "DATA00.TXT"

FREQ_KHZ_ENREG = 200   # fréquence d'échantillonnage en kHz
LENFFT = 512            # taille FFT

# 1 bin FFT = FREQ_KHZ_ENREG / LENFFT kHz
BIN_KHZ = FREQ_KHZ_ENREG / LENFFT   # = 0.390625 kHz/bin

# --- lecture du fichier ---
with open(DATA_PATH, "r") as f:
    lines = f.readlines()

# Trouver la ligne "DATAASCII" et sauter les 2 lignes suivantes (header colonnes + types)
start_idx = next(i for i, l in enumerate(lines) if l.strip() == "DATAASCII")
# Après "DATAASCII" : ligne d'en-têtes colonnes, ligne de types, puis données
col_line = lines[start_idx + 1].strip().split()   # ['time_ms', 'posFME', ...]
# On ignore la ligne "raw: uint32 ..." (start_idx + 2)
data_lines = lines[start_idx + 3:]

# Parser manuellement (rapide et sans ambiguïté)
records = []
for line in data_lines:
    parts = line.strip().split()
    if len(parts) == 6:
        records.append([int(x) for x in parts])

df = pd.DataFrame(records, columns=["time_ms", "posFME", "posFI", "posFT", "posDUREE", "SNRdB"])

# Conversion bins → kHz
for col in ["posFME", "posFI", "posFT"]:
    df[col.replace("pos", "") + "_kHz"] = df[col] * BIN_KHZ

# Renommage pour clarté
df = df.rename(columns={"posDUREE": "duree_bins", "SNRdB": "SNR_dB"})

print(f"Détections chargées : {len(df)}")
print(df.head(10))
print(df.dtypes)

# ===========================================================================
# 1. FILTRAGE DES ARTEFACTS
# ===========================================================================
# Le capteur sort parfois des lignes avec tout à 0 (FME=0, SNR=0, durée=0).
# Ce sont des artefacts de détection → on les exclut avant toute analyse.
# POURQUOI : ces zéros biaiseraient toutes les distributions (fausse bosse à 0 kHz).

mask_artefact = (df["posFME"] == 0) & (df["SNR_dB"] == 0) & (df["duree_bins"] == 0)
n_artefacts = mask_artefact.sum()
print(f"\nArtefacts (tout à 0) : {n_artefacts} ({100*n_artefacts/len(df):.1f}%)")

df_clean = df[~mask_artefact].copy().reset_index(drop=True)
print(f"Détections clean : {len(df_clean)}")

# ===========================================================================
# 2. DISTRIBUTION FME
# ===========================================================================
# La FME (Fréquence de Max Énergie) est la feature la plus robuste du capteur.
# OBJECTIF : voir combien de groupes/espèces sont présents dans l'enregistrement.
# On s'attend à des pics distincts correspondant aux espèces (chaque espèce
# chasse à une FME caractéristique, stable selon Bertaux).

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("Distribution FME — identification des groupes", fontsize=13)

# --- Histogramme brut (tout) ---
ax = axes[0]
ax.hist(df["FME_kHz"], bins=80, color="steelblue", alpha=0.7, label="Tout (avec artefacts)")
ax.hist(df_clean["FME_kHz"], bins=80, color="darkorange", alpha=0.6, label="Clean")
ax.axvline(14, color="red", linestyle="--", label="Seuil social (~14 kHz)")
ax.set_xlabel("FME (kHz)")
ax.set_ylabel("Count")
ax.set_title("FME brute vs clean")
ax.legend()

# --- Zoom sur les groupes écholocation (FME > 18 kHz) ---
# On exclut aussi les cris sociaux (<18 kHz) qui ont passé le filtre embarqué
df_echo = df_clean[df_clean["FME_kHz"] > 18].copy()
n_social = (df_clean["FME_kHz"] <= 18).sum()
print(f"\nCris sociaux résiduels (<18 kHz) : {n_social}")

ax = axes[1]
# Colorier par groupe pour visualiser la séparation
grp1 = df_echo[df_echo["FME_kHz"] <= 48]
grp2 = df_echo[df_echo["FME_kHz"] > 48]
ax.hist(grp1["FME_kHz"], bins=60, color="steelblue", alpha=0.8, label=f"Grp1 35-48 kHz (n={len(grp1)})")
ax.hist(grp2["FME_kHz"], bins=30, color="darkorange", alpha=0.8, label=f"Grp2 >48 kHz (n={len(grp2)})")
ax.set_xlabel("FME (kHz)")
ax.set_ylabel("Count")
ax.set_title("Zoom écholocation — groupes FME")
ax.legend()

print(f"\nGroupe 1 (35-48 kHz) : {len(grp1)} détections")
print(f"  FME mean={grp1['FME_kHz'].mean():.1f}, std={grp1['FME_kHz'].std():.1f} kHz")
print(f"Groupe 2 (>48 kHz)   : {len(grp2)} détections")
print(f"  FME mean={grp2['FME_kHz'].mean():.1f}, std={grp2['FME_kHz'].std():.1f} kHz")

plt.tight_layout()
plt.savefig("plot_FME.png", dpi=120)
plt.close()
print("→ plot_FME.png sauvegardé")

# ===========================================================================
# 3. DISTRIBUTION DES GAPS INTER-DÉTECTIONS
# ===========================================================================
# Le gap = temps entre deux détections consécutives.
# OBJECTIF : comprendre la structure temporelle.
# On s'attend à une bimodalité :
#   - Pics à <10ms : échos (répétitions du même cri par rebond acoustique)
#   - Pics ~15-100ms : cris successifs du même individu (intra-séquence)
#   - Queue longue >100ms : pauses entre séquences (changement d'individu ?)

df_clean_sorted = df_clean.sort_values("time_ms").reset_index(drop=True)
df_clean_sorted["gap_ms"] = df_clean_sorted["time_ms"].diff()   # NaN pour la 1ère ligne

gaps = df_clean_sorted["gap_ms"].dropna()

fig, axes = plt.subplots(1, 3, figsize=(16, 5))
fig.suptitle("Distribution des gaps inter-détections", fontsize=13)

# --- Échelle log (vue globale) ---
ax = axes[0]
# np.log1p pour éviter log(0)
ax.hist(gaps, bins=200, color="salmon", alpha=0.8)
ax.set_xscale("log")
ax.axvline(10, color="red", linestyle="--", label="Seuil écho (~10ms)")
ax.axvline(100, color="black", linestyle="--", label="Seuil séquence (100ms)")
ax.set_xlabel("Gap (ms) — échelle log")
ax.set_ylabel("Count")
ax.set_title("Vue globale (log)")
ax.legend()

# --- Zoom 0-100ms : zone échos et intra-séquence ---
ax = axes[1]
gaps_intra = gaps[gaps <= 100]
ax.hist(gaps_intra, bins=100, color="green", alpha=0.8)
ax.axvline(5, color="red", linestyle="--", label="Écho strict (~5ms)")
ax.axvline(10, color="orange", linestyle="--", label="Écho relaxé (~10ms)")
ax.set_xlabel("Gap (ms)")
ax.set_ylabel("Count")
ax.set_title("Zoom 0-100ms (intra-séquence + échos)")
ax.legend()

# --- Zoom 0-500ms : voir la bimodalité écho / intra ---
ax = axes[2]
gaps_short = gaps[gaps <= 500]
ax.hist(gaps_short, bins=200, color="steelblue", alpha=0.8)
ax.axvline(10, color="red", linestyle="--", label="Seuil écho (~10ms)")
ax.axvline(100, color="black", linestyle="--", label="Seuil séquence (100ms)")
ax.set_xlabel("Gap (ms)")
ax.set_ylabel("Count")
ax.set_title("Zoom 0-500ms")
ax.legend()

# Stats
print(f"\nStats gaps (ms) :")
print(f"  Médiane : {gaps.median():.0f}")
print(f"  Mean    : {gaps.mean():.0f}")
print(f"  P95     : {gaps.quantile(0.95):.0f}")
print(f"  Gaps ≤10ms  : {(gaps <= 10).sum()} ({100*(gaps<=10).mean():.1f}%) → candidats échos")
print(f"  Gaps ≤100ms : {(gaps <= 100).sum()} ({100*(gaps<=100).mean():.1f}%)")
print(f"  Gaps >100ms : {(gaps > 100).sum()} → changements de séquence potentiels")

plt.tight_layout()
plt.savefig("plot_gaps.png", dpi=120)
plt.close()
print("→ plot_gaps.png sauvegardé")

# ===========================================================================
# 4. SÉQUENÇAGE
# ===========================================================================
# On définit une "séquence" comme un groupe de détections séparées par
# des gaps < SEUIL_SEQ_MS. Un gap ≥ seuil = début d'une nouvelle séquence.
# OBJECTIF : segmenter les ~13k détections en séquences cohérentes,
# chacune correspondant potentiellement à un individu qui passe.

SEUIL_SEQ_MS = 100   # ms — à justifier par l'EDA des gaps

df_clean_sorted["nouvelle_seq"] = (df_clean_sorted["gap_ms"] >= SEUIL_SEQ_MS) | df_clean_sorted["gap_ms"].isna()
df_clean_sorted["seq_id"] = df_clean_sorted["nouvelle_seq"].cumsum()

n_sequences = df_clean_sorted["seq_id"].nunique()
print(f"\nSéquences identifiées (seuil={SEUIL_SEQ_MS}ms) : {n_sequences}")

# Taille des séquences (nb de détections par séquence)
seq_sizes = df_clean_sorted.groupby("seq_id").size()
print(f"Taille séquence — médiane={seq_sizes.median():.0f}, mean={seq_sizes.mean():.1f}, max={seq_sizes.max()}")

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle(f"Séquençage (seuil {SEUIL_SEQ_MS}ms)", fontsize=13)

ax = axes[0]
# Cap à 30 pour lisibilité
seq_sizes_cap = seq_sizes.clip(upper=30)
ax.hist(seq_sizes_cap, bins=range(1, 32), color="purple", alpha=0.8, rwidth=0.85)
ax.set_xlabel("Nb détections / séquence (cap 30)")
ax.set_ylabel("Nb séquences")
ax.set_title("Distribution taille des séquences")

# Durée des séquences en ms
seq_duration = df_clean_sorted.groupby("seq_id")["time_ms"].agg(lambda x: x.max() - x.min())
ax = axes[1]
ax.hist(seq_duration[seq_duration > 0], bins=80, color="teal", alpha=0.8)
ax.set_xlabel("Durée séquence (ms)")
ax.set_ylabel("Nb séquences")
ax.set_title("Distribution durée des séquences")

plt.tight_layout()
plt.savefig("plot_sequences.png", dpi=120)
plt.close()
print("→ plot_sequences.png sauvegardé")

# ===========================================================================
# 5. DÉTECTION DES ÉCHOS
# ===========================================================================
# Un écho = répétition du même cri par rebond acoustique.
# Signature : gap très court (≤ 10ms) ET FME quasi-identique (ΔFME ≤ 1 bin).
# POURQUOI dédupliquer : les échos gonflent artificiellement le compte de cris,
# faussent les distributions de gaps, et parasitent le clustering.

SEUIL_ECHO_MS = 10      # gap ≤ 10ms
SEUIL_ECHO_BINS = 1     # |ΔFME| ≤ 1 bin

df_clean_sorted["delta_FME_bins"] = df_clean_sorted["posFME"].diff().abs()

mask_echo = (
    (df_clean_sorted["gap_ms"] <= SEUIL_ECHO_MS) &
    (df_clean_sorted["delta_FME_bins"] <= SEUIL_ECHO_BINS)
)
n_echos = mask_echo.sum()
print(f"\nÉchos détectés : {n_echos} ({100*n_echos/len(df_clean_sorted):.1f}%)")

df_no_echo = df_clean_sorted[~mask_echo].copy().reset_index(drop=True)
print(f"Détections après déduplication échos : {len(df_no_echo)}")

# Visualisation : gaps des échos vs gaps normaux
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("Identification des échos", fontsize=13)

ax = axes[0]
ax.scatter(
    df_clean_sorted.loc[~mask_echo, "gap_ms"].clip(upper=200),
    df_clean_sorted.loc[~mask_echo, "delta_FME_bins"].clip(upper=5),
    alpha=0.1, s=5, color="steelblue", label="Normal"
)
ax.scatter(
    df_clean_sorted.loc[mask_echo, "gap_ms"].clip(upper=200),
    df_clean_sorted.loc[mask_echo, "delta_FME_bins"].clip(upper=5),
    alpha=0.5, s=10, color="red", label="Écho"
)
ax.axvline(SEUIL_ECHO_MS, color="red", linestyle="--")
ax.axhline(SEUIL_ECHO_BINS, color="orange", linestyle="--")
ax.set_xlabel("Gap (ms, cap 200)")
ax.set_ylabel("|ΔFME| (bins, cap 5)")
ax.set_title("Gap vs ΔFME — zone écho en rouge")
ax.legend()

ax = axes[1]
# Distribution des gaps APRÈS suppression des échos
gaps_clean = df_no_echo["gap_ms"].dropna()
ax.hist(gaps_clean[gaps_clean <= 500], bins=150, color="salmon", alpha=0.8)
ax.axvline(100, color="black", linestyle="--", label="Seuil séquence")
ax.set_xlabel("Gap (ms)")
ax.set_ylabel("Count")
ax.set_title("Gaps après suppression échos (≤500ms)")
ax.legend()

plt.tight_layout()
plt.savefig("plot_echos.png", dpi=120)
plt.close()
print("→ plot_echos.png sauvegardé")

# ===========================================================================
# 6. STABILITÉ FME INTRA-SÉQUENCE
# ===========================================================================
# QUESTION : la FME est-elle stable au sein d'une séquence ?
# Si oui → on peut fiablement caractériser une séquence par sa FME moyenne.
# Si non → le clustering sera bruité.
# On calcule l'écart-type de la FME pour chaque séquence (séquences de n≥2 cris).

# Utiliser df_no_echo re-séquencé
df_no_echo["gap_ms2"] = df_no_echo["time_ms"].diff()
df_no_echo["nouvelle_seq2"] = (df_no_echo["gap_ms2"] >= SEUIL_SEQ_MS) | df_no_echo["gap_ms2"].isna()
df_no_echo["seq_id2"] = df_no_echo["nouvelle_seq2"].cumsum()

seq_fme_stats = df_no_echo.groupby("seq_id2")["FME_kHz"].agg(["mean", "std", "count"])
seq_fme_multi = seq_fme_stats[seq_fme_stats["count"] >= 2]

print(f"\nSéquences avec ≥2 cris (après dédupliq. échos) : {len(seq_fme_multi)}")
print(f"Std FME intra-séquence — médiane={seq_fme_multi['std'].median():.2f} kHz, "
      f"mean={seq_fme_multi['std'].mean():.2f} kHz")

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("Stabilité FME intra-séquence", fontsize=13)

ax = axes[0]
ax.hist(seq_fme_multi["std"].clip(upper=5), bins=60, color="goldenrod", alpha=0.8)
ax.axvline(BIN_KHZ, color="red", linestyle="--", label=f"1 bin = {BIN_KHZ:.2f} kHz")
ax.set_xlabel("Std FME intra-séquence (kHz, cap 5)")
ax.set_ylabel("Nb séquences")
ax.set_title("Dispersion FME au sein d'une séquence")
ax.legend()
# Interprétation : si la majorité des std < 1 kHz (~2 bins), la FME est stable
# → le clustering sur la FME moyenne par séquence sera fiable.

ax = axes[1]
ax.scatter(seq_fme_multi["mean"], seq_fme_multi["std"].clip(upper=5),
           alpha=0.3, s=10, color="goldenrod")
ax.set_xlabel("FME moyenne de la séquence (kHz)")
ax.set_ylabel("Std FME (kHz, cap 5)")
ax.set_title("Stabilité FME selon la fréquence")
# Chercher si un groupe est plus stable que l'autre

plt.tight_layout()
plt.savefig("plot_stabilite_FME.png", dpi=120)
plt.close()
print("→ plot_stabilite_FME.png sauvegardé")

# ===========================================================================
# 7. SCATTER FI vs FT coloré par FME — forme du chirp en L
# ===========================================================================
# Le chirp d'un chiroptère a une forme en L sur le spectrogramme f(t) :
#   FI (fréquence initiale, haute) → descente rapide → FT (fréquence terminale, basse)
# OBJECTIF : confirmer la structure FI > FME > FT et voir si les groupes
# se séparent aussi dans l'espace (FI, FT).
# C'est utile pour savoir si FI/FT apportent de l'info discriminante en plus de FME.

df_echo_only = df_clean_sorted[df_clean_sorted["FME_kHz"] > 18]   # sans sociaux

fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle("Forme du chirp : FI vs FT, coloré par FME", fontsize=13)

ax = axes[0]
sc = ax.scatter(df_echo_only["FI_kHz"], df_echo_only["FT_kHz"],
                c=df_echo_only["FME_kHz"], cmap="plasma",
                alpha=0.2, s=5, vmin=30, vmax=65)
ax.plot([0, 110], [0, 110], "k--", alpha=0.3, label="FI=FT")
ax.set_xlabel("FI (kHz)")
ax.set_ylabel("FT (kHz)")
ax.set_title("FI vs FT (couleur = FME)")
plt.colorbar(sc, ax=ax, label="FME (kHz)")
ax.legend()
# On s'attend à FT < FI (le cri descend) → points sous la diagonale
# Deux nuages distincts = deux groupes d'espèces

ax = axes[1]
# FME vs FT : corrélation attendue forte
sc2 = ax.scatter(df_echo_only["FME_kHz"], df_echo_only["FT_kHz"],
                 c=df_echo_only["FI_kHz"], cmap="viridis",
                 alpha=0.2, s=5)
ax.set_xlabel("FME (kHz)")
ax.set_ylabel("FT (kHz)")
ax.set_title("FME vs FT (couleur = FI)")
plt.colorbar(sc2, ax=ax, label="FI (kHz)")

# Corrélations
corr_FME_FT = df_echo_only["FME_kHz"].corr(df_echo_only["FT_kHz"])
corr_FME_FI = df_echo_only["FME_kHz"].corr(df_echo_only["FI_kHz"])
print(f"\nCorrélations (données écholocation) :")
print(f"  FME–FT : {corr_FME_FT:.3f}")
print(f"  FME–FI : {corr_FME_FI:.3f}")

plt.tight_layout()
plt.savefig("plot_chirp_shape.png", dpi=120)
plt.close()
print("→ plot_chirp_shape.png sauvegardé")

# ===========================================================================
# 8. FME AU FIL DU TEMPS
# ===========================================================================
# OBJECTIF : voir si l'activité change au cours de la nuit.
# Est-ce qu'un groupe apparaît seulement en début de nuit ? Est-ce qu'il y a
# des pauses ? Ça donne du contexte pour interpréter les séquences.

fig, ax = plt.subplots(figsize=(14, 5))
df_plot = df_clean_sorted[df_clean_sorted["FME_kHz"] > 18]
sc = ax.scatter(
    df_plot["time_ms"] / 3_600_000,   # conversion ms → heures
    df_plot["FME_kHz"],
    c=df_plot["SNR_dB"], cmap="YlOrRd",
    alpha=0.2, s=4, vmin=19, vmax=65
)
plt.colorbar(sc, ax=ax, label="SNR (dB)")
ax.set_xlabel("Temps (heures)")
ax.set_ylabel("FME (kHz)")
ax.set_title("FME au fil du temps — couleur = SNR")
# Lecture : chaque point = une détection. Les "bandes" horizontales = espèces.
# Les zones vides = silences (pas d'activité ou pas dans le champ du capteur).
plt.tight_layout()
plt.savefig("plot_FME_temps.png", dpi=120)
plt.close()
print("→ plot_FME_temps.png sauvegardé")

# ===========================================================================
# 9. DISTRIBUTION SNR
# ===========================================================================
# Le SNR (rapport signal/bruit) indique la qualité de chaque détection.
# OBJECTIF : comprendre la dynamique du capteur et décider d'un éventuel
# seuil de qualité (ex: ne garder que SNR > X pour le clustering).
# Le capteur a un min théorique de 19 dB.

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("Distribution SNR", fontsize=13)

ax = axes[0]
ax.hist(df_clean["SNR_dB"], bins=60, color="teal", alpha=0.8)
ax.axvline(19, color="red", linestyle="--", label="Min capteur (19 dB)")
ax.set_xlabel("SNR (dB)")
ax.set_ylabel("Count")
ax.set_title("Distribution globale du SNR")
ax.legend()

ax = axes[1]
# SNR selon groupe FME : est-ce qu'un groupe est mieux détecté ?
df_g1 = df_clean[(df_clean["FME_kHz"] > 18) & (df_clean["FME_kHz"] <= 48)]
df_g2 = df_clean[df_clean["FME_kHz"] > 48]
ax.hist(df_g1["SNR_dB"], bins=40, alpha=0.6, color="steelblue", label="Grp1 (35-48 kHz)", density=True)
ax.hist(df_g2["SNR_dB"], bins=40, alpha=0.6, color="darkorange", label="Grp2 (>48 kHz)", density=True)
ax.set_xlabel("SNR (dB)")
ax.set_ylabel("Densité")
ax.set_title("SNR par groupe FME")
ax.legend()

print(f"\nSNR global — mean={df_clean['SNR_dB'].mean():.1f}, "
      f"median={df_clean['SNR_dB'].median():.1f}, "
      f"std={df_clean['SNR_dB'].std():.1f} dB")

plt.tight_layout()
plt.savefig("plot_SNR.png", dpi=120)
plt.close()
print("→ plot_SNR.png sauvegardé")

# ===========================================================================
# RÉSUMÉ FINAL
# ===========================================================================
print("\n" + "="*60)
print("RÉSUMÉ EDA")
print("="*60)
print(f"Détections totales       : {len(df)}")
print(f"Artefacts filtrés        : {n_artefacts}")
print(f"Cris sociaux (<18 kHz)   : {n_social}")
print(f"Échos filtrés            : {n_echos}")
print(f"Détections exploitables  : {len(df_no_echo)}")
print(f"Séquences identifiées    : {df_no_echo['seq_id2'].nunique()}")
print(f"Résolution FFT           : {BIN_KHZ:.4f} kHz/bin")
print(f"Groupes FME : Grp1 (35-48kHz) = {len(grp1)}, Grp2 (>48kHz) = {len(grp2)}")
print("="*60)