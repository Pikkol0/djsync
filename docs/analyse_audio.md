# Analyse audio, pochettes et date d'ajout (V1.1-A4)

Chaque son ajouté par DJSync est désormais **prêt pour les platines sans passer par Rekordbox** :
BPM, grille de temps, tonalité, formes d'onde, pochette et date d'ajout sont écrits dans
`exportLibrary.db` **et** dans `export.pdb`.

## Ce qui est écrit sur la clé

| Élément | exportLibrary.db | export.pdb | Fichiers |
|---|---|---|---|
| Date d'ajout | `dateAdded` / `dateCreated` au **format des sons natifs de la clé** (voir plus bas) | `date_added` = `AAAA-MM-JJ` (relevé sur l'export réel) | — |
| BPM | `bpmx100` (ex. 12800) | champ `tempo` x100 | grille dans `ANLZ0000.DAT` (PQTZ) |
| Tonalité | `key_id` → table `key` | `key_id` → table 5 (tonalités) | — |
| Pochette | `image_id` → table `image` (`/PIONEER/Artwork/00007/a137.jpg`) | `artwork_id` → table 13 (même chemin) | `a137.jpg` 80×80 + `a137_m.jpg` 240×240 |
| Analyse | `analysisDataFilePath`, `analysedBits` (valeur des sons natifs, sinon NULL) | `analyze_path`, `analyze_date` | `PIONEER/USBANLZ/Pxxx/xxxxxxxx/ANLZ0000.DAT` + `.EXT` |

### Date d'ajout
Rekordbox écrit `AAAA-MM-JJ` dans export.pdb (vérifié sur 213 pistes réelles). Pour exportLibrary.db,
DJSync **copie le format d'un son natif de la clé** (ligne avec `masterDbId`, donc exportée par
Rekordbox) : date seule, ou horodatage complet `2025-04-12 19:11:29.274 +00:00` (format OneLibrary
documenté par pyrekordbox). Sur une clé sans son natif : horodatage complet UTC.

### Tonalité
Détectée en notation musicale, convertie en Camelot. Écrite selon le réglage `key_notation` :
* `auto` (défaut) : la notation déjà majoritaire sur la clé (votre clé réelle : `Am`, `F#m`… ; une
  clé vide : Camelot `8A`). Une ligne équivalente existante est réutilisée (`8A` ≡ `Am`) ;
* `camelot` : toujours `8A` ; `musical` : toujours `Am`.
L'interface de DJSync affiche toujours le Camelot.

### Pochettes
Relevé sur l'export réel : 20 pochettes par dossier (`a1`–`a19` dans `00001`, `a20`–`a39` dans
`00002`…). Le numéro suit le plus grand déjà utilisé (bases ET fichiers présents : une pochette
orpheline n'est jamais écrasée). Les sons d'un même album partagent la pochette.

## Moteur d'analyse (`djsync/analysis`)

Dépendances : **numpy + FFmpeg** (déjà requis). Pas de librosa/scipy/numba : +15-20 Mo dans l'exe.
Environ **1 s par minute de musique**, ~80 Mo de mémoire au pic pour un morceau de 5 min.

* **BPM / grille** (V1.1-A4.1, recalibré sur ta clé) : flux spectral → candidats (pics
  d'autocorrélation + rapports 3/2 et 2/3) → chaque candidat est **affiné puis comparé** par
  alignement direct sur les attaques → arrondi à l'entier s'il aligne aussi bien → temps fort par
  l'énergie des basses. Octave : règle observée chez Rekordbox (rapide sous 168, moitié au-dessus).
* **Grille variable** : si (et seulement si) une grille qui suit le morceau colle 1,5 fois mieux
  aux attaques et s'écarte de plus de 30 ms, la grille ANLZ porte un tempo par temps (balise PQTZ).
  Mesuré : accélérations 120→126 suivies à ±5 ms ; 0 bascule sur 10 sons réels à tempo fixe.
* **Tonalité** : spectre moyen, chromagramme (moyenne accordé / 440 Hz), profils 50 % Sha'ath +
  50 % appris sur 206 sons analysés par Rekordbox, 24 tonalités.
* **Formes d'onde** : 3 bandes (basses < 250 Hz, médiums, aigus > 2,5 kHz) à 150 points/s.

### Calibrage sur une vraie clé (213 sons, `python -m djsync.analysis --compare E:\ --csv diag.csv`)
| | V1.1-A4 | V1.1-A4.1 |
|---|---|---|
| Tonalité identique à Rekordbox | 67,5 % | 71,8 % (validation croisée) |
| Tonalité compatible (même, ±1, relatif) | 83,5 % | 90,3 % (validation croisée) |
| BPM, 10 sons « difficiles » envoyés | 0/10 | 6/10 exacts (+ Freestyle Funk à 0,05) |
| Choix d'octave dans la zone 70-90 / 140-180 | 30/53 | 40/53 (règle sur le CSV) |

Le BPM global sur les 213 sons n'a pas pu être remesuré ici (il faut l'audio) : relancer
`--compare`, qui affiche aussi désormais l'écart de **grille** avec Rekordbox (temps à ±20 ms,
même temps fort), lu dans les ANLZ de Rekordbox présents sur la clé.

### Fichiers ANLZ
Constantes et ordre des balises recopiés de **vrais fichiers exportés par Rekordbox 6** (jeu de
test public de pyrekordbox) :
* `.DAT` : PPTH, PVBR, PQTZ (grille), PWAV (aperçu 400), PWV2 (mini-aperçu 100), PCOB ×2 ;
* `.EXT` : PPTH, PWV3 (détail mono), PCOB ×2, PCO2 ×2, PWV5 (détail couleur), PWV4 (aperçu couleur).
* Les échelles de PWV4 (6 octets/colonne, non documenté publiquement) ont été **mesurées par
  régression** sur les fichiers réels (ex. octet 2 ≈ 1,12 × crête des basses, R² = 0,98).

Vérifié : les fichiers sont relus par un lecteur indépendant (pyrekordbox) et reconstruits **à
l'octet près** ; en-têtes identiques aux fichiers Rekordbox.

## Résultats de validation (morceaux synthétiques, vérité terrain exacte)

| Cas | BPM trouvé | 1er temps fort (vrai) | Tonalité |
|---|---|---|---|
| 128, Am | 128.00 | 369 ms (370) | Am / 8A |
| 124, E | 124.00 | 50 ms (50) | E / 12B |
| 92,46, F#m | 92.46 | 810 ms (810) | F#m / 11A |
| 75, Cm (rap) | 75.00 | 200 ms (200) | Cm / 5A |
| 140, Bb | 140.00 | 600 ms (600) | Bb / 6B |
| 174, Dm (DnB) | 174.00 | 99 ms (100) | Dm / 7A |

Aussi testé : m4a/AAC, mp3 VBR, intro silencieuse de 8 s, vidéo désaccordée de +35 cents.

## Limites connues (honnêtement)
* **Jamais testé sur une platine ni sur votre vraie musique** : les tests prouvent la conformité au
  format et la justesse sur des signaux synthétiques. Étape suivante : `python -m djsync.analysis --compare E:\`
  (lecture seule) compare DJSync aux analyses Rekordbox de votre clé, son par son.
* Tonalité : confusion possible majeur/mineur relatif sur les progressions éoliennes ambiguës
  (ex. Bm-G-D-A = aussi vi-IV-I-V de Ré). L'erreur garde le même numéro Camelot (10A ↔ 10B) :
  le mix harmonique reste compatible.
* Rekordbox lui-même n'est pas une vérité absolue (Cloud Analysis activé : certaines valeurs viennent
  de la base partagée Pioneer ; grilles parfois mal calées) : 100 % d'accord n'est pas atteignable.
* Choix d'octave : aucune mesure du signal ne prédisait mieux le choix de Rekordbox que le seuil de
  168 BPM ; ~12 sons sur 53 restent « doublés » (ex. rap à 75 affiché 150).
* Pas de hot cues / memory cues automatiques.
* Non écrits : `.2EX` (forme d'onde 3 bandes du CDJ-3000 : une balise, PWVC, n'est pas décodée
  publiquement), PQT2, PSSI (phrases). Les platines utilisent alors les formes d'onde du `.EXT`,
  comme pour une clé exportée par Rekordbox 5.
* Le dossier `USBANLZ/Pxxx/xxxxxxxx` est un hachage DJSync (celui de Rekordbox n'est pas documenté) ;
  les platines suivent le chemin inscrit dans la base, quel qu'il soit.

## Utilisation
* Automatique à chaque ajout (réglage `analyze_on_add`, activé par défaut).
* Sons ajoutés par une version précédente : `RekordboxUsbLibrary.analyze_missing()` (ou
  `controller.analyze_missing()`, prêt pour un bouton à l'Étape B). Les sons natifs Rekordbox ne
  sont jamais réanalysés ; dans export.pdb, la ligne d'un ancien son DJSync est réécrite avec le
  **même id** (playlists intactes).
* Suppression d'un son DJSync : ses fichiers ANLZ sont supprimés aussi (pas la pochette, partageable).
* Vérifier sans rien écrire : `python -m djsync.analysis fichier.m4a`.
