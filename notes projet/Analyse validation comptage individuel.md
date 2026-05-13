# Analyse de performance du comptage individuel

Date du run : 11 mai 2026  
Dataset analyse : `test`  
Seed : `20260512`  
Commande :

```powershell
uv run python -m src.individual_validation_cli run --dataset test --n-replicates 100
```

## Donnees generees

Le banc de validation a genere un fichier capteur synthetique complet, puis l'a relu via le pipeline normal de preprocessing et de comptage. Le tracker n'a pas acces a la verite terrain.

Sorties principales :

- `data/simulated/DATA_DUMMY_test.TXT`
- `data/simulated/DATA_DUMMY_test_truth.csv`
- `data/processed/validation_test_metrics_by_scenario.csv`
- `data/processed/validation_test_summary_by_case.csv`
- `data/processed/validation_test_track_assignments.csv`
- `plots/counting/validation_test_count_error.png`
- `plots/counting/validation_test_exact_rate.png`
- `plots/counting/validation_test_expected_vs_detected.png`
- `plots/counting/validation_test_ici_sweep.png`
- `plots/counting/validation_test_fme_sweep.png`

Volume du test :

| Mesure | Valeur |
|---|---:|
| Scenarios simules | 1400 |
| Detections capteur simulees | 84 982 |
| Tracks detectees et assignees | 2713 |
| Scenarios evalues | 1400 |

Le temps d'execution observe pour le run complet est d'environ 40 secondes sur la machine locale. Le profilage preliminaire estimait environ 48 secondes pour 1000 scenarios, ce qui confirme que le banc de test est exploitable en pratique.

## Resultats globaux

| Metrique | Valeur |
|---|---:|
| Nombre moyen d'individus simules par scenario | 1.94 |
| Nombre moyen de tracks detectees par scenario | 1.94 |
| Biais moyen detecte - simule | -0.003 |
| MAE, erreur absolue moyenne | 1.951 |
| RMSE | 3.074 |
| Taux de comptage exact | 9.0 % |
| Taux de sous-comptage | 66.4 % |
| Taux de sur-comptage | 24.6 % |

Le biais moyen proche de zero ne signifie pas que le tracker est fiable. Il masque une compensation entre deux erreurs opposees :

- beaucoup de scenarios sont sous-comptes, souvent detectes a 0 track ;
- certains scenarios complexes, surtout avec plusieurs individus superposes, sont fortement sur-comptes.

La figure `validation_test_expected_vs_detected.png` illustre ce point : les points ne suivent pas proprement la diagonale attendue. Les scenarios avec 1 ou 2 individus sont souvent sous la diagonale, tandis que les scenarios avec 4 ou 5 individus peuvent exploser au-dessus.

## Resultats par type de scenario

| Type de scenario | N | Biais | MAE | Taux exact | Interpretation |
|---|---:|---:|---:|---:|---|
| `single_clean` | 100 | -1.00 | 1.00 | 0 % | Un individu propre est presque toujours perdu. |
| `strong_echoes` | 100 | -1.00 | 1.00 | 0 % | Meme echec que le cas propre, les echos n'expliquent pas seuls le probleme. |
| `filtered_low_noise` | 100 | -0.98 | 0.98 | 2 % | Le bruit bas est bien filtre, mais l'individu utile est souvent perdu. |
| `short_passages` | 100 | -2.00 | 2.00 | 0 % | Les passages courts sont volontairement non comptes avec `min_track_chirps=3`. |
| `same_species_distinct_ici` | 100 | -1.04 | 1.44 | 13 % | Deux individus de meme espece sont majoritairement fusionnes ou perdus. |
| `same_species_half_ici` | 100 | -0.42 | 1.40 | 21 % | Le cas entrelace est difficile, mais moins catastrophique que prevu. |
| `close_fme_and_ici` | 100 | -0.25 | 1.13 | 27 % | Meilleur cas relatif, mais encore insuffisant pour une validation forte. |
| `different_species_superposed` | 100 | +0.67 | 1.69 | 18 % | La separation par espece aide, mais cree aussi des sur-comptages. |
| `feeding_buzz` | 100 | +1.76 | 1.76 | 2 % | Les ICI tres courts provoquent presque toujours du sur-comptage. |
| `many_superposed` | 100 | +8.96 | 8.96 | 1 % | Gros echec : fragmentation massive des tracks en forte densite. |
| `ici_sweep` | 200 | -1.00 | 1.41 | 11.5 % | L'ecart d'ICI seul ne suffit pas a rendre la separation robuste. |
| `fme_sweep` | 200 | -1.38 | 1.58 | 9.5 % | La separation FME reste fragile, meme quand l'ecart augmente. |

La figure `validation_test_count_error.png` confirme que l'erreur absolue est elevee dans presque tous les cas. `many_superposed` domine l'echelle avec une MAE proche de 9, ce qui montre une fragmentation excessive quand plusieurs individus se chevauchent.

La figure `validation_test_exact_rate.png` montre que le meilleur taux exact reste faible : environ 27 % pour `close_fme_and_ici`. Les cas `single_clean`, `strong_echoes` et `short_passages` sont a 0 %.

## Analyse des sweeps

### Sweep ICI

La courbe `validation_test_ici_sweep.png` teste deux individus de meme espece avec un ecart d'ICI de 10 a 100 ms.

| Ecart ICI | Taux exact | MAE | Biais |
|---:|---:|---:|---:|
| 10 ms | 0 % | 1.80 | -0.80 |
| 20 ms | 20 % | 1.30 | -0.90 |
| 30 ms | 10 % | 1.20 | -1.00 |
| 40 ms | 0 % | 1.35 | -1.05 |
| 50 ms | 15 % | 1.35 | -1.05 |
| 60 ms | 20 % | 1.30 | -1.00 |
| 70 ms | 10 % | 1.45 | -1.15 |
| 80 ms | 10 % | 1.55 | -1.05 |
| 90 ms | 10 % | 1.50 | -1.10 |
| 100 ms | 20 % | 1.25 | -0.85 |

Conclusion : il n'y a pas de transition nette ou le tracker devient fiable quand l'ecart d'ICI augmente. Le biais reste negatif sur toute la plage, donc le tracker tend a sous-compter ces scenarios.

### Sweep FME

La courbe `validation_test_fme_sweep.png` teste deux individus de meme espece avec un ecart FME de 1 a 10 bins FFT.

| Ecart FME | Taux exact | MAE | Biais |
|---:|---:|---:|---:|
| 1 bin | 45 % | 0.80 | 0.00 |
| 2 bins | 10 % | 1.30 | -1.00 |
| 3 bins | 15 % | 1.25 | -0.95 |
| 4 bins | 5 % | 1.40 | -1.20 |
| 5 bins | 5 % | 1.80 | -1.80 |
| 6 bins | 5 % | 1.85 | -1.65 |
| 7 bins | 5 % | 1.70 | -1.50 |
| 8 bins | 0 % | 1.95 | -1.95 |
| 9 bins | 5 % | 1.85 | -1.85 |
| 10 bins | 0 % | 1.85 | -1.85 |

Conclusion : la separation FME n'est pas monotone. L'augmentation de l'ecart FME n'ameliore pas automatiquement la detection. Cela suggere que l'echec principal ne vient pas uniquement de la confusion frequentielle, mais aussi de la logique temporelle du tracker et de son initialisation.

## Diagnostic technique

Le resultat le plus important est l'echec du cas `single_clean`. Un scenario simple a un individu devrait etre le cas facile. Or le tracker detecte souvent 0 individu compte.

Cause probable : le tracker v1 utilise `bootstrap_ici_ms=100` pour les tracks naissantes. Beaucoup d'individus simules ont des ICI de transit autour de 130-240 ms. Apres le premier chirp, le deuxieme chirp arrive donc trop tard par rapport a l'ICI bootstrap attendu, la track expire ou un nouveau fragment est cree. Comme `min_track_chirps=3`, ces fragments courts ne sont pas comptes.

Cette hypothese est coherente avec :

- le sous-comptage massif des cas simples ;
- le taux exact nul sur `single_clean` et `strong_echoes` ;
- la fragmentation extreme de `many_superposed` ;
- le sur-comptage des `feeding_buzz`, ou les ICI courts creent au contraire trop de tracks compatibles ou trop de fragments comptes.

## Conclusion sur l'utilisabilite

En l'etat, le tracker v1 n'est pas defendable comme estimateur quantitatif fiable du nombre d'individus. Il peut rester utile comme outil exploratoire pour visualiser des pistes candidates, mais les resultats numeriques ne doivent pas etre presentes comme un comptage robuste.

La validation montre que :

- le banc de test fonctionne et produit des resultats exploitables statistiquement ;
- le tracker v1 echoue sur des cas simples, ce qui bloque son utilisation directe dans un rapport comme preuve de qualite ;
- les erreurs sont structurees, donc ameliorables : il ne s'agit pas seulement de bruit aleatoire ;
- le protocole dev/test est pertinent pour comparer objectivement une v2.

Pour le rapport, la conclusion honnete serait :

> Le banc de validation synthetique met en evidence les limites de la premiere version du tracker individuel. La version actuelle ne fournit pas encore un comptage fiable, mais l'outil de validation permet de quantifier precisement les erreurs, d'identifier les regimes d'echec et de comparer objectivement les ameliorations futures.

## Pistes d'amelioration prioritaires

1. Remplacer l'ICI bootstrap fixe par une initialisation multi-hypotheses.
   - Tester plusieurs ICI initiaux plausibles, par exemple 50, 100, 150, 200 et 250 ms.
   - Garder la piste qui maximise la coherence temporelle globale.

2. Retarder la decision de fermeture des tracks.
   - La v1 expire trop vite une track naissante si le deuxieme chirp ne correspond pas au bootstrap.
   - Une piste devrait survivre plusieurs hypotheses d'ICI tant qu'elle n'a pas assez de chirps.

3. Ajouter une phase de fusion des fragments.
   - Beaucoup d'erreurs semblent venir de fragments trop courts.
   - Fusionner deux fragments compatibles en FME et ICI pourrait reduire le sous-comptage et le sur-comptage.

4. Separer explicitement les regimes acoustiques.
   - Transit : ICI longs, risque de sous-comptage.
   - Feeding buzz : ICI courts, risque de sur-comptage.
   - La meme logique de tracking ne semble pas adaptee aux deux.

5. Utiliser le dataset `dev` pour calibrer les parametres.
   - Explorer `bootstrap_ici_ms`, `track_expiry_n_ici`, `ici_tolerance_ratio`, `fme_tolerance_bins`.
   - Ne valider la v2 finale que sur `test`.

6. Ameliorer l'evaluation avec un matching plus fin.
   - Le comptage par scenario suffit pour le rapport actuel.
   - Pour une v2, ajouter un score de purete de track : combien de chirps d'une track appartiennent au meme individu simule.

## Decision recommandee

Ne pas utiliser le comptage individuel v1 comme resultat final de qualite. Utiliser plutot cette validation pour justifier scientifiquement les limites de la v1 et motiver une v2.

Le banc de validation, lui, est utilisable et solide : il est reproductible, separe correctement simulation et detection, produit des intervalles d'incertitude, et met en evidence les zones d'echec du tracker.
