import datetime

import slot_planner as sp

UTC = datetime.timezone.utc


def at(y, m, d, h, mi=0):
    return datetime.datetime(y, m, d, h, mi, tzinfo=UTC)


def test_soir_programme_le_short_de_8h_du_lendemain():
    # 22h UTC en hiver = 23h Paris : le 8h du lendemain (07:00 UTC) doit etre programme.
    done = ["2026-11-22T08", "2026-11-22T13", "2026-11-22T19"]
    assert sp.pick(at(2026, 11, 22, 22), done) == ("short", "2026-11-23T08", "2026-11-23T07:00:00Z")


def test_enchaine_les_creneaux_suivants():
    done = ["2026-11-22T08", "2026-11-22T13", "2026-11-22T19", "2026-11-23T08"]
    assert sp.pick(at(2026, 11, 22, 23), done) == ("short", "2026-11-23T13", "2026-11-23T12:00:00Z")
    done.append("2026-11-23T13")
    assert sp.pick(at(2026, 11, 22, 23), done) == ("long", "2026-11-23T19", "2026-11-23T18:00:00Z")


def test_rien_au_dela_de_l_horizon():
    done = ["2026-11-22T08", "2026-11-22T13", "2026-11-22T19", "2026-11-23T08", "2026-11-23T13",
            "2026-11-23T19"]
    assert sp.pick(at(2026, 11, 22, 23), done) is None


def test_creneau_en_retard_publie_tout_de_suite():
    # 14h30 Paris, le 13h n'est pas couvert : publication immediate.
    done = ["2026-11-22T08"]
    assert sp.pick(at(2026, 11, 22, 13, 30), done) == ("short", "2026-11-22T13", None)


def test_creneau_trop_ancien_abandonne():
    # 13h30 Paris, le 8h (5h30 de retard) est abandonne : on programme le 13h... qui est en retard de 30min.
    assert sp.pick(at(2026, 11, 22, 12, 30), []) == ("short", "2026-11-22T13", None)


def test_heure_d_ete():
    # Juillet : Paris = UTC+2, le 8h tombe a 06:00 UTC.
    done = ["2026-07-01T08", "2026-07-01T13", "2026-07-01T19"]
    assert sp.pick(at(2026, 7, 1, 20), done) == ("short", "2026-07-02T08", "2026-07-02T06:00:00Z")


def test_etat_purge_et_dedoublonne(tmp_path):
    path = tmp_path / "s.json"
    now = at(2026, 11, 22, 12)
    sp.save_state(["2026-11-01T08", "2026-11-22T08", "2026-11-22T08"], now, path=str(path))
    assert sp.load_state(str(path)) == ["2026-11-22T08"]
