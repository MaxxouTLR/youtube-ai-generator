# Générateur vidéo IA — YouTube format long (100% gratuit)

Pipeline automatisé : script IA local → voix off → montage avec visuels libres de droits → publication YouTube.
Niche : motivation / développement personnel, **en anglais** (audience internationale, meilleur RPM que le marché FR).
Rythme visé : 1 vidéo/jour, 15-20 minutes.

## Ce qui est déjà installé, configuré et testé
- **Ollama** (`llama3.2:3b`) — génère le script en local, aucune clé API, aucun compte. Script en anglais.
- **edge-tts** — voix off gratuite et illimitée, voix `en-US-AndrewMultilingualNeural` (chaleureuse/confiante), +12% de rythme.
- **Sous-titres dynamiques** — surbrillance mot par mot façon karaoké (`subtitles.py`), synchronisée précisément
  grâce aux timings edge-tts, gravée via ffmpeg/libass (rapide, ~0.4x la durée de la vidéo).
- **Visuels contextuels** — le script est découpé en segments de ~15-20s ; chaque segment génère son propre
  mot-clé de recherche via Ollama (ex: "man walking alone desert") pour trouver un clip Pexels qui correspond
  vraiment à ce qui est raconté, au lieu d'un pool générique pioché au hasard.
- **Titre/description/tags optimisés** — générés par Ollama à partir du script réel, sauvegardés en note
  `.txt` à côté de chaque vidéo, réutilisés automatiquement pour la publication YouTube.
- **Miniature automatique** — une frame forte extraite de la vidéo + texte accrocheur en surimpression
  (`thumbnail_generator.py`), générée pour chaque vidéo et appliquée automatiquement sur YouTube si le compte
  est éligible (voir limite ci-dessous).
- **Identité de chaîne** (`branding_kit/`, générée une fois, pas par vidéo) — nom **"Elevate Your Self"**
  (+ 8 alternatives dans `channel_name_options.txt`), 4 photos de profil, 4 bannières, et une description de
  chaîne, générées par IA (Pollinations.ai + Ollama, gratuit, sans compte) via `channel_branding.py`.
  À téléverser manuellement dans YouTube Studio (Personnalisation → Image de marque) : c'est une action
  ponctuelle (pas quotidienne), l'API YouTube pour ça est plus complexe qu'un simple glisser-déposer.
  **Voir `GUIDE_UTILISATION.md`** pour la marche à suivre complète, pensé pour piloter le bot sans aide.
- **Clé Pexels** — configurée (variable d'environnement `PEXELS_API_KEY`), visuels stock réels fonctionnels.
- **ffmpeg + moviepy** — montage automatique testé en 1080p/30fps.
- **Tâche planifiée Windows** `YouTubeAI-DailyVideo` — déclenchement quotidien à 9h, upload YouTube en **privé**.
- **Stockage** : toutes les vidéos finies vont dans `D:\YouTube Videos` (disque 2To), nommées
  `AAAA-MM-JJ_sujet-de-la-video.mp4` + leur note `.txt` jumelle — pas d'accumulation sur le disque système.
- Le pipeline complet script→voix→visuels ciblés→montage→sous-titres→métadonnées→upload a été testé de bout en bout.

## Ce qu'il reste à faire

### Accès YouTube Data API (pour la publication automatique) — obligatoire
1. Aller sur https://console.cloud.google.com/ , créer un projet.
2. Menu "API et services" → activer **YouTube Data API v3**.
3. "Identifiants" → créer des identifiants OAuth → type **Application de bureau**.
4. Télécharger le fichier JSON, le renommer `client_secret.json` et le placer dans ce dossier
   (`C:\Users\ovila\youtube-ai-generator\client_secret.json`).
5. Au premier lancement avec `--publish`, une fenêtre Google s'ouvrira pour vous connecter (une seule fois) —
   nécessaire aussi pour que la tâche planifiée quotidienne puisse publier automatiquement.

### ElevenLabs (optionnel, testé — non retenu par défaut)
Clé configurée, mais **inutilisable telle quelle** : ElevenLabs bloque désormais l'accès API aux voix de sa
bibliothèque pour les comptes gratuits (`402 payment_required`). Il faudrait ajouter une voix personnelle
dans "My Voices" depuis leur dashboard web pour débloquer l'API gratuite — et même alors, le quota gratuit
(~10k caractères/mois) ne couvre qu'une fraction d'UNE vidéo de 15-20 min. Non viable pour un rythme quotidien
sans passer sur un forfait payant (~99$/mois). Le pipeline reste donc sur edge-tts par défaut.

## Utilisation

```
cd C:\Users\ovila\youtube-ai-generator

# Générer script + voix + vidéo (sans publier)
python run_pipeline.py

# Générer ET publier automatiquement sur YouTube (en privé par défaut, voir config.py)
python run_pipeline.py --publish

# Imposer un sujet précis
python run_pipeline.py --topic "how to build unshakeable confidence" --publish
```

La tâche planifiée `YouTubeAI-DailyVideo` (visible dans le Planificateur de tâches Windows) lance
`python run_pipeline.py --publish` chaque jour à 9h. Ollama démarre automatiquement avec Windows,
pas d'action requise de votre part une fois `client_secret.json` en place.

La vidéo finale est publiée en **privé** par défaut (`YOUTUBE_PRIVACY_STATUS` dans `config.py`) —
passez-la à `"public"` une fois que vous avez vérifié la qualité sur quelques vidéos.

## Limites connues (honnêteté sur le "100% gratuit")
- Le modèle local (3B paramètres) écrit correctement en anglais (meilleur qu'en français, plus de données
  d'entraînement) mais reste en dessous d'un GPT-4/Claude — une répétition occasionnelle de tournure peut
  apparaître malgré les consignes anti-répétition. Relisez les premières vidéos avant de passer en public.
- Les visuels sont des vraies vidéos stock (choisies par mot-clé selon le contenu de chaque segment), pas de
  vrai "avatar IA" ni de scènes générées (le GPU AMD de cette machine ne permet pas cela gratuitement).
- **Temps d'encodage réel mesuré** : ~3 à 3.5x la durée de la vidéo (goulot d'étranglement = traitement image
  par image en Python pour le recadrage/redimensionnement, pas l'encodage x264 lui-même). Une vidéo de 15-20 min
  prend donc environ 50-70 minutes à assembler. Largement compatible avec une tâche planifiée quotidienne
  (limite fixée à 2h dans la tâche), mais à savoir si vous vouliez un résultat quasi-instantané.
- **Politique YouTube "spam/contenu généré en masse"** : gardez de la variété entre les vidéos
  (`FALLBACK_TOPICS` dans `script_generator.py`) et surveillez les premières semaines de publication.
- Pas de musique de fond par défaut (droits d'auteur) — vous pouvez ajouter des fichiers libres de droits
  dans `assets/music/` et les mixer manuellement si voulu.
- **Miniatures personnalisées sur YouTube** : nécessitent un compte vérifié par numéro de téléphone (limite
  imposée par YouTube, pas par ce script). Si non vérifié, l'upload de la vidéo réussit quand même mais la
  miniature générée n'est pas appliquée (avertissement affiché, sans bloquer le pipeline) — le fichier
  `_thumb.jpg` reste disponible dans `D:\YouTube Videos` pour l'ajouter manuellement une fois le compte vérifié.

## Fichiers du projet
- `config.py` — tous les réglages (voix, langue, durée cible, dossier de sortie, etc.)
- `script_generator.py` — script par sections (Ollama), mots-clés visuels par segment, titre/description/tags
- `voice_generator.py` — synthèse vocale gratuite (edge-tts) + timings mot par mot pour les sous-titres
- `voice_generator_elevenlabs.py` — alternative ElevenLabs (usage ponctuel seulement, voir limites ci-dessus)
- `subtitles.py` — génère les sous-titres dynamiques (.ass, style karaoké) à partir des timings
- `visuals_fetcher.py` — recherche/téléchargement de clips Pexels (par mot-clé ou en lot générique)
- `video_assembler.py` — montage par segments synchronisés (moviepy/ffmpeg) + gravure des sous-titres
- `thumbnail_generator.py` — miniature (frame vidéo + texte accrocheur en surimpression)
- `channel_branding.py` — nom de chaîne, photo de profil, bannière (Ollama + Pollinations.ai) — usage ponctuel
- `youtube_uploader.py` — publication automatique + miniature (YouTube Data API)
- `run_pipeline.py` — orchestre tout le pipeline, decoupe le script, ecrit la note titre/description/tags
