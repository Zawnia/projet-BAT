# Guide d'utilisation BAT

Ce projet fournit deux analyses principales sur des fichiers capteur `DATA*.TXT` :

- clustering d'especes dominantes par passage acoustique ;
- estimation de pistes individuelles a l'interieur des passages.

Le simulateur peut produire des fichiers `.TXT` au format capteur. Ces fichiers doivent ensuite etre relus par les outils Python comme des donnees reelles : le simulateur ne contourne pas le preprocessing.

## Vocabulaire

Un **passage** est un bloc temporel dense de chirps, separe des autres blocs par un silence d'au moins `100 ms` par defaut. Un passage est observable et mecanique : il ne represente pas forcement un individu unique.

Une **track** est une piste individuelle inferee dans un passage. Elle correspond a une suite de chirps que le tracker estime compatibles en cadence d'echolocation et en FME.

L'**ICI** signifie *Inter-Call Interval*, ou intervalle inter-cris. Pour deux chirps consecutifs d'une meme track, c'est la difference de temps entre leurs instants de detection :

```text
ICI_i = time_ms(chirp_i) - time_ms(chirp_{i-1})
```

L'ICI s'exprime ici en millisecondes. Pour une track complete, `ici_median_ms` est la mediane des ICI successifs de cette track. Le tracker l'utilise comme approximation robuste de la cadence d'echolocation de l'individu : deux chirps sont plus probablement dans la meme track si leur ecart temporel est proche de l'ICI attendu et si leur FME reste proche.

Le clustering d'especes actuel attribue donc une espece dominante probable a des passages ou a des groupes de detections. Le comptage d'individus est l'etape qui tente de decomposer ces passages en pistes individuelles.

## Installation et validation

Depuis la racine du repo :

```powershell
uv run python -m unittest discover -s tests
uv run python -m py_compile src\bat_preprocessing.py src\species_clustering.py src\species_cli.py src\individual_counting.py src\individual_cli.py
```

Les donnees locales doivent etre placees dans `data/raw`, `data/simulated` ou `data/processed`. Ces dossiers ne sont pas versionnes, sauf leurs fichiers de structure.

## Clustering d'especes par passage

Commande minimale :

```powershell
uv run python -m src.species_cli data/raw/DATA00.TXT -o plots/clustering/species_gmm_fit.png
```

Cette commande :

- lit le fichier capteur ;
- supprime les artefacts nuls ;
- segmente les detections en passages temporels ;
- supprime les echos avec la strategie legacy `drop_later` ;
- filtre les appels sociaux sous `--fme-min-khz` ;
- ajuste un GMM 1D sur les FME restantes ;
- produit un rapport console et un graphique.

Options principales :

```powershell
uv run python -m src.species_cli data/raw/DATA00.TXT `
  --fme-min-khz 18 `
  --sequence-gap-ms 100 `
  --echo-gap-ms 10 `
  --echo-fme-bins 1 `
  --bandwidth-method scott `
  --bandwidth-scale 1.0 `
  --peak-prominence-ratio 0.05 `
  --max-components 8 `
  -o plots/clustering/species_gmm_fit.png
```

Champs importants du rapport :

- `Passages clean` : passages avant suppression des echos ;
- `Passages no echo` : passages apres suppression des echos ;
- `Passages clustered` : passages contenant des chirps gardes pour clustering ;
- `Selected K` : nombre de composantes GMM retenues ;
- `passage_species` : espece dominante probable du cluster, determinee par la FME mediane et les plages de reference.

Attention : ce pipeline ne compte pas les individus. Il resume les passages selon leur distribution FME dominante.

## Comptage d'individus

Commande minimale :

```powershell
uv run python -m src.individual_cli data/raw/DATA00.TXT
```

Cette commande :

- lit le fichier capteur avec le meme preprocessing commun ;
- utilise la strategie d'echo `best_snr`, qui garde le chirp au meilleur SNR dans un groupe d'echos ;
- construit des passages acoustiques ;
- separe prudemment les especes intra-passage si le passage contient assez de chirps ;
- applique un tracker glouton par paquet d'espece ;
- affiche les tracks individuelles estimees.

Options principales :

```powershell
uv run python -m src.individual_cli data/raw/DATA00.TXT `
  --fme-min-khz 18 `
  --passage-gap-ms 100 `
  --echo-gap-ms 10 `
  --echo-fme-bins 1 `
  --min-passage-chirps 3 `
  --min-chirps-for-kde 15 `
  --ici-tolerance-ratio 0.30 `
  --fme-tolerance-bins 2 `
  --track-expiry-n-ici 3 `
  --min-track-chirps 3 `
  --bootstrap-ici-ms 100 `
  --suspicious-short-ici-ms 45 `
  --tracks-csv data/processed/DATA00_tracks.csv `
  --report-output data/processed/DATA00_individual_report.txt `
  --plot-output plots/counting/DATA00_tracks.png `
  --plot-window-sec 30
```

Champs importants du rapport :

- `Passages detected` : nombre de passages detectes mecaniquement ;
- `Individuals estimated` : nombre de tracks retenues comme individus estimes ;
- `Suspicious short ICI` : nombre de tracks dont l'ICI median est anormalement court ;
- `n_chirps` : nombre de chirps rattaches a la track, utile pour juger sa fiabilite ;
- `fme_median` : FME mediane de la track ;
- `ici_median` : ICI median de la track.

Une track avec beaucoup de chirps est plus fiable qu'une track juste au-dessus du seuil `--min-track-chirps`.

Exports disponibles :

- `--tracks-csv` : export tabulaire des tracks estimees ;
- `--report-output` : sauvegarde le rapport console en `.txt` ;
- `--plot-output` : genere un PNG avec trois panneaux :
  - activite simultanee estimee sur toute la nuit, empilee par espece ;
  - zoom automatique sur la fenetre d'activite la plus dense, sous forme de raster multi-tracks ;
  - distribution de tous les ICI internes aux tracks avec le seuil `suspicious_short_ici_ms`.

Le plot le plus utile pour le rendu est generalement `DATA00_tracks.png`, parce qu'il relie trois niveaux de lecture : activite ecologique globale, exemple visuel de decomposition en tracks, et coherence physiologique des ICI.

## Workflow recommande pour un rendu

1. Lancer le clustering pour presenter les groupes d'especes dominants :

```powershell
uv run python -m src.species_cli data/raw/DATA00.TXT -o plots/clustering/DATA00_species_gmm.png
```

2. Lancer le comptage avec exports :

```powershell
uv run python -m src.individual_cli data/raw/DATA00.TXT `
  --tracks-csv data/processed/DATA00_tracks.csv `
  --report-output data/processed/DATA00_individual_report.txt `
  --plot-output plots/counting/DATA00_tracks.png `
  --plot-window-sec 30
```

3. Utiliser dans le rapport :

- `plots/clustering/DATA00_species_gmm.png` pour montrer la separation globale des frequences FME ;
- `plots/counting/DATA00_tracks.png` pour montrer la decomposition en tracks individuelles ;
- `data/processed/DATA00_tracks.csv` pour justifier les nombres avec les colonnes `n_chirps`, `fme_median_khz`, `ici_median_ms` et `suspicious_short_ici`.

## Parametres importants

`--passage-gap-ms` ou `--sequence-gap-ms` controle la segmentation temporelle. La valeur par defaut `100 ms` vient de l'hypothese initiale de separation entre passages acoustiques.

`--echo-gap-ms` et `--echo-fme-bins` definissent les echos : par defaut, deux detections consecutives sont compatibles echo si elles sont separees par au plus `10 ms` et `1 bin` de FME.

`--min-chirps-for-kde` evite de lancer une separation multimodale FME sur trop peu de points. En dessous de `15 chirps`, le passage est considere unimodal pour la separation d'espece intra-passage.

`--bootstrap-ici-ms` sert aux pistes naissantes : tant qu'une track n'a pas assez de chirps pour calculer son propre ICI, le tracker utilise cette cadence nominale.

`--suspicious-short-ici-ms` est un seuil d'alerte, pas une verite biologique figee. La valeur de depart `45 ms` doit etre calibree sur les donnees reelles, par exemple en inspectant la distribution des ICI sur `DATA00.TXT`.

`--plot-window-sec` controle la duree du zoom dense dans le PNG de comptage. Une valeur courte, par exemple `30`, donne une figure plus lisible pour l'oral qu'un zoom de plusieurs minutes.

`--tracks-csv`, `--report-output` et `--plot-output` creent automatiquement leurs dossiers de sortie si besoin.

## Limites connues

Le cas de deux individus parfaitement entrelaces a demi-ICI n'est pas corrige automatiquement en v1. Le tracker peut alors produire une piste artificielle avec un ICI trop court. Le rapport signale ce cas avec `suspicious_short_ici`.

La separation d'especes intra-passage par KDE est volontairement prudente. Sur des passages courts, elle bascule en unimodal pour eviter des pics instables.

Le clustering d'especes donne une espece dominante probable par cluster ou passage, pas une annotation exhaustive de tous les individus presents.
