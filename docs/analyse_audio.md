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
| Pochette | `image_id` → table `image` (`/PIONEER/Artwork/00007/b137.jpg`) | `artwork_id` → table 13 (`…/a137.jpg`) | `a137.jpg`, `b137.jpg` 80×80 + `a137_m.jpg`, `b137_m.jpg` 240×240 (mêmes octets) |
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
Relevé sur la vraie clé (dossier PIONEER complet, 136 pochettes) : chaque pochette existe en double,
`aN` (référencée par export.pdb) et `bN` (référencée par exportLibrary.db), fichiers identiques,
même numéro, chacune en 80 et 240 px. 20 pochettes par dossier (`a1`–`a19` dans `00001`, `a20`–`a39` dans
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

### Calibrage sur une vraie clé (213 sons + dossier PIONEER complet)
| | V1.1-A4 | V1.1-A4.1 (mesuré) |
|---|---|---|
| BPM identique à Rekordbox | 71 % | 84 % |
| BPM identique ou à l'octave près | 81 % | 92 % |
| Tonalité identique | 67 % | 72 % |
| Tonalité compatible (même, ±1, relatif) | 83 % | 90 % |

Grille (V1.1-A4.2), comparée aux 213 grilles ANLZ de Rekordbox :
* **MP3 : silence d'amorçage.** Rekordbox et les platines comptent le temps AVEC le silence de
  l'encodeur MP3 (en-tête LAME : 576 + 529 échantillons = 25 ms), FFmpeg le retire. Mesuré : grilles
  DJSync à 0,1 ms de Rekordbox en WAV, 24,6 ms trop tôt en MP3. DJSync rajoute ce silence avant
  l'analyse (grille ET formes d'onde). Effet projeté : grilles à ±20 ms de 48 → 112 sons sur 179.
* **Contretemps** : 40 sons calés sur le contretemps (house : charlestons ouverts). Correction :
  si les attaques graves (kick) sont 1,3× plus fortes un demi-temps plus loin, on décale.
* **1er temps de mesure** : changement harmonique (+ 0,5 × basses) : 6/8 au lieu de 3/8 sur les
  sons testés.
* **M4A (AAC), 1.2.0-rc.4** : mesuré sur 52 m4a téléchargés par DJSync et analysés par Rekordbox 7
  (22-23/10/2026) : la grille DJSync arrivait **32,5 ms trop tôt** (écart-type 3,9 ms, 32 sons à BPM
  juste). DJSync rajoute donc 32,5 ms avant l'analyse des .m4a (grille ET formes d'onde,
  `decode.M4A_TIMELINE_OFFSET_MS`) ; projeté : 32/32 grilles à ±15 ms. Valeur empirique : le CSV
  de `--compare` relève la liste d'édition (`edit_media_time`) et l'iTunSMPB de chaque m4a pour
  l'affiner (un son, « Space Song », n'avait pas ce décalage). L'éditeur de grille décale le
  curseur de lecture d'autant (MP3 et m4a), le lecteur jouant le fichier sans ce silence.
* **Contretemps, suite (1.2.0-rc.4)** : sur les mêmes 52 m4a, 10 grilles décalées d'un demi-temps
  sans que le rapport kick contretemps / temps ne les distingue (0,39 à 2,46 contre jusqu'à 2,07
  pour des grilles justes). `--compare` compte maintenant « shifted by half a beat » ; l'éditeur de
  grille a un bouton « ½ temps » en attendant une meilleure détection.

Formes d'onde, comparées aux .EXT de Rekordbox des 10 sons fournis : alignement 0 ms, corrélation
0,79-0,93. Recalibrées (courbe de hauteur en puissance 3, couleurs, blancheur, aperçus, modèle
linéaire PWV4) : erreurs divisées par 1,5 à 3 (détails dans waveform.py).

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
* `.2EX` (formes d'onde « 3 bandes » de Rekordbox 6/7 et du CDJ-3000) écrit depuis la V0.3.0, calé
  sur les 10 sons réels : PWV7 = basses / médiums / aigus à 150 points/s (erreur moyenne 8/127),
  PWV6 = aperçu 1200 colonnes (corrélation 0,93 avec Rekordbox), PWVC = 3 facteurs ≈ k / (bande au
  centile 99,9) (±15 %). Sans ce fichier, Rekordbox réglé sur « 3Band » montrait un aperçu bleu des sons
  DJSync dans la liste et sous les platines. Les sons analysés avant la V0.3.0 l'obtiennent avec
  « Analyser à nouveau ».
* Non écrits : PQT2, PSSI (phrases).
* Le dossier `USBANLZ/Pxxx/xxxxxxxx` est un hachage DJSync (celui de Rekordbox n'est pas documenté) ;
  les platines suivent le chemin inscrit dans la base, quel qu'il soit.

## Utilisation
* V0.2.0 : **à la demande** (Bibliothèque ▸ Outils ▸ Analyser, Accueil, Paramètres) via
  `RekordboxUsbLibrary.analyze_tracks()` (calcul hors verrou, écritures par lots de 8 sons). L'analyse à
  chaque ajout est un réglage (`analyze_on_add`), **désactivé par défaut** depuis la V0.2.0 ; pochette et date
  d'ajout restent toujours écrites.
* Grille fausse sur les platines : éditeur de grille (voir `interface_v020.md`).
* Sons ajoutés par une version précédente : `RekordboxUsbLibrary.analyze_missing()`. Les sons natifs Rekordbox ne
  sont jamais réanalysés ; dans export.pdb, la ligne d'un ancien son DJSync est réécrite avec le
  **même id** (playlists intactes).
* Suppression d'un son DJSync : ses fichiers ANLZ sont supprimés aussi (pas la pochette, partageable).
* Vérifier sans rien écrire : `python -m djsync.analysis fichier.m4a`.
