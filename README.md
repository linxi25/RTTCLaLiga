# Rice Table Tennis League – Ratings

Upload each league night's results → GitHub recalculates everyone's rating → the ratings page updates. The link never changes, and every past week stays viewable under **Match history**.

- Ratings page: `https://linxi25.github.io/RTTCLaLiga/`
- Results entry: `https://linxi25.github.io/RTTCLaLiga/admin.html`

Visitors must answer the club question (set in `config.json`) before anything is shown. The data is encrypted in the page, so the answer is required to read it; case, spaces and punctuation in the answer are ignored, and each browser remembers it.

## One-time setup

1. **Pages**: Settings → Pages → Build and deployment → Source: **GitHub Actions**.
2. **Answer secret**: Settings → Secrets and variables → Actions → New repository secret
   - Name: `SITE_ANSWERS`
   - Value: the accepted answer(s), separated by `|`, e.g. `Jane Doe|Jane`
3. **Build**: Actions → *Update ratings site* → Run workflow.
4. **Token for the entry page** (only needed to use `admin.html`):
   Profile → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token
   - Repository access: *Only select repositories* → this repo
   - Permissions → Contents: **Read and write**

To change the question, edit `config.json`; to change the answer, edit the `SITE_ANSWERS` secret and re-run the workflow.

## Each week

**Automatic (default).** Every Friday at 10:47 pm Central, and again Saturday at 10:17 am, GitHub opens the StadiumTT tournament page(s) listed in `config.json` (`stadiumtt_urls`), picks up newly CERTIFIED matches, saves them under `data/results/`, and rebuilds the site. Matches only get added, never removed, so manual fixes stick. To run it right now: Actions → *Update ratings site* → Run workflow. If a new season uses a new StadiumTT tournament, add its link to `stadiumtt_urls`.

**Option A – entry page.** Open `admin.html`, enter the club answer and your token, pick the date, paste the matches (one per line, `Player A 3-1 Player B`), check the preview, submit. New names are flagged so typos don't create new players; re-submitting a date asks before replacing it.

**Option B – upload a file.** On GitHub, open `data/results/` → Add file → Upload files, and upload `YYYY-MM-DD.csv`:

```
player_a,player_b,score_a,score_b
Jiaqi Wang,Efran Zhao,3,2
```

Either way, the site rebuilds automatically within a couple of minutes.

## Files

| Path | Purpose |
|---|---|
| `data/players.csv` | Players and starting ratings (anyone not listed starts at 1000) |
| `data/results/YYYY-MM-DD.csv` | One file per league night, matches in the order played |
| `config.json` | Site title and the members' question |
| `scripts/build.py` | Recomputes all ratings from week one and builds the site |
| `templates/` | Ratings page and entry page |
| `.github/workflows/build.yml` | Runs the build and publishes on every change |

Rating rules: Elo, K = 32; win chance = 1 / (1 + 10^((opponent − own)/400)); only the winner counts, not the score; ratings rounded to 0.1 after each match; players who miss a week keep their rating.

Note: the repository itself is public (free GitHub Pages requires it), so the CSV files in `data/` can be read by anyone who finds the repo on GitHub. The question only protects the ratings page.
