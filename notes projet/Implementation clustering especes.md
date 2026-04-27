# Implementation clustering especes

## Objectif

Remplacer le seuil fixe a 48 kHz de l'EDA par une separation automatique des groupes de chauves-souris a partir de la distribution 1D de FME.

L'implementation est separee en deux modules :

- `src/bat_preprocessing.py` : lecture et nettoyage des fichiers capteur `DATA*.TXT`.
- `src/species_clustering.py` : modele GMM 1D, reporting CLI et graphique.

## Pretraitement

Le module `bat_preprocessing.py` reprend la logique utile de `src/eda.py` avant clustering :

- lecture du bloc `DATAASCII`;
- extraction de `FREQ_KHZ_ENREG` et `LENFFT`;
- conversion des bins FFT en kHz avec `bin_khz = FREQ_KHZ_ENREG / LENFFT`;
- conversion de `posFME`, `posFI`, `posFT` en `FME_kHz`, `FI_kHz`, `FT_kHz`;
- suppression des artefacts ou `posFME = 0`, `SNR_dB = 0`, `duree_bins = 0`;
- tri par `time_ms`;
- calcul des gaps inter-detections;
- creation des sequences avec `gap >= 100 ms`;
- detection des echos avec `gap <= 10 ms` et `|delta FME| <= 1 bin`;
- suppression des echos;
- recalcul des sequences apres suppression des echos;
- filtre final des cris sociaux avec `FME <= 18 kHz`.

La fonction principale est :

```python
preprocess_bat_file(path: str) -> BatPreprocessingResult
```

Elle retourne :

- `fme_khz` : vecteur 1D pret pour le GMM;
- `detections` : dictionnaire de colonnes numpy apres nettoyage;
- `stats` : compteurs et parametres du pretraitement.

## Clustering GMM

Le module `species_clustering.py` contient la classe `SpeciesGMM`.

API principale :

```python
model = SpeciesGMM(k_max=6, n_init=10, random_state=42).fit(fme_khz)
labels = model.predict(fme_khz)
proba = model.predict_proba(fme_khz)
thresholds = model.thresholds
params = model.params
```

Le modele fitte un `GaussianMixture` sklearn pour chaque `K = 1..k_max`, calcule le BIC, puis garde le modele qui minimise le BIC.

Les composantes sont toujours exposees triees par moyenne FME croissante :

- labels `0..K-1`;
- moyennes;
- sigmas;
- poids;
- responsabilites soft;
- seuils entre composantes adjacentes.

Les seuils sont calcules numeriquement en minimisant la densite totale du melange entre deux moyennes consecutives avec `scipy.optimize.minimize_scalar`.

## CLI

Commande de base :

```bash
python src/species_clustering.py data/raw/DATA00.TXT --output species_gmm_fit.png
```

Options disponibles :

```bash
--fme-min-khz 18
--sequence-gap-ms 100
--echo-gap-ms 10
--echo-fme-bins 1
--k-max 6
--n-init 10
--random-state 42
--show
```

La CLI affiche dans la console :

- nombre de detections brutes;
- artefacts retires;
- detections clean;
- echos retires;
- detections apres suppression des echos;
- cris sociaux retires;
- detections envoyees au clustering;
- nombre de sequences avant/apres suppression des echos;
- resolution FFT;
- regle echo utilisee;
- `K` selectionne;
- courbe BIC;
- seuils GMM;
- details par cluster : effectif, pourcentage, moyenne, sigma, poids.

Elle sauvegarde aussi un graphique avec :

- histogramme normalise des FME;
- gaussiennes ponderees;
- densite totale du melange;
- lignes verticales aux seuils de separation.

## Validation locale

Validation syntaxique :

```bash
python3 -m py_compile src/bat_preprocessing.py src/species_clustering.py
```

Validation du pretraitement sur `data/raw/DATA00.TXT` :

- detections brutes : 14451;
- artefacts retires : 680;
- detections clean : 13771;
- echos retires : 2034;
- detections apres suppression des echos : 11737;
- cris sociaux retires : 247;
- detections envoyees au GMM : 11490;
- sequences clean : 5356;
- sequences apres suppression des echos : 5385;
- resolution FFT : 0.390625 kHz/bin.

Le fit GMM complet doit etre lance dans l'environnement projet declare par `pyproject.toml`, car l'environnement Python systeme WSL utilise pendant l'implementation n'avait pas les dependances compatibles.
