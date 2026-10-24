"""Copie propre de la base chaque nuit entre 4 h 30 et 5 h, avant l'archive de l'hôte (5 h).
Une archive faite pendant qu'un parent note quelque chose peut être incohérente, pas cette copie."""
import os
import sqlite3
import threading
import time
from datetime import datetime

from .database import DB_PATH
from . import service as S

KEEP = 7           # copies gardées, une par jour
CHECK_EVERY = 300  # secondes


def folder() -> str:
    return os.path.join(os.path.dirname(DB_PATH), "backup")


def backup_now(now: datetime) -> str:
    d = folder()
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, f"roupillon-{now:%Y-%m-%d}.db")
    src, out = sqlite3.connect(DB_PATH), sqlite3.connect(dst)
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    old = sorted(f for f in os.listdir(d) if f.startswith("roupillon-") and f.endswith(".db"))[:-KEEP]
    for f in old:
        os.remove(os.path.join(d, f))
    return dst


def _loop():
    # On regarde l'heure toutes les 5 min plutôt que de dormir jusqu'à 4 h 30 : pas de surprise au changement d'heure
    while True:
        now = S.now_local()
        due = (now.hour, now.minute) >= (4, 30) and now.hour < 5
        if due and not os.path.exists(os.path.join(folder(), f"roupillon-{now:%Y-%m-%d}.db")):
            try:
                backup_now(now)
            except Exception as e:  # la copie ne doit jamais faire tomber l'app
                print(f"Copie de la base impossible : {e}", flush=True)
        time.sleep(CHECK_EVERY)


def start():
    if os.environ.get("NIGHTLY_BACKUP", "1") != "0":
        threading.Thread(target=_loop, name="backup", daemon=True).start()
