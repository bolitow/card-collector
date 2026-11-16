# Recette : état des critères d'acceptation

Section 15 du cahier des charges. « Serveur » : tests automatisés de `backend/tests` sur PostgreSQL.
« Navigateur » : scénarios de `e2e/flows.mjs`, joués dans Chrome sur un écran de 390 px.
Rien n'a été vérifié sur un environnement de recette déployé : il n'existe pas encore.

| Réf. | Scénario | État | Vérifié par |
|---|---|---|---|
| CA-01 | A demande une donnée de B | Passe | Serveur, `test_privacy.py` : 17 accès tentés, tous refusés sans donnée |
| CA-02 | Profil public | Passe | Serveur et navigateur : seules les collections partagées ; ni prix, ni date, ni carte vendue dans la page ou les réponses |
| CA-03 | Révoquer un lien | Passe | Serveur et navigateur : le lien et ses photos répondent 404 aussitôt |
| CA-04 | Photo avec position GPS | Passe | Serveur : les trois tailles stockées n'ont plus de métadonnées |
| CA-05 | Toucher une case manquante | Passe | Serveur et navigateur |
| CA-06 | Saisie rapide, trois appuis puis Annuler | Passe | Navigateur : ×2 à l'écran et en base |
| CA-07 | Parallèle sur une carte manquante | Passe | Serveur |
| CA-08 | Achat « Gold 35/50 » d'une série suivie | Passe | Serveur |
| CA-09 | Achat dans une série non suivie, puis suivi | Passe | Serveur |
| CA-10 | Correction d'une checklist suivie | Passe | Serveur, avec 2 utilisateurs au lieu de 10 |
| CA-11 | Import du PDF Topps Flagship Football 2026 | **Partiel** | Le pipeline passe sur une checklist de synthèse (doublons BTP signalés, équipes, rookies). Le PDF réel et l'API Claude n'étaient pas disponibles : les 4 042 références et 87 sous-séries restent à constater. |
| CA-12 | Chercher « 3 » puis « nets » | Passe | Vecteurs partagés serveur/interface, recherche globale, navigateur |
| CA-13 | Équipe prioritaire | Passe | Serveur et navigateur |
| CA-14 | Quota d'IA atteint | Passe côté serveur | Refus explicite, saisie manuelle possible. Le message à l'écran n'a pas été joué dans le navigateur. |
| CA-15 | Réseau coupé pendant un cochage | Passe | Navigateur : retour arrière, bandeau, « Réessayer » enregistre |
| CA-16 | Export puis suppression du compte | Passe | Serveur : archive complète avec photos ; plus aucune ligne ni fichier ensuite |
| CA-17 | Collection de 4 042 cartes sur téléphone | Passe en simulation | Navigateur, processeur ralenti ×4 : environ 0,4 s depuis l'accueil, défilement sans image lente. À confirmer sur un vrai téléphone en 4G. |
| CA-18 | Reprise du prototype | **Partiel** | Totaux identiques et reprise rejouable sur des données de synthèse au format de l'annexe E. Les données réelles n'étaient pas accessibles. |
| CA-19 | Thème sombre et lecteur d'écran | **Partiel** | Contraste du texte mesuré en thème sombre ; cases annoncées « code, nom, état, carte recherchée ». Aucun passage avec un vrai lecteur d'écran. |
| CA-20 | Réponse de l'IA mal formée | Passe côté serveur | Une seule nouvelle tentative, rien d'appliqué, erreur explicite |

## Exigences « Indispensable » non couvertes

| Réf. | Exigence | Manque |
|---|---|---|
| F-28 | Connexion avec Google et Apple | Non développée. L'e-mail, le mot de passe et le lien de connexion fonctionnent. |
| F-46 | Administration du catalogue | L'import, l'édition et l'historique ont leur écran. Univers, éditeurs, parallèles officiels et fusion de doublons n'ont que leur API. |
| T-07 | Trois environnements, supervision, alertes | Les fichiers de déploiement existent ; rien n'est déployé ni branché. |
| D-01, D-04 | Documents légaux, contrats de sous-traitance | Projets rédigés (`web/src/legal/`), à compléter et à faire valider. |

## Exigences « Important » non couvertes

F-35 (bouton de rattachement d'une collection personnelle), F-47 (écran des cartes recherchées
éditoriales ; suggestion par l'IA), F-40 et F-41 (vérification assistée d'un achat, V1.1),
ENF-01 (page d'état).

## À faire avant d'ouvrir au public

1. Brancher une clé d'API Claude et passer le jeu d'essai (`backend/scripts/ai_eval.py`) sur les 48
   photos du prototype, pour confirmer ou changer le modèle.
2. Jouer l'import sur le PDF de CA-11 et la reprise sur l'export réel du prototype.
3. Déployer la recette, puis rejouer `e2e/flows.mjs` dessus et sur un téléphone.
4. Faire valider les documents légaux et le seuil d'âge par un juriste.
