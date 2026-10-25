# Générateur vidéo IA — chaîne YouTube MAXXOU (100% automatisé, coût quasi nul)

Pipeline entièrement automatisé : script IA local → voix off → sous-titres karaoké → visuels libres
de droits → musique de fond générée → miniature IA → publication YouTube. Tourne en continu sur
**GitHub Actions** (pas besoin que le PC soit allumé). Niche : motivation / développement personnel,
**en anglais** (audience internationale, meilleur RPM que le marché FR).

## État actuel (en production)

- **3 vidéos/jour**, publiées automatiquement et **publiquement** sur la chaîne (grille relancée le
  25/10/2026 après une pause du 20 au 25/10) :
  - 2 Shorts (~20s) à **8h** et **13h** (heure de Paris)
  - 1 vidéo longue (15-20 min) à **19h**
- Hébergé sur **GitHub Actions** (dépôt public `MaxxouTLR/youtube-ai-generator`, choisi pour les
  minutes Actions gratuites illimitées). Le workflow `.github/workflows/daily-videos.yml` gère deux
  jeux de cron (heure d'hiver/été) et recalcule l'heure réelle de Paris à chaque déclenchement.
- Secrets GitHub Actions configurés : `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `PEXELS_API_KEY`,
  `YOUTUBE_CLIENT_SECRET_B64`, `YOUTUBE_TOKEN_B64`.
- OAuth YouTube en statut **Production** (pas Testing) — évite l'expiration du token à 7 jours,
  nécessaire pour un hébergement headless.
- Produit associé (affiliation/CTA) : lien inséré automatiquement en fin de description de chaque
  vidéo via `config.PRODUCT_CTA`.

## Périmètre de ce dépôt (branche `main`)

La branche `main` ne contient **que la chaîne YouTube anglaise** (motivation / développement
personnel). Le compte TikTok français « Dossiers d'Histoire » est un **projet séparé** depuis le
25/10/2026 : il vit sur la branche `demo-fr` (worktree local distinct, son propre workflow
`demo-fr.yml`, ses propres scripts `dossier_*.py` / `motion/`).
- Ne jamais fusionner `demo-fr` dans `main` ni l'inverse, et ne pas renommer le dépôt ni la branche
  `demo-fr` : les vidéos TikTok programmées dans Buffer pointent vers des liens `raw` de cette branche.
- Les notes de travail pour Claude (`CLAUDE.md`) restent en local, hors Git (dépôt public).

## Composants du pipeline

- **Script** — Ollama (`llama3.2:3b`, installé sur le runner), aucune clé API, aucun compte. Sujets générés à l'infini
  par Ollama lui-même (`script_generator._generate_new_topic`, évite les ~60 derniers sujets utilisés),
  avec repli sur `FALLBACK_TOPICS` si Ollama échoue 3 fois de suite. Règles de rétention (hooks,
  rythme, pas de répétition) injectées dans le prompt (`HOOK_RULES`).
- **Titres** — 5 gabarits distincts (`TITLE_STYLES` : question_tension, you_are_not, real_reason,
  stop_start, numbered_signs) choisis aléatoirement pondéré par Ollama à partir du script réel, pour
  éviter la convergence vers un seul style répétitif.
- **Voix off** — **Azure Cognitive Services Speech** (tier gratuit Free F0, ~500k caractères/mois).
  Voix unique `en-US-AndrewMultilingualNeural` (+12% de rythme) — configuration qui a produit les
  meilleures performances mesurées sur la chaîne. Remplace edge-tts depuis le 12/10/2026 (Microsoft
  bloque désormais edge-tts sur les IP de datacenter/cloud, dont GitHub Actions). Un garde-fou
  (`_trim_long_silences`) recadre automatiquement tout silence de plus de 0.45s entre deux mots,
  quelle que soit la voix utilisée.
- **Sous-titres dynamiques** — surbrillance mot par mot façon karaoké (`subtitles.py`), synchronisée
  sur les timings Azure Speech (`WordBoundary`), gravée via le filtre natif ffmpeg/libass (rapide,
  ~0.4x la durée de la vidéo).
- **Visuels contextuels** — le script est découpé en segments (~15-25s pour le format long, une
  phrase de ~7 mots pour les Shorts) ; chaque segment génère son propre mot-clé de recherche via Ollama pour
  trouver un clip Pexels pertinent, au lieu d'un pool générique.
- **Montage dynamique des Shorts** (`montage.py`) — un clip différent par phrase, accroche et
  sous-titres animés en police grasse (Montserrat Black sur le runner).
- **Musique de fond** — générée localement par synthèse numpy (`music_generator.py`, nappes
  ambiantes, 6 pistes), zéro risque de droits d'auteur, mixée à bas volume sous la voix off. Activée
  par défaut (`config.MUSIC_ENABLED = True`).
- **Miniature** — fond généré par IA (Pollinations.ai, gratuit) avec un prompt adapté au sujet exact
  de la vidéo, texte accrocheur en surimpression (mot-clé fort en couleur de marque). Repli
  automatique sur une frame extraite de la vidéo si la génération IA échoue.
- **Identité de chaîne** (`channel_branding.py`, usage ponctuel) — nom de chaîne, photo de profil,
  bannière générés par IA (Ollama + Pollinations.ai).
- **Titre/description/tags** — générés par Ollama à partir du script réel, sauvegardés en note
  `.txt`/`metadata.txt` à côté de chaque vidéo, réutilisés pour la publication YouTube.
- **Publication** — YouTube Data API, miniature personnalisée appliquée automatiquement (nécessite un
  compte vérifié par téléphone, sinon avertissement sans bloquer le pipeline).

## Utilisation locale (test / développement)

```
cd youtube-ai-generator  # dossier ou vous avez clone le depot

# Variables d'environnement necessaires (ou utiliser celles deja configurees sur cette machine)
# AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, PEXELS_API_KEY

# Video longue : genere tout, ne publie pas
python run_pipeline.py

# Video longue : genere ET publie sur YouTube (public par defaut, voir config.py)
python run_pipeline.py --publish

# Short : genere tout, ne publie pas
python run_shorts_pipeline.py

# Short : genere ET publie
python run_shorts_pipeline.py --publish

# Imposer un sujet precis
python run_pipeline.py --topic "how to build unshakeable confidence" --publish
```

En production, c'est le workflow GitHub Actions qui lance ces commandes automatiquement — aucune
action locale n'est nécessaire au quotidien. L'exécution manuelle sert surtout à tester une
modification avant de la pousser (`workflow_dispatch` sur GitHub avec la case "Publier" décochée pour
un run de test sans publication réelle).

### Accès YouTube Data API (déjà configuré, pour référence)
1. https://console.cloud.google.com/ → créer un projet.
2. "API et services" → activer **YouTube Data API v3**.
3. "Identifiants" → créer des identifiants OAuth → type **Application de bureau**.
4. Télécharger le JSON, le renommer `client_secret.json`.
5. Authentification unique via `InstalledAppFlow.run_local_server()` (ouvre le navigateur système,
   hors de portée de l'automatisation) — génère `token.json`, à encoder en base64 pour le secret
   GitHub `YOUTUBE_TOKEN_B64`.

### ElevenLabs (optionnel, testé — non retenu)
Clé configurée (`voice_generator_elevenlabs.py`), mais **inutilisable telle quelle** : ElevenLabs
bloque l'accès API aux voix de sa bibliothèque pour les comptes gratuits (`402 payment_required`), et
même en débloquant l'accès le quota gratuit (~10k caractères/mois) ne couvre qu'une fraction d'une
vidéo de 15-20 min. Non viable sans passer sur un forfait payant (~99$/mois). Le pipeline reste donc
sur Azure Speech par défaut.

## Limites connues (honnêteté sur le pipeline)
- Le modèle local (3B paramètres) écrit correctement en anglais (meilleur qu'en français, plus de
  données d'entraînement) mais reste en dessous d'un GPT-4/Claude — une répétition occasionnelle de
  tournure peut apparaître malgré les consignes anti-répétition.
- Les visuels sont des vraies vidéos stock (choisies par mot-clé selon le contenu de chaque segment),
  pas de vrai "avatar IA" ni de scènes générées (pas de GPU compatible pour ça gratuitement).
- **Temps d'assemblage** : le goulot d'étranglement est le traitement image par image en Python
  (recadrage/redimensionnement moviepy), pas l'encodage x264 lui-même. Une vidéo longue prend environ
  50-70 min à assembler sur un runner GitHub Actions standard.
- **Politique YouTube "contenu produit en masse"** (YouTube Partner Program) : signaux de variété
  surveillés (sujets, titres, voix) — voir l'historique du projet pour les ajustements faits suite à
  cette politique.
- **Fiabilité du `schedule` GitHub Actions** : peut rester silencieux plusieurs heures sans se
  déclencher (comportement documenté comme peu fiable pour les schedules nouvellement modifiés) —
  un matching par fenêtre de tolérance (180 min) et un anti-doublon (`output/last_auto_run.json`)
  compensent les déclenchements retardés ou ratés.
- **Miniatures personnalisées** : nécessitent un compte YouTube vérifié par téléphone. Si non
  vérifié, l'upload réussit quand même mais la miniature générée n'est pas appliquée (avertissement,
  pipeline non bloqué).
- Dépôt GitHub **public** : `products/` (contenu payant éventuel) est dans `.gitignore`, ne doit
  jamais être commité.

## Fichiers du projet
- `config.py` — tous les réglages (voix, langue, durée cible, dossier de sortie, CTA produit, etc.)
- `script_generator.py` — script par sections (Ollama), rotation de sujets infinie, 5 gabarits de
  titre, mots-clés visuels par segment, titre/description/tags
- `voice_generator.py` — synthèse vocale (Azure Cognitive Services Speech) + timings mot par mot pour
  les sous-titres + garde-fou anti-silences longs
- `voice_generator_elevenlabs.py` — alternative ElevenLabs (non retenue, voir limites ci-dessus)
- `subtitles.py` — génère les sous-titres dynamiques (.ass, style karaoké) à partir des timings
- `visuals_fetcher.py` — recherche/téléchargement de clips Pexels (par mot-clé ou en lot générique)
- `music_generator.py` — musique de fond ambiante générée localement (numpy, zéro droits d'auteur)
- `montage.py` — montage dynamique des Shorts (un clip par phrase, accroche et sous-titres animés)
- `video_assembler.py` — montage par segments synchronisés (moviepy/ffmpeg) + mixage musique +
  gravure des sous-titres
- `thumbnail_generator.py` — miniature (fond généré par IA + texte accrocheur en surimpression)
- `channel_branding.py` — nom de chaîne, photo de profil, bannière (Ollama + Pollinations.ai) — usage
  ponctuel
- `youtube_uploader.py` — publication automatique + miniature (YouTube Data API)
- `run_pipeline.py` — orchestre le pipeline vidéo longue
- `run_shorts_pipeline.py` — orchestre le pipeline Shorts
- `.github/workflows/daily-videos.yml` — workflow GitHub Actions (planification, retry, secrets)
- `run_pipeline_safe.ps1` — ancien wrapper des tâches planifiées Windows (avant GitHub Actions),
  conservé pour un éventuel retour à l'exécution locale ; plus utilisé en production
- `GUIDE_UTILISATION.md` — guide pas à pas (vérifier, tester, mettre en pause, dépanner)
