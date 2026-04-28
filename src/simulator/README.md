# Simulateur acoustique chauves-souris

SPA frontend-only React + TypeScript pour composer des nuits acoustiques synthetiques et exporter le format capteur `DATA*.TXT`.

## Commandes

```bash
npm install
npm run dev
npm test
npm run build
```

## Principes

- Les clips sont les seules entites editees et sauvegardees.
- Les detections sont recalculees depuis les clips au preview/export.
- IndexedDB sauvegarde l'etat projet localement.
- L'export `scenario.TXT` reproduit l'en-tete CRLF observe dans `data/raw/DATA00.TXT`.
