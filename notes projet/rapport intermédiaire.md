# Rapport intermédiaire - Projet BAT

## 1. Introduction et objectif du projet

Le projet BAT vise à analyser des données acoustiques de chauves-souris produites par un capteur embarqué. Le capteur ne fournit pas directement un signal audio complet, mais une liste de détections déjà prétraitées : pour chaque cri détecté, on dispose notamment de son horodatage, de sa fréquence de maximum d'énergie (FME), de sa fréquence initiale (FI), de sa fréquence terminale (FT), de sa durée et de son rapport signal/bruit.

L'objectif général est double. D'abord, il faut identifier les grands groupes acoustiques présents dans un enregistrement, donc proposer une identification probable des espèces dominantes. Ensuite, il faut aller plus loin et essayer d'estimer le nombre d'individus présents dans les passages acoustiques. Ces deux problèmes sont liés, mais ils ne sont pas de même difficulté : séparer des espèces à partir de distributions de FME est relativement défendable ; compter des individus superposés à partir de quelques caractéristiques temporelles et fréquentielles est beaucoup plus fragile.

À ce stade intermédiaire, le projet a surtout permis de construire une chaîne d'analyse complète : lecture des fichiers capteur, nettoyage, clustering d'espèces, visualisation Web, simulateur de nuits synthétiques, premier tracker individuel et banc de validation statistique. Le livrable actuel n'est donc pas seulement un résultat final, mais une base expérimentale permettant de comprendre où les méthodes fonctionnent, où elles échouent, et quelles pistes sont prioritaires pour la suite.

## 2. Analyse du problème

Les fichiers `DATA*.TXT` contiennent un bloc d'en-tête puis une section `DATAASCII` avec six colonnes principales : temps en millisecondes, `posFME`, `posFI`, `posFT`, durée en fenêtres FFT et `SNRdB`. Les positions fréquentielles sont des bins FFT. Elles doivent donc être converties en kHz avec la résolution du capteur, ici typiquement `200 kHz / 512`, soit environ `0,390625 kHz/bin`.

La FME est la variable centrale du projet. Elle est plus stable que FI ou FT, moins dépendante de la forme exacte du cri, et elle donne une information forte sur l'espèce ou le groupe acoustique. Les premiers échanges avec le tuteur ont confirmé que la FME est aussi la feature la plus utile du point de vue naturaliste : un même spécimen ou une même espèce tend à produire une FME relativement stable dans un contexte comparable.

La difficulté vient du fait que le capteur ne donne pas directement des individus. Il donne des cris. Il faut donc reconstruire une structure à plusieurs niveaux :

- un cri est une détection élémentaire ;
- un passage est un bloc temporel dense de cris, séparé du reste par un silence ;
- une espèce probable est un groupe fréquentiel dans la distribution des FME ;
- un individu est une piste inférée, c'est-à-dire une suite de cris compatibles en temps et en fréquence.

Plusieurs phénomènes compliquent cette reconstruction. Les échos créent des détections parasites très proches du cri original. Les cris sociaux à basse fréquence ne doivent pas être mélangés avec les cris d'écholocation. Plusieurs individus peuvent passer en même temps, parfois de la même espèce, avec des FME très proches. Enfin, les données réelles ne fournissent pas de vérité terrain : sur un enregistrement de nuit, on ne sait pas combien d'individus étaient réellement présents à chaque instant. C'est pour cette raison que le simulateur et le banc de validation sont devenus des pièces importantes du projet.

## 3. Travail réalisé

### Prétraitement commun

La première étape a été de rendre la lecture des fichiers capteur fiable et réutilisable. Le module `src/bat_preprocessing.py` lit le bloc `DATAASCII`, extrait les métadonnées utiles, convertit les bins FFT en kHz, trie les détections par temps et retire les artefacts évidents.

Le preprocessing applique ensuite plusieurs règles :

- suppression des lignes nulles, typiquement `posFME = 0`, `SNR_dB = 0` et durée nulle ;
- segmentation temporelle des passages avec un seuil par défaut de `100 ms` ;
- détection des échos avec un écart temporel court, par défaut `10 ms`, et une FME très proche, par défaut `1 bin` ;
- suppression ou sélection des échos selon la stratégie utilisée ;
- filtrage des cris sociaux ou basses fréquences avec un seuil FME par défaut de `18 kHz`.

Ce preprocessing a été conçu comme un socle commun : le clustering espèces, le comptage individuel et le benchmark relisent tous les données en passant par cette logique. Cela évite d'avoir plusieurs interprétations contradictoires du même format capteur.

### Clustering des espèces

Le clustering espèces remplace l'idée initiale d'un seuil fixe autour de `48 kHz` par une méthode plus souple. L'approche actuelle est centrée sur la distribution 1D des FME. Le module `src/species_clustering.py` estime d'abord une densité KDE pour détecter les pics principaux, puis initialise un modèle de mélange gaussien 1D (GMM) à partir de ces pics.

Les composantes du GMM sont triées par FME croissante. Pour chaque cluster, le pipeline expose les moyennes, écarts-types, poids, effectifs et seuils de séparation. Les seuils sont calculés comme les minima de densité entre deux composantes voisines. Une règle simple d'étiquetage associe ensuite les FME médianes à des espèces probables, par exemple `Pipistrellus kuhlii`, `Pipistrellus pipistrellus`, `Pipistrellus pygmaeus`, `Eptesicus serotinus` ou `Nyctalus sp.`.

Le parti pris est volontairement prudent : le modèle ne prétend pas identifier parfaitement chaque individu ou chaque cri. Il fournit plutôt une lecture dominante et probable des groupes acoustiques présents dans l'enregistrement. C'est un résultat exploitable pour le rapport, à condition de le présenter comme une annotation probable fondée sur les plages de FME.

### Interface Web de clustering

Une interface locale dans `webUI/` permet de charger un fichier capteur et de visualiser rapidement le clustering. Elle reprend en JavaScript la logique de parsing, preprocessing, KDE et GMM. L'intérêt principal est exploratoire : on peut modifier les paramètres, observer la distribution des FME, voir les pics KDE, les composantes du mélange et les seuils.

Cette WebUI a joué un rôle important pour comprendre la sensibilité des résultats. Elle rend visible l'effet des seuils de filtrage, de la bande passante KDE ou du nombre de bins d'histogramme. Elle n'est pas encore présentée comme une application finale, mais comme un outil de diagnostic et de démonstration.

### Simulateur acoustique

Le simulateur situé dans `src/simulator/` est une application React/TypeScript frontend-only. Il permet de composer des scénarios ou des nuits synthétiques à partir de clips. Chaque clip représente une séquence, du bruit ou un extrait importé. Les détections ne sont pas stockées directement : elles sont recalculées au moment du preview ou de l'export à partir des paramètres du clip.

Le simulateur produit des fichiers `.TXT` au format capteur, avec un en-tête compatible avec les fichiers réels. Il peut aussi exporter une vérité terrain en CSV, contenant les identifiants d'individus, les espèces, les séquences et les marqueurs d'échos ou de bruit. Cela permet de tester les algorithmes sur des cas où l'on connaît la réponse attendue.

Les paramètres actuellement simulés incluent les espèces, les phases de vol (`transit`, `chasse`, `approche`, `feeding_buzz`), les ICI, les variations de FME, le SNR, les échos et le bruit basse fréquence. Cette richesse est utile, mais elle introduit aussi un risque : certains paramètres, notamment FI, sont encore trop randomisés par rapport aux retours reçus. Le simulateur doit donc être consolidé pour devenir un livrable plus propre et plus contrôlable.

### Comptage individuel glouton

Le comptage individuel est implémenté dans `src/individual_counting.py`. Il repose sur une logique en deux temps. D'abord, chaque passage peut être séparé en paquets d'espèce par clustering FME si le nombre de cris est suffisant. Ensuite, un tracker glouton construit des pistes individuelles dans chaque paquet.

Le tracker associe un nouveau cri à une piste ouverte si deux conditions sont respectées :

- l'écart temporel est compatible avec l'ICI attendu de la piste ;
- la FME reste proche du centre fréquentiel de la piste.

Quand une piste n'a pas encore assez de cris pour estimer son propre ICI, elle utilise un `bootstrap_ici_ms` par défaut. Les pistes trop courtes sont ignorées grâce à `min_track_chirps`. Le pipeline signale aussi les pistes dont l'ICI médian est anormalement court, car elles peuvent correspondre à une fusion ou à une erreur de tracking.

Ce choix glouton a été utile pour obtenir rapidement un prototype interprétable. Il permet de produire des tracks, des rapports, des CSV et des figures. En revanche, il prend des décisions locales trop tôt, ce qui explique une partie des échecs observés en validation.

### Benchmark de validation

Le benchmark de validation est implémenté dans `src/individual_validation.py` et `src/individual_validation_cli.py`. Il génère des datasets synthétiques reproductibles `dev` et `test`, écrit un fichier capteur `DATA_DUMMY_<dataset>.TXT`, écrit un oracle séparé en CSV, puis relit le `.TXT` via le pipeline normal. Le tracker n'a jamais accès à la vérité terrain pendant le comptage.

Les scénarios testés couvrent plusieurs cas : un individu propre, deux individus de même espèce avec ICI distincts, deux individus entrelacés à demi-ICI, espèces différentes superposées, nombreux individus superposés, échos forts, bruit basse fréquence filtré, passages courts, feeding buzz, ainsi que des sweeps sur l'écart d'ICI et l'écart de FME.

Un run complet sur le dataset `test` avec `100` réplicats a produit `1400` scénarios, environ `84 982` détections simulées et `2713` tracks assignées. Les résultats globaux montrent que le tracker v1 n'est pas encore fiable quantitativement :

| Métrique | Valeur observée |
|---|---:|
| Nombre moyen d'individus simulés par scénario | 1,94 |
| Nombre moyen de tracks détectées par scénario | 1,94 |
| Biais moyen détecté - simulé | -0,003 |
| MAE | 1,951 |
| RMSE | 3,074 |
| Taux de comptage exact | 9,0 % |
| Taux de sous-comptage | 66,4 % |
| Taux de sur-comptage | 24,6 % |

Le biais moyen proche de zéro est trompeur : il vient d'une compensation entre des sous-comptages massifs et des sur-comptages dans les cas complexes. Le cas le plus révélateur est `single_clean` : un individu propre devrait être facile à compter, mais il est souvent perdu. L'hypothèse principale est que l'ICI bootstrap de `100 ms` est trop rigide pour des individus simulés dont les ICI sont souvent autour de `130-240 ms`. Les pistes naissantes expirent ou fragmentent avant d'atteindre le nombre minimal de cris.

La conclusion intermédiaire est donc claire : le banc de validation est solide et utile, mais le tracker individuel v1 doit être présenté comme un prototype exploratoire, pas comme un estimateur fiable du nombre d'individus.

## 4. Questionnements, obstacles et solutions

Le premier questionnement a porté sur la segmentation temporelle. Le seuil de `100 ms` vient de l'idée qu'un grand silence sépare deux passages, mais ce seuil reste un compromis. Trop court, il fragmente une séquence ; trop long, il fusionne plusieurs passages. La solution actuelle est de garder ce seuil configurable et de le documenter comme une hypothèse de travail.

La gestion des échos a été un deuxième obstacle. Un écho ressemble à un vrai cri, mais arrive très peu de temps après avec une FME presque identique. Pour le clustering espèces, la stratégie historique consiste à supprimer la détection suivante dans un groupe d'échos. Pour le comptage individuel, une stratégie plus prudente garde le cri au meilleur SNR. Ce choix limite le risque de supprimer le vrai cri quand plusieurs détections très proches existent.

Le choix du nombre de clusters a aussi évolué. Un seuil fixe était trop simpliste, car les distributions de FME changent selon les fichiers. La combinaison KDE puis GMM permet de détecter automatiquement les pics principaux, tout en gardant une représentation statistique lisible. C'est un bon compromis pour un livrable intermédiaire : assez automatique pour être utile, assez simple pour être expliqué.

La séparation entre espèces et individus est le cœur du problème. Une FME stable aide à identifier une espèce, mais elle ne suffit pas à distinguer deux individus de la même espèce. Pour cette deuxième tâche, il faut exploiter la cadence temporelle des cris, donc l'ICI. La v1 du tracker utilise cette idée, mais elle reste trop locale et trop dépendante de ses paramètres initiaux.

Le benchmark a permis de transformer une impression qualitative en diagnostic quantifié. Au lieu de simplement constater que certains tracks semblent plausibles, on peut mesurer l'erreur par scénario, voir les régimes d'échec et comparer objectivement une future v2. C'est probablement l'avancée méthodologique la plus importante pour la suite du projet.

## 5. Livrables actuels

Les livrables actuels sont les suivants :

- un module de preprocessing commun dans `src/bat_preprocessing.py` ;
- un clustering espèces en Python dans `src/species_clustering.py` et une CLI associée ;
- une WebUI locale dans `webUI/` pour visualiser KDE, GMM, clusters et seuils ;
- un simulateur React/TypeScript dans `src/simulator/`, avec export capteur et vérité terrain ;
- un premier compteur individuel glouton dans `src/individual_counting.py` ;
- une CLI de comptage individuel capable de produire rapports, CSV et figures ;
- un banc de validation reproductible pour comparer scénarios simulés et tracks détectées ;
- des tests automatisés dans `tests/` couvrant le preprocessing, le clustering, le comptage et la validation.

Ces livrables ne sont pas tous au même niveau de maturité. Le clustering espèces et le preprocessing sont les parties les plus stables. Le simulateur est fonctionnel mais encore perfectible. Le comptage individuel est le bloc le plus expérimental : il existe, il produit des résultats, mais sa validation montre qu'il n'est pas encore défendable comme mesure finale fiable.

## 6. Limites actuelles

La principale limite est le comptage individuel. Le tracker v1 échoue sur des cas qui devraient être simples et fragmente fortement les cas de forte densité. Il peut donc servir à visualiser des pistes candidates, mais pas encore à annoncer un nombre d'individus avec confiance.

Plusieurs paramètres restent empiriques : seuil de passage, seuil d'écho, bande passante KDE, tolérance ICI, tolérance FME, durée de vie des pistes et ICI bootstrap. Ils sont configurables, mais ils ne sont pas encore justifiés par une calibration systématique sur des données indépendantes.

Le simulateur est utile pour tester, mais il doit devenir moins aléatoire sur certains aspects. Les retours reçus indiquent notamment qu'il faut réduire le hasard sur FI et rendre certains scénarios plus contrôlables. L'objectif n'est pas de supprimer toute variabilité, mais de séparer clairement ce qui relève d'un paramètre choisi, d'une variation biologique plausible et d'un bruit expérimental.

La bibliographie est également à consolider. Les références naturalistes fournies par Bertaux sont utiles pour comprendre les espèces, les plages de FME et les comportements acoustiques. Il manque encore des références algorithmiques sur le clustering, le tracking, l'association de pistes, les modèles de mélange ou les méthodes de validation.

Enfin, l'ensemble du projet garde encore une forme de POC. Les scripts fonctionnent, mais le rendu final devra davantage insister sur la clarté, la reproductibilité, la documentation des hypothèses et la qualité des figures.

## 7. Plan pour la suite

La priorité technique est d'explorer d'autres algorithmes pour le comptage individuel. La première piste est de remplacer l'ICI bootstrap fixe par une initialisation multi-hypothèses : au lieu de supposer immédiatement `100 ms`, le tracker pourrait maintenir plusieurs cadences plausibles, par exemple `50`, `100`, `150`, `200` et `250 ms`, puis conserver les pistes les plus cohérentes. Une autre piste est de fusionner les fragments compatibles après tracking, car beaucoup d'erreurs semblent venir de pistes interrompues trop tôt.

Il faudra aussi tester des approches moins gloutonnes. Le tracker actuel prend une décision dès qu'un cri arrive. Une version plus robuste pourrait construire un graphe de compatibilité entre cris, puis chercher des chemins cohérents, ou utiliser une association globale minimisant un coût temps/FME. On peut aussi séparer explicitement les régimes acoustiques : un passage de transit avec ICI longs ne devrait pas être traité comme un feeding buzz avec ICI très courts.

Le deuxième axe est la transformation des POC en livrables plus propres. Les commandes doivent être mieux documentées, les sorties plus lisibles, les figures sélectionnées pour le rapport, et les paramètres importants clairement justifiés. Le but est que le rendu ne donne pas l'impression d'une collection de prototypes, mais d'une démarche expérimentale structurée.

Le troisième axe est bibliographique. Il faut intégrer les références naturalistes fournies par Bertaux, notamment pour les espèces et les comportements acoustiques, puis compléter avec des références algorithmiques. Cette bibliographie devra soutenir les choix de FME, de segmentation, de clustering et de tracking.

Le quatrième axe concerne le simulateur. Il faudra intégrer les retours du professeur, notamment rendre FI moins randomisée et plus cohérente avec les espèces ou phases simulées. Il faudra aussi rendre les scénarios de test plus contrôlables : superposition, échos, bruit, ICI, FME et nombre d'individus doivent pouvoir être fixés proprement afin de produire des cas de validation reproductibles.

À court terme, la stratégie la plus défendable est donc de présenter le clustering espèces comme un résultat intermédiaire robuste, le simulateur et le benchmark comme des outils méthodologiques importants, et le comptage individuel comme une première version dont les limites sont déjà quantifiées. Ce positionnement est plus solide qu'une promesse de comptage fiable non démontrée.

