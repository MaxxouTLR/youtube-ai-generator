# Guide d'utilisation — Générateur vidéo YouTube IA

Ce guide explique comment faire vivre le bot **sans avoir besoin de moi (Claude)**. Tout tourne en local sur
cette machine, gratuitement, avec des outils standards (Python, Ollama, ffmpeg).

## 1. Où est tout stocké

| Quoi | Où |
|---|---|
| Le programme (le "bot") | `C:\Users\ovila\youtube-ai-generator` |
| Les vidéos finies | `D:\YouTube Videos\<date>_<sujet>\` (un dossier par vidéo : `video.mp4`, `thumbnail.jpg`, `metadata.txt`) |
| Les assets de chaîne (logo, bannière, description) | `C:\Users\ovila\youtube-ai-generator\branding_kit\` |
| Les réglages (voix, durée, niche...) | `C:\Users\ovila\youtube-ai-generator\config.py` |

## 2. Ce qui tourne automatiquement, sans rien faire

Trois tâches planifiées Windows tournent chaque jour (3 publications/jour au total) :

**"YouTubeAI-DailyVideo"** — **chaque jour à 9h**, vidéo longue (15-20 min) : écrit un nouveau script
sur un sujet de motivation, génère la voix, la musique de fond, les visuels, les sous-titres, le
titre/description/tags, la miniature, puis **publie automatiquement sur YouTube en public**.

**"YouTubeAI-DailyShort"** — **chaque jour à 15h**, Short (~50s, format portrait, voir section 3bis) :
mêmes étapes en version courte, publie avec le tag `#Shorts` **en public**. Log : `logs\shorts_pipeline.log`.

**"YouTubeAI-DailyShort2"** — **chaque jour à 20h**, un 2ème Short (ajouté le 24/09/2026 pour passer
à 3 publications/jour). Même script que le premier, log partagé dans `logs\shorts_pipeline.log`.

Vous n'avez rien à faire pour que ça tourne. Ollama démarre aussi automatiquement avec Windows.

**Publication en PUBLIC directement, sans relecture** (activé le 24/09/2026, voir section 4) —
si vous voulez repasser en privé pour relire avant publication, changez
`config.YOUTUBE_PRIVACY_STATUS` en `"private"` (section 6).

**Si le PC est éteint ou en veille à l'heure prévue** : les trois tâches sont configurées pour
rattraper le coup automatiquement.
- PC **éteint** → la vidéo/le short se génère **dès que vous rallumez le PC** (au lieu d'attendre
  le lendemain).
- PC en **veille** → Windows **réveille le PC** tout seul pour lancer la génération, puis il peut
  se rendormir normalement après.
- Si le PC reste éteint plusieurs jours d'affilée, un seul run de rattrapage se lance par tâche à la
  réactivation (pas un par jour manqué).

**Pour vérifier que les tâches existent / les modifier** : ouvrez le "Planificateur de tâches" Windows
(rechercher "Planificateur de tâches" dans le menu Démarrer) → cherchez `YouTubeAI-DailyVideo`,
`YouTubeAI-DailyShort` ou `YouTubeAI-DailyShort2`.
- Clic droit → "Exécuter" : lance une génération immédiatement, sans attendre l'heure prévue.
- Clic droit → "Désactiver" : met cette tâche en pause sans la supprimer.
- Onglet "Déclencheurs" → modifier l'heure si 9h/15h/20h ne vous convient pas.

## 3. Lancer une vidéo manuellement (sans attendre 9h)

Ouvrez PowerShell, puis :

```
cd C:\Users\ovila\youtube-ai-generator

# Genere tout (script, voix, visuels, sous-titres, miniature) SANS publier sur YouTube
python run_pipeline.py

# Genere ET publie automatiquement sur YouTube (en PUBLIC par defaut, voir config.YOUTUBE_PRIVACY_STATUS)
python run_pipeline.py --publish

# Imposer un sujet precis au lieu d'un sujet aleatoire
python run_pipeline.py --topic "how to stay disciplined when nobody is watching" --publish
```

Une vidéo de 15-20 minutes prend environ **1h à 1h30** à générer (le plus long est le montage vidéo).
Vous pouvez fermer PowerShell une fois la commande lancée si vous utilisez la tâche planifiée à la place —
mais pour un lancement manuel, laissez la fenêtre ouverte jusqu'à la fin (message `Termine.` affiché).

## 3bis. Lancer un Short (format vertical, ~50 secondes)

En plus des vidéos longues, le bot sait générer des **Shorts** : format portrait (1080×1920, comme
un Reel/TikTok), une seule idée courte et percutante au lieu d'un long récit, sous-titres adaptés à
un écran étroit. C'est un script séparé, `run_shorts_pipeline.py` :

```
cd C:\Users\ovila\youtube-ai-generator

# Genere un Short (~50s) SANS publier sur YouTube
python run_shorts_pipeline.py

# Genere ET publie automatiquement sur YouTube (en PUBLIC par defaut, tag #Shorts ajoute)
python run_shorts_pipeline.py --publish

# Imposer un sujet precis
python run_shorts_pipeline.py --topic "why discipline beats motivation" --publish

# Changer la duree cible (par defaut ~50s, voir aussi config.SHORTS_MAX_SECONDS)
python run_shorts_pipeline.py --seconds 40
```

Un Short prend environ **3 à 5 minutes** à générer (bien plus rapide qu'une vidéo longue, vu la durée).
Le résultat est sauvegardé dans `D:\YouTube Videos\<date>_short_<sujet>\short.mp4`, avec son
`metadata.txt` à côté, comme pour les vidéos longues.

Deux tâches planifiées dédiées (**"YouTubeAI-DailyShort"** à 15h et **"YouTubeAI-DailyShort2"** à 20h)
lancent déjà ça automatiquement, deux fois par jour — voir section 2.

## 4. Publication sur YouTube (configuré et actif depuis le 24/09/2026)

Compte Google utilisé : **`totovilaseque@gmail.com`**. `client_secret.json` et `token.json` sont en
place dans `C:\Users\ovila\youtube-ai-generator\`, les trois tâches planifiées publient automatiquement
**en public** chaque jour (voir section 2).

**⚠️ Piège rencontré au setup, à connaître si ça se reproduit (ex: après avoir change de PC, ou si
une vidéo atterrit soudain sur la mauvaise chaîne) :** si le compte Google associé gère **plusieurs
chaînes YouTube** (chaîne perso + chaîne(s) de marque), la première autorisation OAuth peut cibler la
mauvaise chaîne. Pire : supprimer juste `token.json` en local NE SUFFIT PAS pour corriger ça — Google
retient le choix de chaîne côté serveur et le réutilise silencieusement (aucune fenêtre de connexion
ne réapparaît, ça republie directement sur la même chaîne). **La vraie solution :**
1. Allez sur https://myaccount.google.com/permissions (connecté avec le compte concerné)
2. Trouvez l'app (ex: "YouTube AI Generator") → **Supprimer l'accès**
3. Relancez une commande de publication à la main : un écran de connexion **et de sélection de
   chaîne** doit réapparaître — choisissez la bonne chaîne cette fois.

**Autres points d'attention :**
- L'app OAuth est en statut **Testing** sur Google Cloud Console → le jeton (`token.json`) expire au
  bout de **7 jours**. Quand ça arrive, une commande manuelle (`python run_pipeline.py --publish` ou
  `python youtube_uploader.py <video> <titre>`) rouvrira une fenêtre de connexion pour renouveler
  `token.json` — rien à changer dans le code.
- Quota gratuit YouTube API : un upload coûte ~1600 unités sur les 10 000/jour offertes. Avec 3
  publications/jour (1 longue + 2 Shorts) ça consomme ~4800 unités/jour, large marge restante.
- Miniature personnalisée : nécessite un compte YouTube **vérifié par téléphone** (YouTube Studio →
  Paramètres → Chaîne → Fonctionnalités). Sans ça, `set_thumbnail` échoue silencieusement (juste un
  avertissement dans le log) et la vidéo garde une frame automatique comme miniature — n'affecte pas
  la publication elle-même.
- Pour reconfigurer depuis zéro avec un compte/projet différent, voici la procédure complète (gratuite) :
  1. https://console.cloud.google.com/ → créer un projet.
  2. "APIs et services" → activer **YouTube Data API v3** (bien vérifier que c'est le BON projet
     sélectionné en haut à gauche, et le BON compte Google connecté en haut à droite).
  3. "Écran de consentement OAuth" → type **Externe** → ajouter le compte cible dans **Test users**.
  4. "Identifiants" → **Créer des identifiants** → **OAuth client ID** → type **Application de bureau**.
  5. Télécharger le JSON, le renommer `client_secret.json`, le placer dans le dossier du projet.
  6. Supprimer l'ancien `token.json` s'il existe, puis lancer `python run_pipeline.py --publish` à la
     main pour se reconnecter (voir l'encadré ci-dessus si plusieurs chaînes sont en jeu).

## 5. Mettre en place l'identité de la chaîne (une seule fois, à la main)

Le dossier `branding_kit/` contient plusieurs propositions générées par IA. YouTube ne permet pas de changer
la photo de profil/bannière automatiquement par script — c'est un glisser-déposer dans YouTube Studio :

1. Allez sur https://studio.youtube.com/ → **Personnalisation** → **Image de marque**.
2. **Photo de profil** : choisissez une image dans `branding_kit\profile_pictures\` (elle sera recadrée
   en cercle automatiquement par YouTube).
3. **Bannière** : choisissez une image dans `branding_kit\banners\` (déjà au bon format 2560x1440).
4. **Nom de la chaîne** : `Elevate Your Self` (ou un autre choisi dans `branding_kit\channel_name_options.txt`).
5. **Description** : copiez le texte de `branding_kit\channel_description.txt` dans "Description" de la chaîne.

## 6. Ajuster les réglages

Tout se change dans `config.py` (ouvrable avec le Bloc-notes) :
- `TARGET_MINUTES_MIN` / `TARGET_MINUTES_MAX` : durée des vidéos longues (actuellement 15-20 min).
- `SHORTS_TARGET_SECONDS` / `SHORTS_MAX_SECONDS` : durée des Shorts (actuellement ~50s, plafond 59s).
- `TTS_VOICE` : la voix (liste d'alternatives en commentaire à côté).
- `YOUTUBE_PRIVACY_STATUS` : actuellement `"public"`. Repassez à `"private"` si vous voulez relire
  chaque vidéo avant de la publier vous-même dans YouTube Studio.
- `MUSIC_ENABLED` / `MUSIC_VOLUME` : musique de fond ambiante (générée localement, gratuite, sans
  droits d'auteur). `MUSIC_VOLUME = 0.08` par défaut (très discret) ; mettez `MUSIC_ENABLED = False`
  pour désactiver, ou régénérez de nouvelles pistes avec `python music_generator.py`.
- Les sujets de secours (si vous ne précisez pas `--topic`) sont dans `FALLBACK_TOPICS`, en haut de
  `script_generator.py` — ajoutez-en pour varier le contenu. Le bot évite déjà les répétitions tant
  que la liste n'est pas épuisée (fichier `output/used_topics.json` : supprimez-le pour reset la
  rotation manuellement).
- Les hooks/accroches (`HOOK_RULES` dans `script_generator.py`) contrôlent le style d'ouverture des
  scripts, orienté rétention (curiosity gap, pas de résolution immédiate) — à ajuster si le ton ne
  convient pas.

## 7. Problèmes courants

| Symptôme | Cause probable | Solution |
|---|---|---|
| `Impossible de contacter Ollama` | Ollama pas démarré | Ouvrez l'appli Ollama (icône dans la barre des tâches) ou redémarrez le PC |
| `PEXELS_API_KEY manquante` | Variable d'environnement effacée | `setx PEXELS_API_KEY "votre_cle"` puis rouvrez PowerShell |
| Erreur pendant `--publish` sur YouTube | `client_secret.json` absent, jeton expiré (7 jours), ou quota YouTube API dépassé | Voir section 4 ; le quota gratuit (10 000 unités/jour, ~1600/upload) se réinitialise à minuit heure Pacifique |
| Vidéo publiée sur la mauvaise chaîne | Compte Google avec plusieurs chaînes, mauvais choix retenu par Google | Voir l'encadré ⚠️ en section 4 (révoquer l'accès sur myaccount.google.com/permissions, pas juste supprimer `token.json`) |
| "Miniature non appliquée" (mais vidéo publiée quand même) | Compte YouTube pas vérifié par téléphone | Vérifiez le compte dans YouTube Studio → Paramètres → Chaîne, ou ajoutez la miniature à la main (fichier `thumbnail.jpg` dans le dossier de la vidéo) |
| Pas de musique de fond dans la vidéo | `assets/music/` vide ou `MUSIC_ENABLED = False` | `python music_generator.py` régénère les pistes ; vérifiez `config.MUSIC_ENABLED` |
| Le disque D: se remplit | Normal a terme (3 videos/jour, ~30-300 Mo chacune) | Supprimez ou archivez les anciens dossiers dans `D:\YouTube Videos` de temps en temps |

## 8. Arrêter complètement le bot

Planificateur de tâches Windows → clic droit sur chacune des 3 tâches (`YouTubeAI-DailyVideo`,
`YouTubeAI-DailyShort`, `YouTubeAI-DailyShort2`) → **Désactiver** (ou **Supprimer** pour les enlever
définitivement). Rien d'autre ne tourne en arrière-plan à part Ollama (sans danger, ne consomme rien
tant qu'aucun script ne lui demande de générer du texte).
