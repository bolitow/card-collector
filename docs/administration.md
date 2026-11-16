# Administration

L'administration est à l'adresse `/admin`, pour les comptes administrateurs, après la double
authentification.

## Importer une checklist

1. **Source.** Choisir l'univers et l'éditeur, puis déposer le PDF de l'éditeur ou coller son texte.
   Donner le nom de la série selon la convention : marque + produit + sport ou compétition + saison
   (« Topps Chrome Football 2026 », « Topps Gold UEFA Club Competitions 2025/26 »). Indiquer la
   source de la checklist. Le PDF n'est pas conservé : seul son texte l'est.
2. **Analyse.** Elle tourne en tâche de fond. Avec l'IA, le texte est découpé en extraits et
   structuré en sous-séries. Sans IA (case décochée, ou IA indisponible), le texte doit suivre le
   format simple : un titre par sous-série, puis une carte par ligne, colonnes séparées par une
   tabulation ou deux espaces — code, nom, équipe, « RC ». `[special]` après un titre force le type.
3. **Relecture.** Les anomalies sont calculées par l'application, pas par l'IA :
   - *bloquantes* — code invalide, code en double (dans une sous-série, ou repris d'une autre) ;
   - *à regarder* — nom en majuscules, variation dont le numéro n'existe pas dans la base ou dont
     le nom diffère de la carte de base, sous-série vide.

   Pour une sous-série qui reprend les numéros d'une autre, saisir un **préfixe** : le code publié
   devient `PRÉFIXE-code` (« GM-301 », « TIME-BTP-1 »). Ouvrir chaque sous-série signalée, corriger,
   puis « Enregistrer la relecture » : les anomalies sont recalculées.
4. **Publication.** « Voir les changements » montre ce qui sera ajouté, renommé, renuméroté ou
   retiré. « Publier » fait entrer la série au catalogue.

## Corriger une série publiée

Onglet Séries, « Corriger la checklist » : la série s'ouvre en brouillon, chaque carte gardant son
identifiant. Les collections des utilisateurs suivent les corrections : possession, photos et
marques sont conservées. Une carte retirée de la checklist est masquée si quelqu'un la possède ou
l'a achetée, supprimée sinon. Le nombre de possesseurs est affiché avant publication.

## File de travail

Demandes de séries (classées par nombre de demandeurs) et signalements. Chaque élément reçoit un
statut et, si besoin, une réponse envoyée par e-mail à son auteur. Une photo signalée se retire
depuis sa ligne ; le retrait est journalisé.

Quand une demande aboutit, la relier à la série publiée : le demandeur et ceux qui ont cliqué
« Moi aussi » sont prévenus.

## Utilisateurs

Recherche par e-mail ou pseudonyme. Suspendre, rétablir, régler les quotas d'IA ou supprimer un
compte demande un **motif**, conservé au journal. L'administration ne donne pas accès au contenu
des collections.

## Ce qui passe encore par l'API

Univers, éditeurs, cartes recherchées éditoriales, parallèles officiels et fusion de doublons
n'ont pas encore d'écran. En développement, l'API est documentée à `/api/docs`.
