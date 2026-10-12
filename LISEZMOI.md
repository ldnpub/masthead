# Masthead

La une, à voix haute.

Masthead transforme des sources que vous avez déjà le droit de lire en podcast personnel : articles RSS, posts et fils X, bandes-son de vidéos, pages web, et courtes leçons. Le pupitre tourne sur votre ordinateur. Publier les flux est facultatif, et la publication se fait sur un compte Cloudflare qui vous appartient.

![Le pupitre Masthead, avec l’étagère d’exemple](docs/screenshots/desk-fr.png)

## Avant d’enregistrer

- **edge-tts** parle à un service de synthèse Microsoft via un client officieux. Microsoft peut le bloquer. Dans ce cas, passez le moteur sur Piper.
- **fxtwitter** (`api.fxtwitter.com`) est un moyen officieux de lire des posts publics. Il peut changer ou disparaître.
- **Vous êtes responsable des droits** sur les articles, posts, pages et vidéos que vous convertissez. Masthead est prévu pour un usage personnel. Il n’embarque ni identifiants ni extracteurs de sites payants commerciaux. Ne partagez pas le flux si le contenu n’est pas le vôtre à partager.

## Ce que vous obtenez

- Un pupitre local sur `http://127.0.0.1:8741`, en français ou en anglais.
- N’importe quelle voix edge-tts, ou un modèle Piper hors ligne. La voix par défaut est `en-US-AriaNeural`. Une voix française multilingue est dans la liste proposée.
- Cinq flux : articles, le fil, l’écran, les leçons, les lectures. Les chapitres sont écrits en trames ID3 `CHAP` et en JSON Podcasting 2.0.
- Une page de partage Android une fois votre propre Worker déployé.
- Un endroit pour ajouter vous-même un flux privé. Voir [docs/private-feeds.md](docs/private-feeds.md).

## Voir l’étagère d’exemple

Il faut Node.js 18 ou plus récent et Python 3.10 ou plus récent. L’étagère d’exemple n’appelle ni la voix ni le fil.

```bash
npm run demo
```

Ouvrez [http://127.0.0.1:8741](http://127.0.0.1:8741). Les éditions de cette étagère sont fictives.

`npm start` est le même pupitre sans les exemples. Sans configuration, il demande d’ajouter une source. Les épisodes restent dans `data/` tant que R2 n’est pas configuré.

## Enregistrer pour de vrai

ffmpeg est requis. Debian/Ubuntu : `sudo apt install ffmpeg`. macOS : `brew install ffmpeg`.

```bash
./installer.sh
npm start
```

`./installer.sh` crée `.venv`, puis installe edge-tts et yt-dlp. `./installer.sh --piper fr` ou `--piper en` télécharge aussi une voix Piper hors ligne. Indiquez ce modèle dans Réglages, et installez le binaire Piper de votre système si vous voulez éviter la voix en ligne.

Collez un flux que vous pouvez récupérer dans Sources, ou envoyez une adresse depuis Écran, Le fil ou Leçons. Les tâches passent une par une. Les journaux retirent les chaînes de requête.

## Publier les flux sur votre compte Cloudflare

`./setup.sh` est l’installation du premier jour. Il passe par Wrangler, crée un bucket R2, déploie le Worker dans `cloudflare/`, envoie les couvertures, génère un jeton de boîte, et le range comme secret `INBOX_TOKEN`. Le jeton est écrit dans `studio-config.json` (mode 600) et n’est pas affiché. Ouvrez Réglages sur cet ordinateur pour le voir.

```bash
./setup.sh --dry-run
./setup.sh --yes --worker-name masthead --bucket masthead-library --lang fr
```

La connexion Wrangler suffit pour déployer et envoyer les fichiers. Le moteur local écrit l’audio dans R2 avec un jeton d’API Cloudflare qui a accès à R2. Collez ce jeton dans Réglages. Tant que l’identifiant de compte, le bucket et le jeton ne sont pas tous les trois renseignés, les épisodes restent sur le disque.

`cloudflare/wrangler.jsonc` est généré pour vous et ignoré par git. L’exemple versionné ne contient pas d’identifiant de compte.

La page de partage du téléphone est `https://<votre-worker>.workers.dev/share`. La première visite avec `?k=` pose un cookie `mh_k` puis redirige, pour ne pas laisser le jeton dans la barre d’adresse.

## Sources privées ou payantes

Lisez [docs/private-feeds.md](docs/private-feeds.md). En bref : collez l’URL d’un flux à jeton, utilisez l’authentification HTTP basic, ou enregistrez votre propre cookie de session pour chaque source. Cookies et jetons restent dans `studio-config.json`. Pour un site auquel vous êtes abonné, ajoutez un extracteur Python dans `extractors/` (ignoré par git). `engine/extractors/example_member_press.py` est un adaptateur fictif à copier.

## Langue et voix

Le bouton EN / FR dans la manchette règle la langue du pupitre, les dates lues à voix haute et les consignes des leçons. Réglages accepte n’importe quel identifiant de voix edge-tts, par exemple `fr-FR-VivienneMultilingualNeural` ou `en-GB-SoniaNeural`.

## Allure

Masthead est composé comme un petit journal : papier `#f3ecdf`, encre `#1c140f`, une lampe vermillon « à l’antenne » `#d63c2e`, des filets laiton, et des liens bleu marine. Les caractères sont Fraunces, Barlow et IBM Plex Mono, fournis sous la SIL Open Font License (`public/fonts/OFL-*.txt`). Les couvertures sont les cinq planches de `public/covers/`.

![Les sources de l’étagère d’exemple](docs/screenshots/sources.png)

![Les éditions](docs/screenshots/editions.png)

## Organisation

| Chemin | Rôle |
| --- | --- |
| `server.js` | Pupitre local |
| `engine/studio.py` | Récupérer, extraire, lire, publier |
| `engine/extractors/` | Extracteurs intégrés et l’exemple fictif |
| `cloudflare/` | Worker qui sert le RSS, l’audio, les couvertures et la boîte |
| `docs/private-feeds.md` | Ajouter une source à laquelle vous êtes abonné |
| `setup.sh` | Déployer votre Worker et votre bucket |
| `installer.sh` | Outils Python locaux |

## Tests

```bash
npm test
```

## Licence

[MIT](LICENSE). Les polices restent sous la SIL Open Font License.

Le guide en anglais est [README.md](README.md).
