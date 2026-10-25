# Guide d'utilisation — Générateur vidéo YouTube IA

Ce guide explique comment faire vivre le bot **sans avoir besoin de moi (Claude)**. Tout tourne sur GitHub
Actions, gratuitement, avec des outils standards (Python, Ollama, ffmpeg) ; le PC ne sert qu'aux tests.

## 1. Où est tout stocké

| Quoi | Où |
|---|---|
| Le programme (le "bot") | Dépôt GitHub `MaxxouTLR/youtube-ai-generator`, branche **`main`** (copie locale : `%USERPROFILE%\youtube-ai-generator`) |
| Ce qui tourne chaque jour | Workflow GitHub Actions `.github/workflows/daily-videos.yml` (onglet **Actions** du dépôt) |
| Les clés (Azure, Pexels, YouTube) | Secrets GitHub Actions du dépôt (et variables d'environnement locales pour les tests) |
| Les vidéos finies (runs locaux) | `D:\YouTube Videos\<date>_<sujet>\` (un dossier par vidéo : `video.mp4`, `thumbnail.jpg`, `metadata.txt`). Sur GitHub Actions, dossier jetable du runner : la vidéo est déjà sur YouTube. |
| L'historique des sujets/titres | `output/used_topics.json`, `output/used_titles.json`, `output/last_auto_run.json` (recommités par le workflow à chaque run) |
| Les assets de chaîne (logo, bannière, description) | `%USERPROFILE%\youtube-ai-generator\branding_kit\` (local uniquement, hors Git) |
| Les réglages (voix, durée, niche...) | `config.py` |

> **Ce dépôt = la chaîne YouTube anglaise uniquement.** Le TikTok français « Dossiers d'Histoire »
> est un projet séparé (branche `demo-fr`, dossier local `tiktok-dossiers`). Ne pas faire
> `git checkout demo-fr` dans le dossier de la chaîne YouTube, ni fusionner les deux branches.

## 2. Ce qui tourne automatiquement, sans rien faire

Tout tourne sur **GitHub Actions** (le PC peut rester éteint). Le workflow `Daily YouTube videos`
se déclenche 3 fois par jour (heure de Paris, été comme hiver) :

- **8h** — Short (~20s, format portrait, voir section 3bis)
- **13h** — Short
- **19h** — vidéo longue (15-20 min)

Chaque run écrit un nouveau script, génère la voix, la musique, les visuels, les sous-titres, le
titre/description/tags, la miniature, puis **publie automatiquement sur YouTube en public**.

**Publication en PUBLIC directement, sans relecture** (activé le 24/09/2026, voir section 4) —
si vous voulez repasser en privé pour relire avant publication, changez
`config.YOUTUBE_PRIVACY_STATUS` en `"private"` (section 6).

**Bon à savoir sur le planificateur GitHub :**
- Un cron GitHub ne rattrape jamais un créneau manqué, et peut avoir 50-70 min de retard. Le
  workflow accepte donc un déclenchement jusqu'à 180 min autour du créneau, et
  `output/last_auto_run.json` empêche de publier deux fois le même créneau.
- Il arrive que le planificateur reste silencieux plusieurs heures ; pousser un commit le relance.

**Pour vérifier / lancer à la main** : sur GitHub → onglet **Actions** → `Daily YouTube videos` →
**Run workflow**. Choisissez `short` ou `long`, et décochez **Publier** pour un run de test sans
publication réelle.

**Pour mettre en pause** : onglet **Actions** → `Daily YouTube videos` → menu `...` →
**Disable workflow** (et **Enable workflow** pour reprendre).

## 3. Lancer une vidéo en local (test / développement)

En production rien n'est à lancer à la main (section 2). Pour tester une modification sur le PC
(Ollama installé, variables `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`, `PEXELS_API_KEY` définies),
ouvrez PowerShell, puis :

```
cd $env:USERPROFILE\youtube-ai-generator

# Genere tout (script, voix, visuels, sous-titres, miniature) SANS publier sur YouTube
python run_pipeline.py

# Genere ET publie automatiquement sur YouTube (en PUBLIC par defaut, voir config.YOUTUBE_PRIVACY_STATUS)
python run_pipeline.py --publish

# Imposer un sujet precis au lieu d'un sujet aleatoire
python run_pipeline.py --topic "how to stay disciplined when nobody is watching" --publish
```

Une vidéo de 15-20 minutes prend environ **1h à 1h30** à générer (le plus long est le montage vidéo).
Laissez la fenêtre ouverte jusqu'à la fin (message `Termine.` affiché).

## 3bis. Lancer un Short (format vertical, ~20 secondes)

En plus des vidéos longues, le bot sait générer des **Shorts** : format portrait (1080×1920), une seule idée courte et percutante au lieu d'un long récit, sous-titres adaptés à
un écran étroit, montage dynamique (un clip par phrase, `montage.py`). C'est un script séparé, `run_shorts_pipeline.py` :

```
cd $env:USERPROFILE\youtube-ai-generator

# Genere un Short (~20s) SANS publier sur YouTube
python run_shorts_pipeline.py

# Genere ET publie automatiquement sur YouTube (en PUBLIC par defaut, tag #Shorts ajoute)
python run_shorts_pipeline.py --publish

# Imposer un sujet precis
python run_shorts_pipeline.py --topic "why discipline beats motivation" --publish

# Changer la duree cible (par defaut ~20s, voir aussi config.SHORTS_MAX_SECONDS)
python run_shorts_pipeline.py --seconds 40
```

Un Short prend quelques minutes à générer (bien plus rapide qu'une vidéo longue, vu la durée).
Le résultat est sauvegardé dans `D:\YouTube Videos\<date>_short_<sujet>\short.mp4`, avec son
`metadata.txt` à côté, comme pour les vidéos longues.

Le workflow GitHub Actions lance déjà ça automatiquement à 8h et 13h — voir section 2.

## 4. Publication sur YouTube (configuré et actif depuis le 24/09/2026)

Compte Google utilisé : **`totovilaseque@gmail.com`**. Sur GitHub Actions, `client_secret.json` et
`token.json` sont recréés à chaque run depuis les secrets `YOUTUBE_CLIENT_SECRET_B64` et
`YOUTUBE_TOKEN_B64` (puis supprimés en fin de run) ; en local ils sont dans
`%USERPROFILE%\youtube-ai-generator\` (hors Git).

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
- L'app OAuth est en statut **Production** sur Google Cloud Console (indispensable pour GitHub
  Actions : en statut Testing le jeton expire au bout de 7 jours). Si le jeton est un jour révoqué,
  relancez une publication en local (`python run_pipeline.py --publish`) pour régénérer
  `token.json`, puis encodez-le en base64 dans le secret GitHub `YOUTUBE_TOKEN_B64`.
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

Tout se change dans `config.py`, puis commit + push sur `main` (pris en compte au run suivant) :
- `TARGET_MINUTES_MIN` / `TARGET_MINUTES_MAX` : durée des vidéos longues (actuellement 15-20 min).
- `SHORTS_TARGET_SECONDS` / `SHORTS_MAX_SECONDS` : durée des Shorts (actuellement ~20s, plafond 59s).
- `TTS_VOICE_POOL` : voix Azure utilisées (actuellement une seule, Andrew Multilingual à +12 %).
- Les horaires de publication se changent dans `.github/workflows/daily-videos.yml` (les deux lignes
  `cron` et la liste des créneaux `"long:19" "short:08" "short:13"`).
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
| Aucune vidéo publiée à l'heure prévue | Planificateur GitHub en retard ou silencieux | Onglet Actions : vérifier les runs ; lancer à la main (**Run workflow**) ; pousser un commit relance le planificateur |
| Run rouge dans l'onglet Actions | Erreur réseau/API (3 tentatives déjà faites) ou secret manquant/expiré | Ouvrir le run pour lire le log ; vérifier les secrets du dépôt |
| `Impossible de contacter Ollama` (en local) | Ollama pas démarré | Ouvrez l'appli Ollama (icône dans la barre des tâches) ou redémarrez le PC |
| `PEXELS_API_KEY manquante` (en local) | Variable d'environnement effacée | `setx PEXELS_API_KEY "votre_cle"` puis rouvrez PowerShell |
| Erreur pendant `--publish` sur YouTube | `client_secret.json` absent, jeton révoqué, ou quota YouTube API dépassé | Voir section 4 ; le quota gratuit (10 000 unités/jour, ~1600/upload) se réinitialise à minuit heure Pacifique |
| Vidéo publiée sur la mauvaise chaîne | Compte Google avec plusieurs chaînes, mauvais choix retenu par Google | Voir l'encadré ⚠️ en section 4 (révoquer l'accès sur myaccount.google.com/permissions, pas juste supprimer `token.json`) |
| "Miniature non appliquée" (mais vidéo publiée quand même) | Compte YouTube pas vérifié par téléphone | Vérifiez le compte dans YouTube Studio → Paramètres → Chaîne, ou ajoutez la miniature à la main (fichier `thumbnail.jpg` dans le dossier de la vidéo) |
| Pas de musique de fond dans la vidéo | `assets/music/` vide ou `MUSIC_ENABLED = False` | `python music_generator.py` régénère les pistes ; vérifiez `config.MUSIC_ENABLED` |
| Le disque D: se remplit (runs locaux) | Chaque test local garde sa vidéo (~30-300 Mo) | Supprimez ou archivez les anciens dossiers dans `D:\YouTube Videos` de temps en temps |

## 8. Arrêter complètement le bot

Sur GitHub → onglet **Actions** → `Daily YouTube videos` → menu `...` → **Disable workflow**. Plus
rien ne se publie tant qu'il n'est pas réactivé. Les anciennes tâches planifiées Windows
(`YouTubeAI-*`, lancées via `run_pipeline_safe.ps1`) ne sont plus utilisées : si elles existent
encore sur le PC, désactivez-les pour éviter un double run.
