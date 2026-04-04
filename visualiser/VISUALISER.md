# Contexte Projet
Agis en tant que développeur Python expert en Data Science (Streamlit / Pandas / Plotly).
Je suis le Product Owner du "Projet BAT". Notre objectif est de développer un dashboard local en Streamlit pour analyser et comparer des données de détection d'écholocation de chauves-souris. 
Nous devons comparer visuellement un enregistrement réel (donnée terrain) et une donnée simulée générée par notre propre algorithme.

# Format des Données (Inputs)
Les fichiers d'entrée sont au format `.TXT`. Ils contiennent deux parties :
1. Un en-tête de métadonnées contenant notamment les clés `FREQ_KHZ_ENREG` (souvent 200) et `LENFFT` (souvent 512).
2. Un délimiteur strict nommé `DATAASCII`.
3. Les données brutes sous forme de tableau séparé par des espaces. Les colonnes sont dans cet ordre strict : `time_ms`, `posFME`, `posFI`, `posFT`, `posDUREE`, `SNRdB`.

# User Stories & Fonctionnalités attendues

## 1. Moteur de parsing (Core Engine)
- Le système doit lire le fichier `.TXT`, extraire les métadonnées dans un dictionnaire, puis charger les données numériques post-`DATAASCII` dans un DataFrame Pandas.
- **Règle métier vitale (Conversion Métrique) :** Les variables `posFME`, `posFI` et `posFT` sont des "bins" fréquentiels. Le système doit créer de nouvelles colonnes en kHz en appliquant cette formule : `fréquence_khz = posX * (FREQ_KHZ_ENREG / LENFFT)`.
- **Règle métier (Nettoyage) :** Les lignes où `posFME == 0` et `SNRdB == 0` sont des artefacts. Le système doit les filtrer automatiquement.

## 2. Interface Utilisateur (Streamlit)
- Créer une interface permettant d'importer (via Drag & Drop ou sélection locale) deux fichiers distincts : "Donnée Réelle" et "Donnée Simulée".
- Ajouter une barre latérale (Sidebar) avec des contrôles globaux :
  - Un curseur pour filtrer dynamiquement le seuil `SNRdB` minimum (de 19 à 80 dB).
  - Un curseur pour zoomer sur une fenêtre temporelle spécifique (en millisecondes).

## 3. Visualisation Interactive (Plotly)
- Afficher un ou deux graphiques (side-by-side ou superposés, propose la meilleure UX) permettant de comparer les deux jeux de données.
- **Axe X :** Temps d'enregistrement (`time_ms`).
- **Axe Y :** Fréquence en kHz (afficher principalement la `FME_khz`, c'est la "Fréquence d'Énergie Maximale").
- **Esthétique :** Les points affichés doivent être colorés selon une carte de chaleur (colormap 'Jet' ou 'Viridis') basée sur la valeur du `SNRdB`.
- **Interactivité :** Au survol de la souris (hover), l'utilisateur doit voir les valeurs exactes de temps, FME, FI, FT et SNR.

# Contraintes techniques
Ne te préoccupe pas des conversions binaires ou d'architecture logicielle complexe. Fais un code Streamlit propre, modulaire et documenté, centré sur la fluidité de la comparaison visuelle Pandas/Plotly. Propose-moi une première itération complète et exécutable du fichier `app.py`.