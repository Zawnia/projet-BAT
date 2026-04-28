# Experiments

Ce dossier sert aux approches exploratoires qui ne sont pas encore integrees au pipeline principal.

Regles simples :

- creer un sous-dossier par approche;
- ajouter un court `README.md` expliquant l'idee et comment lancer le code;
- eviter les imports implicites depuis un autre prototype;
- ecrire les sorties dans `plots/`, `outputs/` ou un dossier ignore par Git.

Le script `kde_validation.py` garde l'ancien test visuel KDE + pics. Il n'est pas dans `tests/` car il depend de donnees locales et genere une figure.
