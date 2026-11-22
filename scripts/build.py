#!/usr/bin/env python3
"""Rebuild the ratings site from data/.

data/players.csv          name,start_rating   (anyone missing starts at 1000)
data/results/YYYY-MM-DD.csv  player_a,player_b,score_a,score_b  (one file per league night)

Rating rules (same as the original page):
  win chance  E = 1 / (1 + 10^((Rb - Ra) / 400))
  winner +32*(1-E), loser -the same; ratings rounded to 0.1 after every match;
  matches processed in file order, weeks in date order. Only who won counts.

Writes site/index.html (data embedded) and site/data.json.

Members-only: set SITE_ANSWERS (a GitHub Actions secret) to the accepted answer(s)
to the question in config.json, separated by "|". The data is then AES-GCM encrypted
and only unlocks in the browser with a correct answer (case, spaces and punctuation ignored).
"""
import base64, csv, json, os, re, sys, shutil, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, SITE = ROOT / "data", ROOT / "site"
K, DEFAULT = 32, 1000.0


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def clean(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def load_players():
    start, order = {}, []
    p = DATA / "players.csv"
    if p.exists():
        with p.open(newline="", encoding="utf-8-sig") as f:
            for i, row in enumerate(csv.DictReader(f), 2):
                name = clean(row.get("name"))
                if not name:
                    continue
                raw = (row.get("start_rating") or "").strip()
                try:
                    start[name] = float(raw) if raw else DEFAULT
                except ValueError:
                    die(f"players.csv line {i}: bad start_rating '{raw}'")
                if name not in order:
                    order.append(name)
    return start, order


def load_week(path):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
        die(f"{path.name}: file name must be YYYY-MM-DD.csv")
    out = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for i, row in enumerate(csv.DictReader(f), 2):
            a, b = clean(row.get("player_a")), clean(row.get("player_b"))
            if not a and not b:
                continue
            where = f"{path.name} line {i}"
            if not a or not b:
                die(f"{where}: missing a player name")
            if a.lower() == b.lower():
                die(f"{where}: '{a}' is listed against themselves")
            try:
                sa, sb = int(row["score_a"]), int(row["score_b"])
            except (KeyError, TypeError, ValueError):
                die(f"{where}: scores must be whole numbers")
            if sa == sb or sa < 0 or sb < 0:
                die(f"{where}: score {sa}-{sb} has no winner")
            out.append({"a": a, "b": b, "sa": sa, "sb": sb})
    return out


def norm_answer(s):
    s = unicodedata.normalize("NFKC", s).lower()
    return "".join(c for c in s if unicodedata.category(c)[0] in "LN")


def encrypt(data, answers, question):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    b64 = lambda b: base64.b64encode(b).decode()
    it = 150_000
    dek, iv = os.urandom(32), os.urandom(12)
    ct = AESGCM(dek).encrypt(iv, json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(), None)
    keys = []
    for a in answers:
        salt, wiv = os.urandom(16), os.urandom(12)
        kek = PBKDF2HMAC(hashes.SHA256(), 32, salt, it).derive(norm_answer(a).encode())
        keys.append({"salt": b64(salt), "iv": b64(wiv), "ct": b64(AESGCM(kek).encrypt(wiv, dek, None))})
    return {"enc": 1, "q": question, "iter": it, "keys": keys, "iv": b64(iv), "ct": b64(ct)}


def main():
    start, order = load_players()
    # case-insensitive name matching so "efran zhao" still maps to "Efran Zhao"
    canon = {n.lower(): n for n in order}

    def name(n):
        if n.lower() not in canon:
            canon[n.lower()] = n
            order.append(n)
        return canon[n.lower()]

    rating, stats, weeks = {}, {}, []
    files = sorted((DATA / "results").glob("*.csv"))
    for path in files:
        results = load_week(path)
        if not results:
            continue
        before, wk, new = {}, {}, []
        for m in results:
            m["a"], m["b"] = name(m["a"]), name(m["b"])
            for p in (m["a"], m["b"]):
                if p not in rating:
                    rating[p] = start.get(p, DEFAULT)
                    stats[p] = {"g": 0, "w": 0, "l": 0}
                    new.append(p)
                before.setdefault(p, rating[p])
                wk.setdefault(p, {"w": 0, "l": 0})
            a, b = m["a"], m["b"]
            ea = 1 / (1 + 10 ** ((rating[b] - rating[a]) / 400))
            d = K * ((1 if m["sa"] > m["sb"] else 0) - ea)
            rating[a] = round(rating[a] + d, 1)
            rating[b] = round(rating[b] - d, 1)
            win, lose = (a, b) if m["sa"] > m["sb"] else (b, a)
            for p, k in ((win, "w"), (lose, "l")):
                wk[p][k] += 1
                stats[p][k] += 1
                stats[p]["g"] += 1
        weeks.append({
            "date": path.stem,
            "results": results,
            "changes": [{"name": p, "from": before[p], "to": rating[p], **wk[p]} for p in before],
            "newNames": new,
        })

    players = [{"name": p, "rating": rating[p], **stats[p]} for p in order if p in rating]
    data = {"players": players, "weeks": weeks}

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    answers = [a for a in (os.environ.get("SITE_ANSWERS") or "").split("|") if norm_answer(a)]
    if answers:
        payload = encrypt(data, answers, cfg["question"])
    elif os.environ.get("ALLOW_PUBLIC") == "1":
        payload = data
    else:
        die("SITE_ANSWERS is not set. Add it under Settings -> Secrets and variables -> Actions "
            "(answers separated by |), or set ALLOW_PUBLIC=1 to publish without a question.")

    SITE.mkdir(exist_ok=True)
    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    title = cfg.get("title", "Ratings")
    for name in ("index.html", "admin.html"):
        page = (ROOT / "templates" / name).read_text(encoding="utf-8")
        page = page.replace("__DATA__", js).replace("__TITLE__", title.replace("<", "&lt;"))
        (SITE / name).write_text(page, encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"Built {len(players)} players, {len(weeks)} weeks, {sum(len(w['results']) for w in weeks)} matches.")


if __name__ == "__main__":
    main()
