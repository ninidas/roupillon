"""Reprise des journées de l'ancien oracle (une page HTML) : python -m app.import_oracle jour1.json ...
Chaque fichier porte le nom de sa date (2026-03-02.json) et contient la journée au format de l'oracle."""
import json
import sys
from datetime import date
from pathlib import Path

from . import models
from . import service as S
from .database import Base, SessionLocal, engine


def import_day(db, d: date, v: dict) -> int:
    added = []
    def add(kind, start, end=None, ml=None):
        if start:
            added.append(models.Event(kind=kind, start=S.stamp(S.resolve(d, kind, start)),
                                      end=S.stamp(S.resolve(d, kind, end)) if end else None, ml=ml))
    if v.get("wakeSet") and v.get("wake"):
        add("wake", v["wake"])
    for _, n in sorted((v.get("naps") or {}).items(), key=lambda kv: int(kv[0])):
        add("nap", n.get("start"), n.get("end"))
    add("bed", v.get("bed"))
    for w in v.get("night") or []:
        add("night", w.get("start"), w.get("end"))
    for f in v.get("feeds") or []:
        add("feed", f.get("t"), ml=f.get("ml"))
    # Une journée déjà présente dans la nouvelle base n'est pas reprise une seconde fois
    m0 = S.midnight(d)
    if S.events_between(db, m0, m0.replace(hour=23, minute=59)):
        return 0
    db.add_all(added)
    return len(added)


def main(paths):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for p in paths:
            d = date.fromisoformat(Path(p).stem)
            n = import_day(db, d, json.loads(Path(p).read_text(encoding="utf-8")))
            print(f"{d} : {n} événement(s)")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
