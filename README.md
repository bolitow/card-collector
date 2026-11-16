# Collections de cartes

Application web pour suivre ses collections de cartes à partir des listes officielles, gérer ses
achats et ses ventes, et partager sa collection sans montrer ses prix.
Réalisation du cahier des charges v2.0 du 15 novembre 2026.

| Document | Contenu |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Pile, hébergement, coûts, modèle d'IA, interprétations à confirmer |
| [docs/recette.md](docs/recette.md) | État de chaque critère d'acceptation, et ce qui reste à faire |
| [docs/exploitation.md](docs/exploitation.md) | Déploiement, sauvegardes, restauration, supervision |
| [docs/administration.md](docs/administration.md) | Importer une checklist, traiter la file de travail |
| [CHANGELOG.md](CHANGELOG.md) | Note de version |

## Lancer en local

```bash
docker compose up --build          # http://localhost:8000
docker compose exec api python -m scripts.seed_dev   # données de démonstration
```

Comptes de démonstration : `demo@example.org` et `admin@example.org`, mot de passe `demonstration`.
Les e-mails s'affichent dans les journaux de `worker` ; l'IA est simulée.

### Sans Docker

```bash
# Serveur (Python 3.13, uv, PostgreSQL 16 avec les extensions citext et unaccent)
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload      # API sur :8000
uv run python -m app.worker               # tâches de fond, dans un second terminal

# Interface (Node 22, pnpm)
cd web
pnpm install
pnpm dev                                  # http://localhost:5173, /api relayé vers :8000
```

## Tests

```bash
cd backend && uv run pytest        # 119 tests sur PostgreSQL : règles de gestion, cloisonnement, critères d'acceptation
cd web && pnpm test && pnpm build  # règles de recherche partagées avec le serveur, typage, compilation
cd e2e && npm install && npm run flows   # scénarios dans un navigateur de 390 px (serveur local + seed_dev)
```

## Organisation

```
backend/app/rules/      règles pures : codes, recherche, avancement, variantes
backend/app/services/   collections, achats, partage, photos, IA, import de checklist, comptes
backend/app/api/        routes /api/v1 ; schemas.py décrit toutes les entrées et sorties
backend/scripts/        reprise du prototype, données de démonstration, jeu d'essai de l'IA
web/src/screens/        un fichier par écran ; web/src/i18n/fr.ts porte tous les textes
shared/                 vecteurs de test communs au serveur et à l'interface
```

Le code cite les références du cahier des charges (RG-xx, F-xx, CA-xx) là où il les applique.
Après toute modification de `schemas.py` : `cd web && pnpm gen:api`.
