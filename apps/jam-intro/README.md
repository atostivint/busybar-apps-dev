# Jam Intro — BUSY Bar sur le MacBook

Cette app fait tourner une animation sur la BUSY Bar, branchée en USB.

## Lancer l'animation

Deux façons :

1. Double-clic sur **Jam Intro.app** : choisis l'effet dans la liste, la barre démarre.
2. Ou dans le Terminal :

```bash
cd apps/jam-intro
./run-jam-intro.command
```

Pour arrêter : `Control-C` dans la fenêtre Terminal. L'écran de la barre est effacé.

## La barre en USB

En USB, la barre est toujours à `http://10.0.4.20`.
Aucun mot de passe n'est demandé.
Tu branches, tu attends quelques secondes, tu lances.

Si le script dit qu'aucune barre ne répond : débranche, rebranche, attends 5 secondes.

## Jouer avec la barre (scène `pool`)

- **Tourner la molette** : pousse les jouets vers les bords pour dégager le titre ou le logo,
  avec des ronds dans l'eau qui font onduler le texte. Les jouets restent écartés un instant,
  puis reviennent doucement.
- **Cliquer sur la molette** : lance un jouet au hasard au milieu de
  la piscine. Il tombe, fait plouf, puis dérive hors de l'écran. Trois au maximum à la fois.
- **Appuyer sur start/pause** : passe tout de suite du titre au logo, ou l'inverse.

Sans action, titre et logo alternent toutes les 60 s.
Pour changer ce rythme : `python3 app.py --swap 30` (0 = seulement avec start/pause).

### Les jouets de la piscine

Un canard et une bouée, plus des clins d'œil aux jeux vidéo : Pac-Man poursuivi par un fantôme,
champignon, anneau d'or, Poké Ball, pièce de Tetris, envahisseur de l'espace, cœur et Creeper.
Ils sont dessinés pixel par pixel dans `app.py` (`ROSTER`, `toy_pixels`).

## Les effets

`auto` alterne tout seul. Sinon, un effet à la fois :

| Effet | Rendu |
|---|---|
| `pool` | piscine vue de dessus : le titre en grand au fond, qui alterne toutes les minutes avec le logo Stunfest (une vague fait la transition). Déformation comme vue à travers l'eau, un reflet balaie le mot, et de gros jouets traversent à tour de rôle, trois par passage, en changeant à chaque fois — effet par défaut. Se pilote avec la barre, voir plus haut |
| `plasma` | nappes de couleurs qui ondulent |
| `starfield` | étoiles qui arrivent vers toi |
| `fire` | flammes en bas de l'écran |
| `sparkle` | étincelles de couleurs |

Exemple au choix :

```bash
./run-jam-intro.command 10.0.4.20 plasma
./run-jam-intro.command 10.0.4.20 fire
```

## Changer l'image du bandeau

Le bandeau est le fichier `banner.png`. Il est dessiné par-dessus l'animation.
Par défaut : le logo officiel **Octojam 2026**, entier, mis à l'échelle pour tenir dans l'écran.

- Il doit faire **72×16 pixels au maximum**, en PNG.
- Les pixels transparents laissent voir l'animation derrière.
- Tu peux mettre n'importe quelle image : remplace `banner.png` et relance.

Autres bandeaux prêts à l'emploi, dans le dossier `banners/` :

| Fichier | Contenu |
|---|---|
| `octojam-contrast-black-bright.png` | identique à `banner.png` : lettres blanches/jaunes sur bandeau noir |
| `octojam-contrast-dim-outline.png` | fond assombri (garde un peu de couleur) + contour noir |
| `octojam-pixel-band.png` | le bandeau pixelisé brut, sans traitement |
| `stunfest-2026-full.png` | logo Stunfest entier |
| `stunfest-2026-wordmark.png` | seulement le mot « stunfest », en plus gros |

Pour en utiliser un autre :

```bash
cd apps/jam-intro
cp banners/stunfest-2026-wordmark.png banner.png
```

Le bandeau par défaut est passé par le **Pixel Engine** : le logo a été
pixelisé (8 couleurs, vraie grille de pixels), puis un contour noir de 1 pixel
a été ajouté autour des lettres. Sans ça, un simple redimensionnement laisse
des bords flous et flous le mot devient illisible sur 72×16.

Un logo entier qui contient trois lignes de texte ne peut pas être lisible sur 72×16 :
c'est pour ça que les versions « wordmark » ne gardent que le nom.

`logo-source-stunfest.png` et `logo-source-octojam.png` sont les logos d'origine,
gardés comme référence. Le logo Octojam 2026 vient de stunfest.com.
Le logo Stunfest de la scène `pool` est redessiné pixel par pixel d'après
`logo-source-stunfest-nb.svg` (LOGO_STUN25_NB.svg). Il monte vers la droite comme
l'original, mais en moins raide (3 pixels), pour que les lettres restent assez hautes.

Ces logos appartiennent à l'association 3 Hit Combo : usage perso / jam, pas commercial.

## Détails utiles

- Le script n'a besoin que de `python3`. Pas de `pip install`.
- La même app tourne sur l'émulateur : `./run-jam-intro.command 127.0.0.1:8080`.
- En Wi-Fi : `export BUSYBAR_TOKEN=le_mot_de_passe` puis
  `./run-jam-intro.command <ip_de_la_barre>`. Il faut d'abord activer l'accès HTTP API sur la barre.
  En USB, rien de tout ça.

## Fichiers

| Fichier | Rôle |
|---|---|
| `app.py` | le programme (Python seul, sans dépendance) |
| `banner.png` | le bandeau affiché par-dessus l'animation |
| `banners/` | autres bandeaux prêts à l'emploi |
| `logo-source-*.png` | les logos d'origine, pour refaire un bandeau |
| `run-jam-intro.command` | le lanceur en ligne de commande |
| `jam-intro.applescript` | source de l'app double-cliquable |
| `preview.gif` | aperçu enregistré depuis l'émulateur (720×160) |
| `manifest.yaml` | fiche descriptive de l'app |
