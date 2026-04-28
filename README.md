# Projet BAT

Outils d'exploration et de clustering pour des detections de chauves-souris a partir de fichiers `DATA*.TXT`.

## Structure

- `src/` : code Python reutilisable pour le preprocessing et le clustering.
- `webUI/` : interface locale HTML/JS pour charger un fichier et visualiser KDE/GMM.
- `tests/` : tests automatises. Les scripts exploratoires ne doivent pas etre mis ici.
- `experiments/` : essais et prototypes independants du pipeline principal.
- `scripts/` : scripts d'analyse ponctuels, utiles mais pas forcement integres a l'API.
- `notes projet/` : notes de reunion et documentation de travail.
- `data/` : donnees locales ignorees par Git.
- `plots/` : figures generees, ignorees par Git.

## Donnees

Les fichiers de donnees (`data/raw`, `data/simulated`, `data/processed`) restent locaux et ne sont pas versionnes. Garde uniquement les `.gitkeep` et le README du dossier `data` dans Git.

## Commandes utiles

```bash
python -m unittest tests.test_species_clustering
python -m src.species_cli data/raw/DATA00.TXT -o plots/clustering/species_gmm_fit.png
```

Sous WSL, utilise un environnement Python Linux compatible avec les versions du `pyproject.toml`. Le `.venv` actuel du projet est un environnement Windows et peut ne pas se lancer directement depuis WSL.
