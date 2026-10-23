# Recevoir les retours de DJSync par e-mail (10 minutes, une seule fois)

L'onglet **Retours** de DJSync envoie bugs, idées et commentaires à un petit script Google qui vous
les transfère par e-mail, captures en pièces jointes. Le script tourne sur votre compte Google :
pas de serveur, pas d'abonnement, rien à entretenir. Tant qu'il n'est pas installé, DJSync ouvre à la
place un formulaire GitHub prérempli.

## 1. Créer le script
1. Connectez-vous au compte Gmail qui doit **recevoir** les retours.
2. Ouvrez <https://script.google.com> ▸ **Nouveau projet**.
3. Renommez le projet (en haut à gauche) : `DJSync retours`.
4. Effacez le contenu de `Code.gs`, collez **tout** le fichier `tools/feedback/apps_script.gs` du dépôt,
   puis **Enregistrer** (icône disquette).

## 2. Autoriser l'envoi d'e-mails
1. En haut, choisissez la fonction `doGet` puis **Exécuter**.
2. Google demande l'autorisation : *Examiner les autorisations* ▸ votre compte ▸ *Paramètres avancés* ▸
   *Accéder à DJSync retours (non sécurisé)* ▸ **Autoriser**. (« Non sécurisé » veut seulement dire que
   le script n'a pas été vérifié par Google : c'est le vôtre.)

## 3. Déployer
1. **Déployer** ▸ **Nouveau déploiement** ▸ roue dentée ▸ **Application Web**.
2. Description : `DJSync`. **Exécuter en tant que : Moi**. **Qui a accès : Tout le monde**.
3. **Déployer**, puis copiez l'**URL de l'application Web** (elle finit par `/exec`).

## 4. Vérifier
Collez l'URL dans le navigateur : la page doit afficher `{"ok":true,"service":"djsync-feedback"}`.

## 5. Brancher DJSync
Envoyez l'URL à Claude (ou mettez-la vous-même dans `djsync/core/feedback.py`, ligne
`FEEDBACK_URL = ""`). Elle sera dans la version suivante. Pour essayer avant, lancez DJSync avec la
variable d'environnement `DJSYNC_FEEDBACK_URL=<l'URL>`.

## Ce que vous recevez
Un e-mail par envoi : « [DJSync 1.2.1-rc.1] 2 Bug, 1 Idée · titre de la première remarque », avec les
remarques numérotées, les captures nommées d'après leur remarque (`1-bug-capture-1.jpg`), la version,
le système et, si l'utilisateur l'a laissé coché, la fin du journal (`djsync-log.txt`, chemins
personnels masqués). *Répondre* écrit directement à l'utilisateur s'il a donné son e-mail.

## Mise à jour du script (1.2.3)
La 1.2.3 ajoute deux sortes d'envois : « Logs » (bouton *Envoyer les logs*, avec un rapport sur la clé et,
si l'utilisateur le coche, un zip de `PIONEER/rekordbox`) et « Erreur » (rapport d'erreur proposé après
une erreur inattendue). Ils marchent avec le script d'origine (sujet « Remarque »). Pour avoir les bons
libellés : recollez `tools/feedback/apps_script.gs`, enregistrez, puis **Déployer** ▸ *Gérer les
déploiements* ▸ ✏️ ▸ *Version : nouvelle version* ▸ **Déployer** (l'URL ne change pas).

## Limites et entretien
- Gmail gratuit : environ **100 e-mails par jour**, largement assez.
- Le script refuse au-delà de 10 envois par ordinateur et 60 au total par tranche de 6 h, et les envois
  de plus de 15 Mo (DJSync réduit déjà les captures).
- En cas de spam : **Déployer** ▸ *Gérer les déploiements* ▸ archiver le déploiement, en créer un nouveau
  (nouvelle URL) et la mettre dans DJSync ; l'ancienne URL ne marche plus.
- Modifier le script : enregistrer, puis *Gérer les déploiements* ▸ ✏️ ▸ *Version : nouvelle version*
  (l'URL ne change pas).
