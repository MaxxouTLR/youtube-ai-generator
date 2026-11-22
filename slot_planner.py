"""Planificateur des creneaux de publication (2 Shorts + 1 longue par jour, heure de Paris).

Pourquoi : les cron GitHub Actions de ce depot se declenchent tres en retard (souvent 2 a 15h) ou pas
du tout. Avec l'ancien systeme "publier au moment ou le cron tombe", le Short de 8h n'etait jamais
publie et celui de 13h sortait vers 15h30 : 1 seul Short par jour au lieu de 2 (constate du 05 au
22/11/2026 dans l'historique des runs).

Nouveau principe : chaque declenchement (cron horaire, quel que soit son retard) prepare UNE video pour
le prochain creneau pas encore couvert, l'envoie a YouTube en "privee" avec une date de mise en ligne
(publishAt), et c'est YouTube qui la rend publique pile a l'heure. Un creneau deja passe de moins de
LATE_TOLERANCE_HOURS est publie tout de suite ; au-dela il est abandonne (pas de rafale de rattrapage).

Usage (GitHub Actions) :
    python slot_planner.py pick            # ecrit run_type / slot / publish_at dans $GITHUB_OUTPUT
    python slot_planner.py done <slot>     # marque le creneau comme couvert (apres upload reussi)
"""
import datetime
import json
import os
import sys
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
STATE_FILE = os.path.join("output", "scheduled_slots.json")

# (heure locale Paris, type de video). Grille du 25/10/2026, confirmee le 22/11/2026 : 2 Shorts + 1 longue.
SLOTS = [(8, "short"), (13, "short"), (19, "long")]

# Un creneau a deja ete rate de moins de X heures : on publie tout de suite plutot que de le perdre.
LATE_TOLERANCE_HOURS = 4
# Marge minimale entre l'upload et la mise en ligne programmee (le traitement YouTube prend quelques minutes).
MIN_LEAD_MINUTES = 20
# On ne prepare pas plus loin que ca a l'avance (evite de consommer les sujets en avance de plusieurs jours).
HORIZON_HOURS = 30
# Historique garde dans le fichier d'etat.
KEEP_DAYS = 7


def slot_key(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H")


def load_state(path: str = STATE_FILE) -> list[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return list(data) if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_state(keys: list[str], now: datetime.datetime, path: str = STATE_FILE) -> None:
    cutoff = slot_key(now.astimezone(PARIS) - datetime.timedelta(days=KEEP_DAYS))
    kept = sorted({k for k in keys if k >= cutoff})
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(kept, f, indent=2)


def candidate_slots(now: datetime.datetime):
    """Creneaux d'hier a apres-demain, en heure de Paris (gere l'heure d'ete/hiver), tries."""
    local_now = now.astimezone(PARIS)
    out = []
    for day_offset in (-1, 0, 1, 2):
        day = local_now.date() + datetime.timedelta(days=day_offset)
        for hour, run_type in SLOTS:
            out.append((datetime.datetime(day.year, day.month, day.day, hour, tzinfo=PARIS), run_type))
    return sorted(out)


def pick(now: datetime.datetime, done: list[str]):
    """Renvoie (run_type, slot_key, publish_at_utc_iso_ou_None) ou None s'il n'y a rien a faire."""
    done_set = set(done)
    for slot_dt, run_type in candidate_slots(now):
        key = slot_key(slot_dt)
        if key in done_set:
            continue
        delta = slot_dt - now
        if delta < -datetime.timedelta(hours=LATE_TOLERANCE_HOURS):
            continue  # trop tard, creneau abandonne
        if delta < datetime.timedelta(minutes=MIN_LEAD_MINUTES):
            return run_type, key, None  # en retard (ou imminent) : publication immediate
        if delta <= datetime.timedelta(hours=HORIZON_HOURS):
            publish_at = slot_dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            return run_type, key, publish_at
        return None
    return None


def _write_outputs(values: dict) -> None:
    out_path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in values.items()]
    if out_path:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main(argv: list[str]) -> int:
    now = datetime.datetime.now(datetime.timezone.utc)
    if len(argv) >= 1 and argv[0] == "pick":
        print(f"Heure Paris : {now.astimezone(PARIS):%Y-%m-%d %H:%M}")
        choice = pick(now, load_state())
        if choice is None:
            print("Tous les creneaux des prochaines heures sont deja couverts - rien a faire.")
            _write_outputs({"run_type": "skip", "slot": "", "publish_at": ""})
        else:
            run_type, key, publish_at = choice
            when = f"programme pour {publish_at} (UTC)" if publish_at else "publication immediate"
            print(f"Creneau {key}h Paris -> {run_type}, {when}")
            _write_outputs({"run_type": run_type, "slot": key, "publish_at": publish_at or ""})
        return 0
    if len(argv) >= 2 and argv[0] == "done":
        save_state(load_state() + [argv[1]], now)
        print(f"Creneau {argv[1]} marque comme couvert.")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
