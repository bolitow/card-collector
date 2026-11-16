# Note de version

## 0.1.0 — 16 novembre 2026

Première livraison. Le périmètre visé est la V1 de la section 14. L'état détaillé, critère par
critère, est dans [docs/recette.md](docs/recette.md).

### Livré

- Dossier d'architecture : pile, hébergement en région Paris, coûts pour 100, 1 000 et 10 000
  utilisateurs, choix du modèle d'IA.
- Comptes : inscription, connexion par mot de passe ou par lien, vérification de l'adresse, mot de
  passe oublié, sessions, double authentification, paramètres, export des données, suppression.
- Catalogue commun : parcours, fiche d'une série, demande d'ajout, collection personnelle.
- Tous les écrans du prototype : mes collections, collection, fiche d'une carte, parallèles, ajout par
  photo, achats, ventes, bilan, recherche globale, cartes isolées.
- Partage : profil public, lien secret par collection, options, aperçu, signalement.
- Administration : import d'une checklist en quatre étapes, mise à jour d'une série publiée avec
  comparaison, file de travail, utilisateurs, tableau de bord, journal.
- IA : lecture d'une photo et import d'une checklist, avec quotas, journal et repli manuel.
- Script de reprise du prototype, rejouable, avec contrôle des totaux.
- Projets de conditions d'utilisation, de politique de confidentialité et de mentions légales.

### Ajouts au cahier des charges

Chacun est signalé « Ajout » dans le code et se retire sans toucher au reste.

- « Copier les manquantes » propose aussi le format compact (`1-12, 15, 18-20`), que l'import de
  liste relit.
- Sur une collection partagée, un collectionneur connecté compare avec la sienne : les cartes qui
  lui manquent, et les siennes parmi les manquantes affichées. Aucun double, aucune messagerie.
- « Moi aussi » sur une demande de série : évite les doublons et classe la file de travail.
- Depuis la fiche d'une carte, toutes les cartes du joueur dans le catalogue.
- À la publication d'une série, les achats saisis avec ce nom en texte libre s'y rattachent.

### Pas encore fait

- Connexion avec Google et Apple (F-28).
- Écrans d'administration pour les cartes recherchées éditoriales, les parallèles officiels, la
  fusion de références, les univers et les éditeurs : l'API existe, pas l'écran.
- Rattachement d'une collection personnelle à une série du catalogue : l'API existe, pas le bouton.
- Page d'état et branchement de la supervision (ENF-01, T-07).
- V1.1 : vérification assistée des achats (F-40, F-41), suggestion de cartes recherchées (F-47).

### Non vérifié dans cet environnement

- Appels réels à l'API Claude, envoi réel d'e-mails, stockage S3, déploiement.
- Import du PDF réel Topps Flagship Football 2026 (CA-11) et reprise des données réelles (CA-18).
- Installation de la PWA et usage hors ligne sur un téléphone.
