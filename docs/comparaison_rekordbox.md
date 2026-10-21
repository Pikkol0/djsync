# Comparer l'analyse de DJSync à celle de Rekordbox

Objectif : mesurer, sur **votre** musique, à quel point DJSync trouve le même BPM, la même tonalité et
la même grille que Rekordbox. L'outil ne modifie rien (lecture seule).

## 1. Préparer l'échantillon

Les sons **analysés par DJSync** ne servent à rien ici (on comparerait DJSync à lui-même) : il faut
que **Rekordbox** analyse les mêmes fichiers. L'outil ne prend que les sons analysés par Rekordbox et
le dit (« N analysed by DJSync ignored »).

1. Téléchargez vos sons avec DJSync sur la clé (c'est déjà fait pour vos ~50 sons).
2. Ouvrez **Rekordbox** (PC), *Préférences ▸ Analyse* :
   - *Mode d'analyse des morceaux* : **Normal** (grille à tempo fixe, comme DJSync) ;
   - *Plage BPM* : la même que d'habitude (par défaut 70-180) — notez-la ;
   - cochez BPM / grille, Tonalité.
3. Dans l'Explorateur, ouvrez `E:\Contents` et **glissez le dossier** dans la *Collection* de
   Rekordbox. Attendez la fin de l'analyse (barre en haut).
4. **Fermez Rekordbox** (sinon `master.db` est verrouillée).

## 2. Lancer la comparaison

Dans le dossier du dépôt (là où vous lancez `python app.py`) :

```
python -m djsync.analysis --compare local --under "E:\Contents" --csv comparaison.csv
```

- `local` = la collection Rekordbox de ce PC ; `--under` = seulement les sons de la clé.
- Variante : une clé exportée par Rekordbox (sons « natifs ») → `python -m djsync.analysis --compare E:`.
- Compter ~1 à 3 s par son (DJSync réanalyse chaque fichier).

Chaque ligne montre BPM et tonalité des deux côtés (`<--` = différence). Le résumé final :

```
==== Summary (DJSync vs Rekordbox) ====
  Same BPM (±0.05)                     46/50    92.0 %   (95 % CI 81-97 %)
  Same BPM or ×2 / ÷2                  49/50    98.0 %   (95 % CI 90-100 %)
  Same key                             38/50    76.0 %   (95 % CI 63-86 %)
  Same key or relative maj./min.       44/50    88.0 %   (95 % CI 76-94 %)
  Grid: beats within 20 ms             45/49    91.8 %   (95 % CI 81-97 %)
  Grid: same downbeat (bar start)      41/49    83.7 %   (95 % CI 71-92 %)
```
(chiffres d'exemple). Envoyez-moi `comparaison.csv` : il contient les mesures internes qui servent au
réglage fin.

## 3. Quelle taille d'échantillon ?

La « fourchette » (intervalle de confiance à 95 %) dit où se trouve la vraie précision :

| Sons comparés | Marge d'erreur (pour ~90 % d'accord) | Marge (pire cas, ~50 %) |
|---|---|---|
| 50 | ± 8 points | ± 14 points |
| 100 | ± 6 | ± 10 |
| 200 | ± 4 | ± 7 |
| 400 | ± 3 | ± 5 |
| 1 000 | ± 2 | ± 3 |

- **50 sons** : suffisant pour repérer un défaut grossier (BPM doublé, grille décalée sur tout un
  format), pas pour chiffrer la précision.
- **300 à 500 sons variés** : le bon compromis (± 3-5 points). Au-delà, le gain est faible.
- **La variété compte plus que le nombre** : mélangez les styles (house, techno, rap/trap, afro,
  reggaeton, DnB, pop, rock/live), les tempos (70-175 BPM), et quelques cas difficiles (intros sans
  batterie, tempo qui varie, versions live). 500 sons d'un seul style mesurent ce style seulement.
- Comptez les **erreurs d'octave** à part (85 contre 170 BPM) : ce n'est souvent qu'une question de
  plage BPM, pas une erreur de détection.

## 4. Lire les écarts

- **BPM ×2 / ÷2** : plage BPM différente ; normal sur le rap (75/150) et la DnB (87/174).
- **Tonalité relative** (8A ↔ 8B) : même gamme, erreur « légère » pour le mix harmonique.
- **Grille décalée d'un temps** (« downbeat shifted ») : le 1er temps de mesure n'est pas au même
  endroit ; le BPM est bon, il suffit de recaler le premier temps dans l'éditeur de grille.
- **Décalage constant par format** (ligne `.m4a : median offset …`) : un décalage de quelques ms
  identique sur tous les m4a se corrige d'un seul réglage — c'est exactement ce que le CSV permet.
