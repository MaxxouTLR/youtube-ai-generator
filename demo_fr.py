"""Demo chaine FR histoire, style "dossier" : epidemie dansante de Strasbourg (1518).

Faits verifies sur fr.wikipedia.org/wiki/Épidémie_dansante_de_1518 : debut le 15 juillet 1518 ; 34 danseurs en une
semaine et ~400 en un mois SELON PARACELSE (recit posterieur) ; diagnostic "sang trop chaud" ; scene en bois et
musiciens payes par la ville ; danse publique interdite ; pelerinage a la chapelle Saint-Vit pres de Saverne ;
aucun temoin contemporain ne mentionne de morts.

    python demo_fr.py <dossier_sortie>      (voix imposee par TTS_VOICE / TTS_RATE, cles Azure requises)
"""
import json
import os
import sys

import dossier_video
import voice_generator

BEATS = [
    {"say": "Juillet 1518, à Strasbourg.", "led": "1518", "led_sub": "Strasbourg", "icon": "🏰"},
    {"say": "Une femme sort dans la rue, et se met à danser.", "title": "Une femme se met à *danser.*", "icon": "💃"},
    {"say": "Elle ne s'arrête plus.", "title": "Elle ne *s'arrête plus.*", "flash": True},
    {"say": "Une semaine plus tard, ils sont trente-quatre.", "title": "Une semaine plus tard", "array": {"icon": "💃", "n": 34}},
    {"say": "Un mois après, près de quatre cents.", "led": "400", "led_sub": "danseurs", "stamp": "Selon la légende", "stamp_at": 1.1},
    {"say": "Le plus fou ? La réponse des autorités.", "title": "Le plus fou ?", "icon": "🏛️"},
    {"say": "Les médecins accusent un sang trop chaud.", "title": "Diagnostic : un *sang trop chaud.*", "icon": "🩸"},
    {"say": "Leur remède : faire danser les malades encore plus.", "title": "Le remède ? *Danser encore plus.*", "flash": True},
    {"say": "La ville construit une scène en bois, et paie des musiciens.", "title": "Une scène. Des *musiciens.*", "icon": "🎺", "stamp": "Payé par la ville"},
    {"say": "Sauf que ça ne marche pas.", "title": "*Sauf que…*", "flash": True},
    {"say": "Alors on interdit de danser en public.", "icon": "🚫", "stamp": "Interdit", "stamp_at": 0.5},
    {"say": "Et les malades partent en pèlerinage près de Saverne.", "title": "Pèlerinage à *Saverne*", "icon": "⛪"},
    {"say": "Mais attendez.", "title": "MAIS ATTENDEZ.", "flash": True},
    {"say": "Les morts d'épuisement qu'on raconte partout ?", "led": "MORTS", "strike": 1.4},
    {"say": "Aucun témoin de l'époque n'en parle.", "led": "0", "led_sub": "témoin de l'époque", "icon": "📜"},
    {"say": "Ces chiffres viennent de récits écrits bien plus tard.", "title": "Une histoire *amplifiée*", "stamp": "Paracelse", "icon": "✍️"},
    {"say": "Cinq siècles après, personne ne sait vraiment pourquoi ils dansaient.", "title": "Pourquoi ? *Personne ne sait.*", "icon": "🧠"},
    {"say": "Et toi, tu penses que c'était quoi ?", "title": "Et toi, tu penses *quoi ?*", "sub": "Épilepsie · Intoxication · Panique collective"},
]

if __name__ == "__main__":
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    name = os.environ.get("TTS_VOICE", "voix").split("-")[2].replace("Neural", "").replace("Multilingual", "")
    work = os.path.join(out_dir, f"_work_{name}")
    os.makedirs(work, exist_ok=True)
    text = " ".join(b["say"] for b in BEATS)
    audio, timing = voice_generator.generate_voice_with_timing(
        text, out_path=os.path.join(work, "voice.mp3"), timing_path=os.path.join(work, "timing.json"))
    words = json.load(open(timing, encoding="utf-8"))
    out = dossier_video.make_short(audio, words, [dict(b) for b in BEATS],
                                   os.path.join(out_dir, f"demo_1518_{name}.mp4"), work)
    print("OK", out)
