#!/usr/bin/env python3
"""Pull CERTIFIED matches from the StadiumTT tournament page(s) in config.json
("stadiumtt_urls") and write data/results/YYYY-MM-DD.csv.

The page is opened in headless Chromium exactly as a visitor would see it; the
Matches tab text is parsed. A week's file only ever gains matches: newly
certified ones are appended; nothing already saved is removed or reordered,
so fixes made by hand stick.

Usage:  python scripts/fetch_stadiumtt.py            (fetch with a browser)
        python scripts/fetch_stadiumtt.py page.txt   (parse saved page text)
"""
import csv, datetime, io, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results"


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def stadium_name(n):
    parts = [p.strip() for p in n.split(",") if p.strip()]
    full = " ".join(parts[1:] + parts[:1]) if len(parts) > 1 else parts[0]
    if full == full.upper():  # "JIANG, YIFAN" -> "Yifan Jiang"
        full = re.sub(r"(^|[\s\-'])(\w)", lambda m: m.group(1) + m.group(2).upper(), full.lower())
    return norm(full)


def parse(text):
    """Return ({(month, day): [match, ...]}, skipped_count)."""
    lines = [norm(l) for l in text.splitlines()]
    lines = [l for l in lines if l]
    weeks, skipped = {}, 0
    for i, line in enumerate(lines):
        h = re.match(r"^(?:LEAGUE\s+)?(\d{1,2})/(\d{1,2}).*\bGROUP\b", line, re.I)
        if not h:
            continue
        end = i + 1
        while end < len(lines) and not re.search(r"\bGROUP\b", lines[end], re.I) and lines[end].upper() != "SHARE":
            end += 1
        blk = lines[i + 1:end]
        if not any(x.upper() == "CERTIFIED" for x in blk):
            skipped += 1
            continue
        names = [x for x in blk if "," in x and not re.search(r"AFFILIATION|CLUB|\(USA\)|•", x, re.I)]
        nums = [x for x in blk if re.fullmatch(r"\d{1,2}", x)]
        if len(names) == 2 and len(nums) >= 2 and nums[0] != nums[1]:
            weeks.setdefault((int(h[1]), int(h[2])), []).append(
                {"a": stadium_name(names[0]), "b": stadium_name(names[1]), "sa": int(nums[0]), "sb": int(nums[1])})
    for k in weeks:  # page lists newest first
        weeks[k].reverse()
    return weeks, skipped


def fetch(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1200, "height": 2000})
        pg.goto(url.split("#")[0], wait_until="networkidle", timeout=90_000)
        pg.get_by_text(re.compile(r"^\s*MATCHES\s*$", re.I)).first.click(force=True)
        pg.wait_for_function("document.body.innerText.match(/CERTIFIED|NOT SUBMITTED/)", timeout=60_000)
        last = -1
        for _ in range(30):  # scroll until no more matches load
            pg.mouse.wheel(0, 20000)
            pg.wait_for_timeout(1200)
            n = pg.evaluate("document.body.innerText.length")
            if n == last:
                break
            last = n
        text = pg.evaluate("(document.querySelector('main')||document.body).innerText")
        b.close()
        return text


def key(m):
    """Same match regardless of which side is listed first."""
    a, b = (m["a"].lower(), m["sa"]), (m["b"].lower(), m["sb"])
    return tuple(sorted([a, b]))


def read_week(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [{"a": norm(r["player_a"]), "b": norm(r["player_b"]), "sa": int(r["score_a"]), "sb": int(r["score_b"])}
                for r in csv.DictReader(f) if norm(r.get("player_a"))]


def main():
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    urls = cfg.get("stadiumtt_urls") or []
    if len(sys.argv) > 1:
        texts = [Path(sys.argv[1]).read_text(encoding="utf-8")]
    elif not urls:
        print("No stadiumtt_urls in config.json; nothing to fetch.")
        return
    else:
        texts = [fetch(u) for u in urls]

    weeks, skipped = {}, 0
    for t in texts:
        w, s = parse(t)
        skipped += s
        for k, v in w.items():
            weeks.setdefault(k, []).extend(v)

    today = datetime.date.today()
    changed = []
    RESULTS.mkdir(parents=True, exist_ok=True)
    for (mo, d), matches in sorted(weeks.items()):
        year = today.year - 1 if mo > today.month + 1 else today.year
        path = RESULTS / f"{year:04d}-{mo:02d}-{d:02d}.csv"
        if path.exists():
            old = read_week(path)
            have = list(map(key, old))
            extra = []
            for m in matches:  # keep saved matches (and their order); only add new ones
                if key(m) in have:
                    have.remove(key(m))
                else:
                    extra.append(m)
            if not extra:
                continue
            matches = old + extra
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["player_a", "player_b", "score_a", "score_b"])
        for m in matches:
            w.writerow([m["a"], m["b"], m["sa"], m["sb"]])
        path.write_text(buf.getvalue(), encoding="utf-8")
        changed.append(f"{path.name} ({len(matches)} matches)")

    print(f"StadiumTT: {sum(map(len, weeks.values()))} certified matches in {len(weeks)} week(s); "
          f"{skipped} not certified yet.")
    print("Updated: " + (", ".join(changed) if changed else "nothing new"))


if __name__ == "__main__":
    main()
