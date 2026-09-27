"""Genere un script de video longue duree via un modele Ollama local (gratuit, sans cle API)."""
import json
import os
import re
import urllib.request
import config


STYLE_RULES = """Mandatory style rules:
- VERY short sentences (5 to 12 words on average). One idea per sentence.
- Vary the rhythm: a few punchy sentences, then ONE longer sentence that breathes, then short again.
- Use concrete, vivid examples (a scene, a character, a specific moment) instead of repeating abstract concepts.
- Ask the viewer direct questions from time to time.
- STRICTLY forbidden to repeat the same sentence, phrase or metaphor twice. Every sentence must bring a new idea.
- No lists, no "first/second/third". One flowing narration, like telling a story."""

HOOK_RULES = """Retention rules (this is a watch-time-optimized script, every line must earn the next one):
- NEVER open with a generic line like "have you ever felt...", "in today's world...", "we all know that...".
- Open a curiosity gap: tease a specific, concrete outcome or twist without revealing it yet
  ("what happened next changed how I see..." / "there's one reason most of them quit, and it's not what you think").
- Do NOT give away the main insight immediately. Delay the payoff so the viewer has a reason to keep listening.
- Use specific numbers, ages, timeframes or details instead of vague generalities (specificity keeps attention).
- Every few sentences, plant a small forward-pointing line ("but here's the part nobody talks about",
  "and it gets worse before it gets better") to pull the viewer into the next moment."""

PROMPT_TEMPLATE = """You are a scriptwriter specialized in long-form YouTube motivation and self-improvement videos,
in the style of the best US channels (punchy, highly visual, never flat, optimized for maximum watch time).

Write the BEGINNING of a narration script for a long YouTube video on the following topic: "{topic}".

{style_rules}

{hook_rules}

Structure of this beginning:
- The first 2 sentences must be a scroll-stopping curiosity gap (see retention rules), zero context given yet.
- Then a mini-story or concrete example that illustrates the problem, WITHOUT resolving the opening tease.
- End on an open loop: a specific question or promise that makes the viewer need to know what happens next.

Write ONLY the text to be read aloud (no section titles, no stage directions, no markdown, no part numbers).
Do NOT conclude the video, this is only the beginning. Write in English.
"""

CONTINUE_TEMPLATE = """Here is the script of a motivation YouTube video, written so far:

---
{previous}
---

{style_rules}

{hook_rules}

Continue this script, developing a NEW argument, a NEW story or a NEW concrete example
related to the topic "{topic}". Do not reuse any sentence, phrase or image already present above.
Start this new section with a RE-HOOK: a fresh curiosity gap, bold claim or open question that
re-captures attention as if a distracted viewer just tuned back in (do not just say "now let's talk about").
End this section on another open loop that pulls into the next part.
{conclude_instruction}
Write ONLY the continuation of the text to be read aloud (no titles, no markdown, no recap of what came before). Write in English.
"""

CONCLUDE_INSTRUCTION = (
    "This is the LAST part: resolve the open loops from earlier, end with a strong conclusion that sums up "
    "the message, and clearly invite the viewer to subscribe to the channel."
)

SHORT_PROMPT_TEMPLATE = """You are a scriptwriter specialized in viral YouTube Shorts / TikTok style motivation content,
in the style of the best US creators (punchy, highly visual, never flat, optimized to prevent any swipe-away).

Write a COMPLETE, SELF-CONTAINED narration script for a {seconds}-second vertical short video
on the following topic: "{topic}".

{style_rules}

{hook_rules}

Structure (all of it, in this one short script):
- First sentence (under 2 seconds to read): an immediate, scroll-stopping hook with an open loop
  the viewer needs resolved (a specific promise, a surprising claim, a "wait for it" moment).
- One single sharp idea, developed with ONE concrete example or mini-story. Do not try to cover multiple ideas.
  Do NOT resolve the opening hook yet — keep the tension until the very end.
- Last sentence: resolve the opening hook AND deliver a punchy takeaway line that could work as a caption.

Target length: about {words} words, NOT more. Write ONLY the text to be read aloud
(no section titles, no stage directions, no markdown, no hashtags). Write in English.
"""

FALLBACK_TOPICS = [
    "why discipline beats motivation",
    "how to rebuild yourself after failure",
    "the power of patience in a world that moves too fast",
    "how to stop procrastinating: the method that actually works",
    "the habits of people who succeed in the long run",
    "how to leave your comfort zone without burning out",
    "the power of quiet discipline",
    "why most people give up right before they would have succeeded",
    "how to stop caring what other people think of you",
    "the danger of comparing your life to other people's highlight reel",
    "how to turn your anxiety into fuel instead of fear",
    "why doing the hard thing first changes everything",
    "how to build self-respect when nobody is clapping for you",
    "the myth of overnight success and what it hides",
    "how to keep going when you see zero results",
    "why saying no is the most underrated skill",
    "how to stop waiting for the perfect moment to start",
    "the hidden cost of a comfortable life",
    "how to forgive yourself for wasted years",
    "why small daily habits beat big dramatic changes",
    "how to deal with people who don't believe in you",
    "the difference between being busy and being productive",
    "how to rebuild your confidence from zero",
    "why competition with yourself matters more than with others",
    "how to stay consistent when motivation disappears",
    "the real reason you keep procrastinating on your goals",
    "how to turn failure into your biggest advantage",
    "why solitude makes you stronger, not weaker",
    "how to set boundaries without feeling guilty",
    "the one habit that separates winners from everyone else",
]

TOPIC_HISTORY_FILE = os.path.join(config.OUTPUT_DIR, "used_topics.json")
# File d'attente prioritaire : sujets a utiliser en premier, dans l'ordre, avant de repasser sur la
# generation Ollama habituelle. Alimentee manuellement (ex: idees suggerees par YouTube Studio) - le
# workflow GitHub Actions commite ce fichier comme used_topics.json pour qu'il survive entre deux runs
# ephemeres.
PRIORITY_TOPICS_FILE = os.path.join(config.OUTPUT_DIR, "priority_topics.json")
# A 8 videos/jour (7 shorts + 1 longue), les 30 sujets de FALLBACK_TOPICS seraient epuises en moins
# de 4 jours si on tournait juste dessus. On genere donc un nouveau sujet via Ollama a chaque appel
# (source infinie), et FALLBACK_TOPICS ne sert plus que d'exemples de style + repli si Ollama echoue.
MAX_TOPIC_HISTORY = 400  # ~50 jours d'historique a cette cadence, suffisant pour eviter les doublons proches

TOPIC_GENERATION_PROMPT = """You invent topic ideas for a motivation / self-improvement YouTube channel.

Topics are short lowercase phrases like these (style examples, do not reuse them):
{examples}

Do NOT reuse any of these already-used topics, even reworded:
{recent_used}

Give exactly ONE new topic idea, 5 to 15 words, lowercase, no ending punctuation, no quotes,
no numbering, nothing else in your reply.
"""


def _generate_new_topic(used: list[str]) -> str:
    """Demande a Ollama un sujet inedit, jamais utilise recemment (source infinie de sujets,
    contrairement a une simple rotation sur une liste fixe)."""
    recent = used[-60:]
    examples = "\n".join(f"- {t}" for t in FALLBACK_TOPICS[:8])
    recent_block = "\n".join(f"- {t}" for t in recent) if recent else "(none yet)"
    raw = _call_ollama_with_retry(
        TOPIC_GENERATION_PROMPT.format(examples=examples, recent_used=recent_block), attempts=2
    )
    topic = raw.strip().splitlines()[0].strip().strip('."\'').lower()
    topic = re.sub(r"^(topic|idea)\s*:\s*", "", topic)
    return topic


def _pop_priority_topic() -> str | None:
    """Retire et retourne le premier sujet de la file d'attente prioritaire, ou None si vide/absente."""
    if not os.path.exists(PRIORITY_TOPICS_FILE):
        return None
    try:
        with open(PRIORITY_TOPICS_FILE, "r", encoding="utf-8") as f:
            queue = json.load(f)
    except Exception:
        return None
    if not queue:
        return None
    topic = queue.pop(0)
    with open(PRIORITY_TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False)
    return topic


def _pick_topic() -> str:
    """Retourne d'abord les sujets de la file prioritaire (s'il y en a), sinon un sujet inedit genere
    par Ollama (evite les repetitions recentes). Si Ollama ne repond pas ou ne varie pas (glitch),
    repli sur une rotation classique de FALLBACK_TOPICS."""
    import random

    priority = _pop_priority_topic()
    if priority:
        used = []
        if os.path.exists(TOPIC_HISTORY_FILE):
            try:
                with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
                    used = json.load(f)
            except Exception:
                used = []
        used.append(priority)
        used = used[-MAX_TOPIC_HISTORY:]
        os.makedirs(os.path.dirname(TOPIC_HISTORY_FILE), exist_ok=True)
        with open(TOPIC_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(used, f, ensure_ascii=False)
        return priority

    used = []
    if os.path.exists(TOPIC_HISTORY_FILE):
        try:
            with open(TOPIC_HISTORY_FILE, "r", encoding="utf-8") as f:
                used = json.load(f)
        except Exception:
            used = []

    topic = ""
    for _ in range(3):
        candidate = _generate_new_topic(used)
        if candidate and candidate not in used and 15 <= len(candidate) <= 120:
            topic = candidate
            break

    if not topic:
        available = [t for t in FALLBACK_TOPICS if t not in used]
        if not available:
            available = FALLBACK_TOPICS
        topic = random.choice(available)

    used.append(topic)
    used = used[-MAX_TOPIC_HISTORY:]

    os.makedirs(os.path.dirname(TOPIC_HISTORY_FILE), exist_ok=True)
    with open(TOPIC_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(used, f, ensure_ascii=False)
    return topic


KEYWORD_PROMPT = """Read this short excerpt of narration from a motivation video:

"{segment}"

Give ONE short visual search phrase (2 to 4 words) describing a concrete, filmable stock-footage scene
that matches the mood or content of this excerpt. Think concrete and visual: "man walking city street",
"sunrise over mountains", "person writing notebook", "crowded office workers", "empty road at night".
Never use abstract words like "motivation", "discipline" or "success". Reply with ONLY the phrase, nothing else.
"""


def generate_visual_keyword(segment_text: str) -> str:
    """Demande a Ollama un mot-cle de recherche visuelle pertinent pour ce passage du script."""
    try:
        raw = _call_ollama(KEYWORD_PROMPT.format(segment=segment_text[:600]))
    except Exception:
        return "cinematic nature background"
    keyword = raw.strip().splitlines()[0].strip().strip('."\'')
    keyword = re.sub(r"^(phrase|answer|scene)\s*:\s*", "", keyword, flags=re.IGNORECASE)
    return keyword[:80] if keyword else "cinematic nature background"


# Plusieurs gabarits de titre distincts, pas juste des synonymes du meme moule "Are you...?".
# Le modele 3B a tendance a retomber sur LE style le plus fortement suggere dans le prompt, meme
# quand on lui demande explicitement de "varier" - constate en pratique (titres quasi tous identiques
# en structure, feedback utilisateur direct le 27/09/2026). Fix : le CODE choisit un style au hasard
# (pondere pour garder "question_tension" dominant car c'est le style avec la meilleure retention
# mesuree, cf. analyse du 26/09/2026 dans les notes projet) et n'injecte QUE ce style dans le prompt,
# ce qui force mecaniquement la variete au lieu d'esperer que le modele varie de lui-meme.
TITLE_STYLES = [
    {
        "name": "question_tension",
        "weight": 3,
        "guidance": 'A direct SECOND-PERSON question ("Are you...", "Why do you...", "Are you actually...") '
                    "paired with a paradox or tension word (trapped, illusion, lying, sabotaging, addicted, "
                    "broken, lie, prison).",
        "example": "Are You Trapped in the Perfect Illusion?",
    },
    {
        "name": "you_are_not",
        "weight": 2,
        "guidance": 'A reframe in the form "You\'re Not X, You\'re Just Y" that challenges a common '
                    "negative self-label with a more honest, sympathetic explanation.",
        "example": "You're Not Lazy, You're Just Terrified",
    },
    {
        "name": "real_reason",
        "weight": 2,
        "guidance": 'A curiosity-gap statement in the form "The Real Reason You Keep [X]-ing" or '
                    '"Nobody Tells You This About [X]", implying a hidden truth the video reveals.',
        "example": "The Real Reason You Keep Sabotaging Your Own Success",
    },
    {
        "name": "stop_start",
        "weight": 2,
        "guidance": 'A short, imperative two-part command in the form "Stop [X]. Start [Y]." that '
                    "contrasts a common bad habit with the better alternative taught in the video.",
        "example": "Stop Chasing Motivation. Start Building Discipline.",
    },
    {
        "name": "numbered_signs",
        "guidance": "A specific-number list-style title in the form \"N Signs You're [X] (And Don't Know It)\".",
        "weight": 2,
        "example": "3 Signs You're Sabotaging Your Own Success",
    },
]


def _pick_title_style() -> dict:
    import random
    return random.choices(TITLE_STYLES, weights=[s["weight"] for s in TITLE_STYLES], k=1)[0]


METADATA_PROMPT = """You are a YouTube SEO expert for a motivation / self-improvement channel.

Here is the video script:
\"\"\"
{script}
\"\"\"

Generate optimized YouTube metadata for this exact video. Follow this EXACT format and nothing else,
no markdown, no extra commentary, no quotation marks around the values:

TITLE: a punchy, curiosity-driven title under 90 characters that accurately reflects the video content.
Required style for THIS title: {title_style_guidance}
Example (do not reuse, just illustrates the style): "{title_style_example}".
Do NOT reuse any of these titles already used on the channel, not even reworded with a synonym:
{recent_titles}
DESCRIPTION: a 3 to 5 sentence description in plain text: hook the reader in the first sentence, summarize what they will get from the video, end with a call to subscribe for more
TAGS: 8 to 12 comma-separated relevant lowercase keywords, no hashtags, no numbering
"""

TITLE_HISTORY_FILE = os.path.join(config.OUTPUT_DIR, "used_titles.json")
MAX_TITLE_HISTORY = 60  # assez pour couvrir plusieurs semaines a cette cadence sans fichier illimite


def _load_used_titles() -> list[str]:
    if os.path.exists(TITLE_HISTORY_FILE):
        try:
            with open(TITLE_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_used_title(title: str, used: list[str]) -> None:
    used = (used + [title])[-MAX_TITLE_HISTORY:]
    os.makedirs(os.path.dirname(TITLE_HISTORY_FILE), exist_ok=True)
    with open(TITLE_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(used, f, ensure_ascii=False)


def _extract_field(text: str, field: str) -> str:
    match = re.search(rf"{field}\s*:\s*(.+?)(?=\n[A-Z ]+:|\Z)", text, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def generate_metadata(topic: str, script: str) -> dict:
    """Genere titre/description/tags optimises via Ollama a partir du script reel. Retombe sur des
    valeurs generiques si le modele ne repond pas dans le format attendu. Reessaie si le titre est un
    doublon exact d'un titre recent (le modele 3B a tendance a retomber sur les memes exemples du
    prompt, ex: 'Are You Sabotaging Your Dreams?' genere deux fois de suite le 26/09/2026, et
    'Are You Trapped in the Perfect Illusion?' reproduit a l'identique le 27/09/2026 - l'exemple donne
    dans le prompt pour le style question_tension EST cette phrase, le modele l'a recopiee telle
    quelle malgre la consigne explicite de ne pas la reutiliser)."""
    used_titles = _load_used_titles()
    used_titles_lower = {t.strip().lower() for t in used_titles}
    all_example_titles_lower = {s["example"].strip().lower() for s in TITLE_STYLES}
    recent_titles_block = "\n".join(f"- {t}" for t in used_titles[-20:]) if used_titles else "(none yet)"

    raw, title, description, tags_raw = "", "", "", ""
    is_duplicate = True
    for _ in range(5):
        style = _pick_title_style()
        try:
            raw = _call_ollama(METADATA_PROMPT.format(
                script=script[:2000], recent_titles=recent_titles_block,
                title_style_guidance=style["guidance"], title_style_example=style["example"],
            ))
        except Exception:
            raw = ""
        title = _extract_field(raw, "TITLE").strip('"')
        description = _extract_field(raw, "DESCRIPTION").strip('"')
        tags_raw = _extract_field(raw, "TAGS")
        title_lower = title.strip().lower()
        # Rejette aussi bien un doublon d'un titre deja publie qu'un simple recopiage verbatim de
        # l'exemple donne dans le prompt (qui n'est peut-etre pas encore dans used_titles s'il s'agit
        # d'un exemple different de celui reellement deja publie, mais reste un signe que le modele
        # n'a rien invente).
        is_duplicate = (not title) or title_lower in used_titles_lower or title_lower in all_example_titles_lower
        if not is_duplicate:
            break

    if is_duplicate:
        # Tous les essais ont produit un titre vide ou deja utilise/copie de l'exemple : mieux vaut
        # un titre generique jamais publie qu'un vrai doublon de contenu sur la chaine.
        title = f"{topic.strip().capitalize()} | Motivation"
    if not description:
        description = script[:400] + "..."

    _save_used_title(title, used_titles)

    tags = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
    if not tags:
        tags = ["motivation", "self improvement", "mindset", "personal development"]

    hashtag_pool = tags[:3] + ["motivation", "selfimprovement"]
    seen, hashtags = set(), []
    for t in hashtag_pool:
        tag = re.sub(r"[^a-z0-9]", "", t.lower())
        if tag and tag not in seen:
            seen.add(tag)
            hashtags.append(f"#{tag}")

    # Bloc produit/affiliation optionnel (config.PRODUCT_CTA) : vide par defaut, n'affecte aucune
    # video tant qu'il n'est pas rempli. Place AVANT les hashtags (les hashtags doivent rester la
    # toute derniere ligne pour que YouTube les affiche comme tags cliquables).
    cta_block = f"\n\n{config.PRODUCT_CTA}" if config.PRODUCT_CTA else ""
    full_description = f"{description}{cta_block}\n\n{' '.join(hashtags)}"
    return {"title": title[:100], "description": full_description[:5000], "tags": tags[:15]}


def _word_target(minutes: int) -> int:
    # ~140 mots/minute pour une narration TTS naturelle
    return minutes * 140


def _call_ollama(prompt: str) -> str:
    payload = json.dumps({
        "model": config.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        # num_ctx/num_predict explicites : sans ca Ollama peut appliquer des defauts bas
        # (historiquement 2048 ctx / 128 tokens de sortie) qui coupent une continuation en plein
        # milieu et la font ressortir vide apres nettoyage -> script bien plus court que la cible.
        "options": {"temperature": 0.85, "num_ctx": 4096, "num_predict": 800},
    }).encode("utf-8")

    req = urllib.request.Request(
        config.OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("response", "").strip()


def _call_ollama_with_retry(prompt: str, attempts: int = 3) -> str:
    """Reessaie un appel Ollama qui renvoie une reponse vide (glitch ponctuel observe en prod) :
    une seule reponse vide ne doit pas raccourcir toute la video de plusieurs minutes."""
    for attempt in range(1, attempts + 1):
        text = _call_ollama(prompt)
        if text.strip():
            return text
        print(f"    [warn] Reponse Ollama vide (essai {attempt}/{attempts}), nouvelle tentative...")
    return ""


def _clean_script(text: str) -> str:
    text = re.sub(r"^#+.*$", "", text, flags=re.MULTILINE)   # titres markdown
    text = re.sub(r"\*\*|\*|__|_", "", text)                    # gras/italique
    text = re.sub(r"^\s*\d+[\.\)]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def generate_script(topic: str | None = None, minutes: int | None = None) -> tuple[str, str]:
    """Retourne (topic, script_text). Genere par sections successives jusqu'a la longueur cible.
    Leve RuntimeError si Ollama n'est pas joignable."""
    import random
    topic = topic or _pick_topic()
    minutes = minutes or random.randint(config.TARGET_MINUTES_MIN, config.TARGET_MINUTES_MAX)
    target_words = _word_target(minutes)
    # Marge large : chaque section n'ajoute souvent que 150-300 mots avec un modele 3B,
    # il en faut donc facilement 15-20 pour une video de 15-20 min. L'ancienne limite de 24
    # etait deja suffisante en theorie, mais laisse peu de marge si quelques sections echouent.
    max_sections = 40
    max_consecutive_failures = 3

    try:
        raw = _call_ollama_with_retry(
            PROMPT_TEMPLATE.format(topic=topic, style_rules=STYLE_RULES, hook_rules=HOOK_RULES)
        )
        script = _clean_script(raw)
        print(f"    Section 1: {len(script.split())} mots (cumul)")

        sections = 1
        consecutive_failures = 0
        while len(script.split()) < target_words and sections < max_sections:
            sections += 1
            remaining_words = target_words - len(script.split())
            about_to_conclude = remaining_words < _word_target(2)  # < ~2 min restantes
            prompt = CONTINUE_TEMPLATE.format(
                previous=script[-2000:],
                topic=topic,
                style_rules=STYLE_RULES,
                hook_rules=HOOK_RULES,
                conclude_instruction=CONCLUDE_INSTRUCTION if about_to_conclude else "",
            )
            continuation = _clean_script(_call_ollama_with_retry(prompt))
            if not continuation:
                consecutive_failures += 1
                print(f"    [warn] Section {sections} vide malgre les tentatives "
                      f"({consecutive_failures}/{max_consecutive_failures} echecs consecutifs)")
                if consecutive_failures >= max_consecutive_failures:
                    break
                continue
            consecutive_failures = 0
            script = f"{script}\n\n{continuation}"
            print(f"    Section {sections}: {len(script.split())} mots (cumul, cible {target_words})")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "Impossible de contacter Ollama (http://localhost:11434). "
            "Verifie qu'Ollama tourne (`ollama serve`) et que le modele est telecharge "
            f"(`ollama pull {config.OLLAMA_MODEL}`)."
        ) from exc

    if len(script.split()) < 50:
        raise RuntimeError("Le script genere est trop court, reessaie ou verifie le modele Ollama.")

    word_count = len(script.split())
    if word_count < target_words * 0.8:
        print(f"    [warn] Script final ({word_count} mots) nettement sous la cible "
              f"({target_words} mots) malgre les tentatives : la video sera plus courte que 15-20 min.")
    return topic, script


def _truncate_to_target(script: str, target_words: int, tolerance: float = 1.3) -> str:
    """Le modele 3B suit mal la consigne de longueur sur un Short (un seul appel, pas de boucle de
    controle comme generate_script) : mesure sur un run reel, cible ~117 mots -> 253 generes (2x trop
    long, video hors gabarit Shorts). Tronque en gardant le debut jusqu'a la cible, PLUS la toute
    derniere phrase (la resolution du hook d'ouverture, cruciale pour HOOK_RULES) meme si ca depasse
    legerement."""
    if len(script.split()) <= target_words * tolerance:
        return script

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script.replace("\n", " ")) if s.strip()]
    if len(sentences) <= 2:
        return script

    last_sentence = sentences[-1]
    kept, kept_words = [], 0
    for s in sentences[:-1]:
        w = len(s.split())
        if kept and kept_words + w > target_words:
            break
        kept.append(s)
        kept_words += w
    kept.append(last_sentence)
    return " ".join(kept)


def generate_short_script(topic: str | None = None, seconds: int | None = None) -> tuple[str, str]:
    """Genere un script COMPLET et autonome pour un Short (une seule idee, pas de suite).
    Contrairement a generate_script, un seul appel Ollama suffit vu la longueur visee."""
    import random
    topic = topic or _pick_topic()
    seconds = seconds or config.SHORTS_TARGET_SECONDS
    words = _word_target(seconds / 60)

    try:
        raw = _call_ollama_with_retry(
            SHORT_PROMPT_TEMPLATE.format(
                topic=topic, style_rules=STYLE_RULES, hook_rules=HOOK_RULES, seconds=seconds, words=words
            )
        )
        script = _clean_script(raw)
    except Exception as exc:
        raise RuntimeError(
            "Impossible de contacter Ollama (http://localhost:11434). "
            "Verifie qu'Ollama tourne (`ollama serve`) et que le modele est telecharge "
            f"(`ollama pull {config.OLLAMA_MODEL}`)."
        ) from exc

    words_before = len(script.split())
    script = _truncate_to_target(script, words)
    if len(script.split()) < words_before:
        print(f"    [warn] Script tronque de {words_before} a {len(script.split())} mots "
              f"(cible {words}, le modele a largement depasse la consigne de longueur)")

    if len(script.split()) < 15:
        raise RuntimeError("Le script court genere est trop court, reessaie ou verifie le modele Ollama.")
    return topic, script


if __name__ == "__main__":
    import os
    import datetime

    topic, script = generate_script()
    os.makedirs(config.SCRIPTS_DIR, exist_ok=True)
    filename = f"{datetime.datetime.now():%Y%m%d_%H%M%S}_script.txt"
    path = os.path.join(config.SCRIPTS_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"SUJET: {topic}\n\n{script}")
    print(f"Script genere ({len(script.split())} mots) -> {path}")
