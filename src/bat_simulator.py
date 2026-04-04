"""
Simulateur de signaux acoustiques de chiroptères.
Génère des données synthétiques au format DATA00.TXT avec ground truth.

Architecture:
    SpeciesProfile  → distributions d'une espèce
    Specimen        → individu concret (FME fixe, pattern d'activité)
    SequenceGenerator → génère les séquences de cris d'un spécimen
    EchoInjector    → ajoute les échos réalistes
    NightSimulator  → orchestre la nuit entière, merge les flux
    OutputFormatter → écrit DATA00.TXT + ground truth CSV
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional
import json


# ─────────────────────────────────────────────
# Constantes capteur (calées sur le prototype)
# ─────────────────────────────────────────────
FREQ_KHZ = 200
LENFFT = 512
OVERLAP = 2
SNRMIN = 19
BIN_TO_KHZ = FREQ_KHZ / LENFFT  # 0.3906 kHz/bin


def khz_to_bin(khz: float) -> int:
    """Convertit kHz en bin FFT (arrondi entier, clippé 0-255 car uint8)."""
    return int(np.clip(round(khz / BIN_TO_KHZ), 0, 255))


def bin_to_khz(b: int) -> float:
    return b * BIN_TO_KHZ


# ─────────────────────────────────────────────
# SpeciesProfile
# ─────────────────────────────────────────────
@dataclass
class SpeciesProfile:
    """Distributions caractéristiques d'une espèce."""
    name: str
    # FME
    fme_mean_khz: float
    fme_std_khz: float
    # Offsets FI et FT par rapport à FME
    fi_offset_mean: float   # FI = FME + offset (positif = FI > FME)
    fi_offset_std: float
    ft_offset_mean: float   # FT = FME - offset (positif = FME > FT)
    ft_offset_std: float
    # Durée (en bins FFT)
    duree_mean: float
    duree_std: float
    # SNR
    snr_mean: float
    snr_std: float
    # Variabilité intra-spécimen (jitter FME d'un cri à l'autre)
    fme_jitter_std: float = 0.85

    def sample_specimen_fme(self, rng: np.random.Generator) -> float:
        """Tire la FME 'identité' d'un spécimen de cette espèce."""
        return rng.normal(self.fme_mean_khz, self.fme_std_khz)

    def sample_chirp(self, specimen_fme: float, rng: np.random.Generator) -> dict:
        """Génère les paramètres d'un cri pour un spécimen donné."""
        fme = specimen_fme + rng.normal(0, self.fme_jitter_std)
        fi = fme + abs(rng.normal(self.fi_offset_mean, self.fi_offset_std))
        ft = fme - abs(rng.normal(self.ft_offset_mean, self.ft_offset_std))
        # Durée : géométrique (median ~3, queue lourde)
        duree = rng.geometric(1.0 / self.duree_mean)
        duree = max(1, min(duree, 255))
        # SNR : exponentielle décalée depuis SNRMIN (skew right, median ~27)
        snr_raw = SNRMIN + rng.exponential(self.snr_mean - SNRMIN)
        snr = max(SNRMIN, min(255, int(round(snr_raw))))

        return {
            'posFME': khz_to_bin(fme),
            'posFI': khz_to_bin(fi),
            'posFT': khz_to_bin(ft),
            'posDUREE': duree,
            'SNRdB': snr,
        }


# Profils par défaut calibrés sur DATA00
SPECIES_DEFAULTS = {
    'group1_35_45': SpeciesProfile(
        name='Espèce A (~38 kHz)',
        fme_mean_khz=38.7, fme_std_khz=2.6,
        fi_offset_mean=7.4, fi_offset_std=13.1,
        ft_offset_mean=1.6, ft_offset_std=2.2,
        duree_mean=5.2, duree_std=5.5,
        snr_mean=32.1, snr_std=12.2,
        fme_jitter_std=0.85,
    ),
    'group2_50_58': SpeciesProfile(
        name='Espèce B (~53 kHz)',
        fme_mean_khz=53.0, fme_std_khz=2.4,
        fi_offset_mean=4.0, fi_offset_std=7.8,
        ft_offset_mean=1.3, ft_offset_std=2.9,
        duree_mean=4.4, duree_std=3.9,
        snr_mean=31.7, snr_std=10.6,
        fme_jitter_std=0.85,
    ),
}


# ─────────────────────────────────────────────
# Specimen
# ─────────────────────────────────────────────
@dataclass
class Specimen:
    """Un individu concret avec son identité acoustique."""
    specimen_id: int
    species_id: int
    species_profile: SpeciesProfile
    fme_khz: float  # FME identité (fixe pour cet individu)
    # Activité : liste de (start_ms, end_ms) pendant lesquels le spécimen est actif
    active_windows: List[tuple] = field(default_factory=list)


# ─────────────────────────────────────────────
# SequenceGenerator
# ─────────────────────────────────────────────
@dataclass
class SequenceGeneratorConfig:
    """Paramètres de génération des séquences."""
    # Nb cris par séquence (géométrique)
    n_cris_p: float = 0.45          # P(stop) → mean ≈ 1/p ≈ 2.2
    n_cris_min: int = 1
    n_cris_max: int = 90
    # Gaps intra-séquence hors échos (log-normal)
    intra_gap_mu: float = 2.7       # ln(15) ≈ 2.7 → median ~15ms
    intra_gap_sigma: float = 0.9
    intra_gap_min: float = 2.0      # ms
    intra_gap_max: float = 99.0     # ms (< seuil séquence)


class SequenceGenerator:
    """Génère les séquences de cris d'un spécimen."""

    def __init__(self, config: SequenceGeneratorConfig = None,
                 rng: np.random.Generator = None):
        self.config = config or SequenceGeneratorConfig()
        self.rng = rng or np.random.default_rng()

    def generate_sequence(self, specimen: Specimen, t_start_ms: int,
                          sequence_id: int) -> List[dict]:
        """Génère une séquence complète pour un spécimen à partir de t_start_ms."""
        cfg = self.config
        n_cris = self.rng.geometric(cfg.n_cris_p)
        n_cris = np.clip(n_cris, cfg.n_cris_min, cfg.n_cris_max)

        detections = []
        t = t_start_ms

        for i in range(n_cris):
            chirp = specimen.species_profile.sample_chirp(
                specimen.fme_khz, self.rng
            )
            chirp['time_ms'] = int(t)
            chirp['specimen_id'] = specimen.specimen_id
            chirp['species_id'] = specimen.species_id
            chirp['sequence_id'] = sequence_id
            chirp['is_echo'] = False
            detections.append(chirp)

            # Gap vers le prochain cri
            if i < n_cris - 1:
                gap = self.rng.lognormal(cfg.intra_gap_mu, cfg.intra_gap_sigma)
                gap = np.clip(gap, cfg.intra_gap_min, cfg.intra_gap_max)
                t += gap

        return detections


# ─────────────────────────────────────────────
# EchoInjector — data-driven
# ─────────────────────────────────────────────
@dataclass
class EchoConfig:
    """Paramètres d'injection des échos, calibrés empiriquement sur DATA00.

    Résultats de l'analyse des 2034 paires maître-écho :
    - Gap : 45.7% dans [2,4)ms, 29.3% dans [4,6)ms, reste [6,10)ms
    - FME delta : 40% = 0 bin, 60% = 1 bin
    - SNR drop dépend du SNR maître (proportionnel, pas additif) :
        master [19,25) → drop mean -0.93 std 2.77  (écho souvent ≈ maître)
        master [25,35) → drop mean  4.06 std 3.98
        master [35,50) → drop mean 19.53 std 5.20
        master [50,72) → drop mean 33.18 std 5.38
    - Durée ratio écho/maître : median 0.50, mean 0.72
    - Bursts : 78.3% = 1 écho, 16.9% = 2, 3.5% = 3, 1.3% = 4-5
    """
    echo_prob: float = 0.12

    # Distribution du nombre d'échos par burst (empirique)
    # Index = nb_échos - 1, valeurs = probabilités cumulées inversées
    burst_weights: tuple = (0.783, 0.169, 0.035, 0.009, 0.004)

    # Gap écho (ms) — mixture pondérée par buckets observés
    gap_bucket_weights: tuple = (0.457, 0.293, 0.118, 0.085, 0.047)
    gap_bucket_edges: tuple = (2.0, 4.0, 6.0, 8.0, 10.0, 10.5)

    # FME delta (bins)
    fme_delta_zero_prob: float = 0.401  # P(delta=0)

    # SNR drop : régression linéaire par morceaux sur le SNR maître
    # Modèle : drop = slope * master_SNR + intercept + N(0, residual_std)
    # Fit sur les 4 buckets observés : points (22, -0.93), (30, 4.06), (42.5, 19.53), (61, 33.18)
    snr_drop_slope: float = 0.87
    snr_drop_intercept: float = -20.5
    snr_drop_residual_std: float = 4.5

    # Durée : ratio écho/maître
    duree_ratio_mean: float = 0.72
    duree_ratio_std: float = 0.88
    duree_ratio_min: float = 0.1

    # FI delta (bins) — plus variable que FME/FT
    fi_delta_median: float = 4.0
    fi_delta_scale: float = 8.0  # exponentielle décalée

    # FT delta (bins)
    ft_delta_median: float = 1.0
    ft_delta_scale: float = 2.5


def _extract_echo_params_from_real(data_path: str) -> dict:
    """Analyse DATA00.TXT et retourne les constantes empiriques pour EchoConfig.

    Identifie les paires maître-écho (gap <= 10ms, ΔFME <= 1 bin)
    et calcule les statistiques de dégradation.

    Returns:
        dict avec les clés correspondant aux champs de EchoConfig.
    """
    lines = open(data_path).readlines()
    start = next(
        i + 1 for i, l in enumerate(lines)
        if l.strip().startswith('DATAASCII')
    )
    rows = []
    for l in lines[start:]:
        l = l.strip()
        if l:
            parts = l.split()
            if len(parts) == 6:
                rows.append([int(x) for x in parts])

    df = pd.DataFrame(
        rows,
        columns=['time_ms', 'posFME', 'posFI', 'posFT', 'posDUREE', 'SNRdB']
    )
    df = df[(df['posFME'] > 0) & (df['SNRdB'] > 0) & (df['posDUREE'] > 0)]
    df = df.sort_values('time_ms').reset_index(drop=True)

    df['gap_ms'] = df['time_ms'].diff()
    df['delta_FME'] = df['posFME'].diff().abs()

    # Paires maître-écho
    echo_mask = (
        (df['gap_ms'] <= 10) & (df['delta_FME'] <= 1) & df['gap_ms'].notna()
    )
    echo_idx = df.index[echo_mask]
    master_idx = echo_idx - 1

    master_snr = df.loc[master_idx, 'SNRdB'].values
    echo_snr = df.loc[echo_idx, 'SNRdB'].values
    master_duree = df.loc[master_idx, 'posDUREE'].values
    echo_duree = df.loc[echo_idx, 'posDUREE'].values
    gaps = df.loc[echo_idx, 'gap_ms'].values
    delta_fme = df.loc[echo_idx, 'posFME'].values - df.loc[master_idx, 'posFME'].values
    delta_fi = (df.loc[echo_idx, 'posFI'].values - df.loc[master_idx, 'posFI'].values)
    delta_ft = (df.loc[echo_idx, 'posFT'].values - df.loc[master_idx, 'posFT'].values)

    snr_drop = master_snr - echo_snr

    # --- SNR drop régression linéaire ---
    from numpy.polynomial.polynomial import polyfit
    coeffs = polyfit(master_snr, snr_drop, 1)  # [intercept, slope]
    residuals = snr_drop - (coeffs[0] + coeffs[1] * master_snr)
    residual_std = float(np.std(residuals))

    # --- Gap buckets ---
    edges = [2, 4, 6, 8, 10, 10.5]
    gap_weights = []
    for i in range(len(edges) - 1):
        gap_weights.append(((gaps >= edges[i]) & (gaps < edges[i + 1])).mean())
    # Normaliser au cas où gap < 2ms existe
    total = sum(gap_weights)
    gap_weights = [w / total for w in gap_weights] if total > 0 else gap_weights

    # --- Burst distribution ---
    bursts = []
    current = 0
    for is_e in echo_mask:
        if is_e:
            current += 1
        else:
            if current > 0:
                bursts.append(current)
            current = 0
    if current > 0:
        bursts.append(current)
    bursts = np.array(bursts)
    burst_w = []
    for n in range(1, 6):
        burst_w.append((bursts == n).sum())
    total_b = sum(burst_w)
    burst_w = [w / total_b for w in burst_w] if total_b > 0 else burst_w

    # --- Durée ratio ---
    with np.errstate(divide='ignore', invalid='ignore'):
        duree_ratio = echo_duree / master_duree
    valid = (duree_ratio > 0) & (duree_ratio < 10) & np.isfinite(duree_ratio)
    dr_mean = float(np.mean(duree_ratio[valid]))
    dr_std = float(np.std(duree_ratio[valid]))

    # --- FME delta prob ---
    fme_zero_prob = float((np.abs(delta_fme) == 0).mean())

    # --- FI / FT ---
    fi_abs = np.abs(delta_fi).astype(float)
    ft_abs = np.abs(delta_ft).astype(float)

    params = {
        'snr_drop_slope': float(coeffs[1]),
        'snr_drop_intercept': float(coeffs[0]),
        'snr_drop_residual_std': residual_std,
        'gap_bucket_weights': tuple(round(w, 3) for w in gap_weights),
        'gap_bucket_edges': tuple(float(e) for e in edges),
        'burst_weights': tuple(round(w, 3) for w in burst_w),
        'duree_ratio_mean': round(dr_mean, 3),
        'duree_ratio_std': round(dr_std, 3),
        'fme_delta_zero_prob': round(fme_zero_prob, 3),
        'fi_delta_median': float(np.median(fi_abs)),
        'fi_delta_scale': float(np.percentile(fi_abs, 75)),
        'ft_delta_median': float(np.median(ft_abs)),
        'ft_delta_scale': float(np.percentile(ft_abs, 75)),
        'n_pairs': len(echo_idx),
    }

    print(f"[EchoCalibration] Extracted from {len(echo_idx)} master-echo pairs:")
    for k, v in params.items():
        print(f"  {k}: {v}")

    return params


class EchoInjector:
    """Injecte des échos avec dégradation calibrée empiriquement.

    Modèle data-driven :
    - Le SNR de l'écho dépend du SNR du maître via une régression linéaire
      (les échos de signaux forts perdent plus de dB que ceux de signaux faibles)
    - La durée est un ratio du maître (median ~0.5, mean ~0.72)
    - Le gap, la FME delta, et la taille des bursts suivent les distributions
      mesurées sur les paires réelles
    - FI et FT ont des deltas indépendants (FI très variable, FT plus stable)
    """

    def __init__(self, config: EchoConfig = None,
                 rng: np.random.Generator = None):
        self.config = config or EchoConfig()
        self.rng = rng or np.random.default_rng()

    @classmethod
    def from_real_data(cls, data_path: str,
                       rng: np.random.Generator = None) -> 'EchoInjector':
        """Construit un EchoInjector calibré directement depuis DATA00.TXT."""
        params = _extract_echo_params_from_real(data_path)
        cfg = EchoConfig(
            burst_weights=params['burst_weights'],
            gap_bucket_weights=params['gap_bucket_weights'],
            gap_bucket_edges=params['gap_bucket_edges'],
            fme_delta_zero_prob=params['fme_delta_zero_prob'],
            snr_drop_slope=params['snr_drop_slope'],
            snr_drop_intercept=params['snr_drop_intercept'],
            snr_drop_residual_std=params['snr_drop_residual_std'],
            duree_ratio_mean=params['duree_ratio_mean'],
            duree_ratio_std=params['duree_ratio_std'],
            fi_delta_median=params['fi_delta_median'],
            fi_delta_scale=params['fi_delta_scale'],
            ft_delta_median=params['ft_delta_median'],
            ft_delta_scale=params['ft_delta_scale'],
        )
        return cls(config=cfg, rng=rng)

    def _sample_burst_size(self) -> int:
        """Tire le nombre d'échos dans un burst."""
        weights = np.array(self.config.burst_weights)
        weights = weights / weights.sum()
        return self.rng.choice(range(1, len(weights) + 1), p=weights)

    def _sample_gap(self) -> float:
        """Tire un gap écho depuis les buckets empiriques."""
        cfg = self.config
        weights = np.array(cfg.gap_bucket_weights)
        weights = weights / weights.sum()
        bucket_idx = self.rng.choice(len(weights), p=weights)
        lo = cfg.gap_bucket_edges[bucket_idx]
        hi = cfg.gap_bucket_edges[bucket_idx + 1]
        return self.rng.uniform(lo, hi)

    def _sample_snr_drop(self, master_snr: int) -> float:
        """Calcule le drop SNR à partir du modèle linéaire empirique."""
        cfg = self.config
        expected = cfg.snr_drop_slope * master_snr + cfg.snr_drop_intercept
        noise = self.rng.normal(0, cfg.snr_drop_residual_std)
        return expected + noise

    def _sample_duree(self, master_duree: int) -> int:
        """Tire la durée de l'écho comme ratio du maître."""
        cfg = self.config
        ratio = max(
            cfg.duree_ratio_min,
            self.rng.normal(cfg.duree_ratio_mean, cfg.duree_ratio_std)
        )
        return max(1, int(round(master_duree * ratio)))

    def _sample_fme_delta(self) -> int:
        """Tire le delta FME en bins (0 ou ±1)."""
        if self.rng.random() < self.config.fme_delta_zero_prob:
            return 0
        return self.rng.choice([-1, 1])

    def _sample_fi_delta(self) -> int:
        """Tire le delta FI — plus dispersé que FME."""
        cfg = self.config
        delta = self.rng.exponential(cfg.fi_delta_scale)
        sign = self.rng.choice([-1, 1])
        return int(round(sign * delta))

    def _sample_ft_delta(self) -> int:
        """Tire le delta FT — relativement stable."""
        cfg = self.config
        delta = self.rng.exponential(cfg.ft_delta_scale)
        sign = self.rng.choice([-1, 1])
        return int(round(sign * delta))

    def inject(self, detections: List[dict]) -> List[dict]:
        """Prend une liste de détections, retourne avec échos insérés."""
        cfg = self.config
        result = []

        for det in detections:
            result.append(det)

            if det['is_echo']:
                continue

            if self.rng.random() < cfg.echo_prob:
                n_echoes = self._sample_burst_size()
                t = det['time_ms']

                for e in range(n_echoes):
                    gap = self._sample_gap()
                    t += gap

                    snr_drop = self._sample_snr_drop(det['SNRdB'])
                    echo_snr = max(SNRMIN, min(255, int(det['SNRdB'] - snr_drop)))

                    # Si l'écho tombe sous le seuil de détection, on l'ignore
                    if echo_snr <= SNRMIN and snr_drop > 5:
                        break

                    fme_delta = self._sample_fme_delta()
                    fi_delta = self._sample_fi_delta()
                    ft_delta = self._sample_ft_delta()

                    echo = {
                        'time_ms': int(t),
                        'posFME': max(0, min(255, det['posFME'] + fme_delta)),
                        'posFI': max(0, min(255, det['posFI'] + fi_delta)),
                        'posFT': max(0, min(255, det['posFT'] + ft_delta)),
                        'posDUREE': self._sample_duree(det['posDUREE']),
                        'SNRdB': echo_snr,
                        'specimen_id': det['specimen_id'],
                        'species_id': det['species_id'],
                        'sequence_id': det['sequence_id'],
                        'is_echo': True,
                    }
                    result.append(echo)

        return result


# ─────────────────────────────────────────────
# NightSimulator
# ─────────────────────────────────────────────
@dataclass
class NightConfig:
    """Configuration globale de la simulation."""
    duration_hours: float = 11.0
    species_profiles: List[SpeciesProfile] = field(default_factory=list)
    specimens_per_species: List[int] = field(default_factory=list)
    # Gaps inter-séquence : mixture model
    #   short_frac% → lognormal(short_mu, short_sigma) : passages rapides
    #   (1-short_frac)% → lognormal(long_mu, long_sigma) : grands silences
    inter_seq_short_frac: float = 0.70
    inter_seq_short_mu: float = 5.14    # median ~170ms
    inter_seq_short_sigma: float = 0.4
    inter_seq_long_mu: float = 8.5      # median ~5s, queue lourde
    inter_seq_long_sigma: float = 1.5
    inter_seq_min: float = 101.0        # ms (> seuil séquence)
    # Artefacts
    artefact_rate: float = 0.05         # ~5% de fausses détections
    # Activité : fraction de la nuit où chaque spécimen est actif
    activity_fraction_mean: float = 0.12
    activity_fraction_std: float = 0.05
    # Seed
    seed: int = 42

    def __post_init__(self):
        if not self.species_profiles:
            self.species_profiles = [
                SPECIES_DEFAULTS['group1_35_45'],
                SPECIES_DEFAULTS['group2_50_58'],
            ]
        if not self.specimens_per_species:
            self.specimens_per_species = [3, 2]


class NightSimulator:
    """Orchestre la simulation d'une nuit entière."""

    def __init__(self, config: NightConfig = None,
                 real_data_path: Optional[str] = None):
        self.config = config or NightConfig()
        self.rng = np.random.default_rng(self.config.seed)
        self.seq_gen = SequenceGenerator(rng=self.rng)
        # Si un fichier réel est fourni, calibrer les échos dessus
        if real_data_path:
            self.echo_inj = EchoInjector.from_real_data(
                real_data_path, rng=self.rng
            )
        else:
            self.echo_inj = EchoInjector(rng=self.rng)

    def _create_specimens(self) -> List[Specimen]:
        """Instancie tous les spécimens avec leur FME et fenêtres d'activité."""
        cfg = self.config
        duration_ms = cfg.duration_hours * 3.6e6
        specimens = []
        specimen_id = 0

        for sp_idx, (profile, n_spec) in enumerate(
            zip(cfg.species_profiles, cfg.specimens_per_species)
        ):
            for _ in range(n_spec):
                fme = profile.sample_specimen_fme(self.rng)
                # Générer des fenêtres d'activité aléatoires
                frac = np.clip(
                    self.rng.normal(cfg.activity_fraction_mean,
                                    cfg.activity_fraction_std),
                    0.05, 0.8
                )
                windows = self._generate_activity_windows(
                    duration_ms, frac
                )
                specimens.append(Specimen(
                    specimen_id=specimen_id,
                    species_id=sp_idx,
                    species_profile=profile,
                    fme_khz=fme,
                    active_windows=windows,
                ))
                specimen_id += 1

        return specimens

    def _generate_activity_windows(self, duration_ms: float,
                                    fraction: float) -> List[tuple]:
        """Génère des créneaux d'activité couvrant ~fraction de la nuit."""
        windows = []
        total_active = 0
        target = duration_ms * fraction
        t = self.rng.uniform(0, duration_ms * 0.1)  # début décalé

        while total_active < target and t < duration_ms:
            # Durée d'un créneau actif : 2-30 min
            w_dur = self.rng.uniform(2 * 60_000, 30 * 60_000)
            w_dur = min(w_dur, target - total_active, duration_ms - t)
            windows.append((int(t), int(t + w_dur)))
            total_active += w_dur
            # Pause entre créneaux : 5-60 min
            pause = self.rng.uniform(5 * 60_000, 60 * 60_000)
            t += w_dur + pause

        return windows

    def _generate_specimen_detections(self, specimen: Specimen) -> List[dict]:
        """Génère toutes les détections d'un spécimen sur ses fenêtres actives."""
        cfg = self.config
        all_dets = []
        seq_id = 0

        for (win_start, win_end) in specimen.active_windows:
            t = win_start

            while t < win_end:
                # Générer une séquence
                seq_dets = self.seq_gen.generate_sequence(
                    specimen, int(t), seq_id
                )
                if seq_dets:
                    all_dets.extend(seq_dets)
                    t = seq_dets[-1]['time_ms']
                    seq_id += 1

                # Gap inter-séquence (mixture model)
                if self.rng.random() < cfg.inter_seq_short_frac:
                    gap = self.rng.lognormal(cfg.inter_seq_short_mu,
                                              cfg.inter_seq_short_sigma)
                else:
                    gap = self.rng.lognormal(cfg.inter_seq_long_mu,
                                              cfg.inter_seq_long_sigma)
                gap = max(gap, cfg.inter_seq_min)
                t += gap

        return all_dets

    def _generate_artefacts(self, duration_ms: float,
                             n_real: int) -> List[dict]:
        """Génère des artefacts (détections parasites FME=0)."""
        n_artefacts = int(n_real * self.config.artefact_rate)
        artefacts = []
        for _ in range(n_artefacts):
            artefacts.append({
                'time_ms': int(self.rng.uniform(0, duration_ms)),
                'posFME': 0,
                'posFI': 0,
                'posFT': 0,
                'posDUREE': 0,
                'SNRdB': 0,
                'specimen_id': -1,
                'species_id': -1,
                'sequence_id': -1,
                'is_echo': False,
            })
        return artefacts

    def simulate(self) -> pd.DataFrame:
        """Lance la simulation complète. Retourne un DataFrame trié par temps."""
        specimens = self._create_specimens()
        all_detections = []

        # Log des spécimens
        print(f"Simulation: {len(specimens)} spécimens")
        for s in specimens:
            print(f"  Spécimen {s.specimen_id} | espèce {s.species_id} "
                  f"({s.species_profile.name}) | FME={s.fme_khz:.1f} kHz | "
                  f"{len(s.active_windows)} fenêtres")

        # Générer les détections par spécimen
        for specimen in specimens:
            dets = self._generate_specimen_detections(specimen)
            dets = self.echo_inj.inject(dets)
            all_detections.extend(dets)
            print(f"  → Spécimen {specimen.specimen_id}: "
                  f"{len(dets)} détections générées")

        # Artefacts
        duration_ms = self.config.duration_hours * 3.6e6
        artefacts = self._generate_artefacts(duration_ms, len(all_detections))
        all_detections.extend(artefacts)
        print(f"  → {len(artefacts)} artefacts ajoutés")

        # Merge et tri temporel
        df = pd.DataFrame(all_detections)
        df = df.sort_values('time_ms').reset_index(drop=True)
        print(f"  Total: {len(df)} détections")

        return df


# ─────────────────────────────────────────────
# OutputFormatter
# ─────────────────────────────────────────────
class OutputFormatter:
    """Écrit les résultats aux formats DATA00 et ground truth."""

    @staticmethod
    def write_data_txt(df: pd.DataFrame, path: str):
        """Écrit au format DATA00.TXT compatible capteur."""
        cols_capteur = ['time_ms', 'posFME', 'posFI', 'posFT',
                        'posDUREE', 'SNRdB']
        n = len(df)

        with open(path, 'w') as f:
            f.write('DETECTDATA\r\n')
            f.write(f'FREQ_KHZ_ENREG {FREQ_KHZ}\r\n')
            f.write(f'LENFFT {LENFFT}\r\n')
            f.write(f'OVERLAP {OVERLAP}\r\n')
            f.write(f'SNRMIN {SNRMIN}\r\n')
            f.write(f'detectData_nbsig {n}\r\n')
            f.write(f'nbsig_detect {n}\r\n')
            f.write(f'temps_ms_fin_prec 0\r\n')
            f.write(f'RAW-ASCII 1\r\n')
            f.write('time_ms posFME posFI posFT posDUREE SNRdB\r\n')
            f.write('raw: uint32 uint8 uint8 uint8 uint8 uint8\r\n')
            f.write('\r\n')
            f.write('DATAASCII\r\n')

            for _, row in df[cols_capteur].iterrows():
                vals = [str(int(row[c])) for c in cols_capteur]
                f.write(' '.join(vals) + '\r\n')

    @staticmethod
    def write_ground_truth(df: pd.DataFrame, path: str):
        """Écrit le ground truth complet en CSV."""
        gt_cols = ['time_ms', 'posFME', 'posFI', 'posFT', 'posDUREE',
                   'SNRdB', 'specimen_id', 'species_id', 'sequence_id',
                   'is_echo']
        df[gt_cols].to_csv(path, index=False)

    @staticmethod
    def write_config(config: NightConfig, specimens: list, path: str):
        """Sauvegarde la config de simulation en JSON."""
        info = {
            'duration_hours': config.duration_hours,
            'seed': config.seed,
            'artefact_rate': config.artefact_rate,
            'species': [],
            'specimens': [],
        }
        for i, sp in enumerate(config.species_profiles):
            info['species'].append({
                'id': i,
                'name': sp.name,
                'fme_mean_khz': sp.fme_mean_khz,
                'fme_std_khz': sp.fme_std_khz,
            })
        for s in specimens:
            info['specimens'].append({
                'specimen_id': s.specimen_id,
                'species_id': s.species_id,
                'fme_khz': round(s.fme_khz, 2),
                'n_windows': len(s.active_windows),
            })
        with open(path, 'w') as f:
            json.dump(info, f, indent=2)
