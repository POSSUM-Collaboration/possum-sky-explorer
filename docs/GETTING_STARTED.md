# Getting started — from the zip on your disk to a public repo and a live tool

*Written for someone who has never used git. Nothing here needs the command line;
where a command-line equivalent exists it's shown in a grey box, but you can ignore it.*

## 0. Two minutes of vocabulary

- **Git** is a program that records the history of a folder: every saved state ("commit")
  is kept forever, you can see who changed what, and several people can work on copies
  and merge their changes back. The folder plus its history is a **repository** ("repo").
- **GitHub** is a website that hosts repositories so people can share them. A **public**
  repo can be read by anyone; only people you invite can change it.
- **GitHub Desktop** is a free point-and-click app that does the git parts for you.
  This guide uses it.
- **Commit** = save a snapshot with a one-line message. **Push** = upload your commits
  to GitHub. **Pull** = download other people's commits. **Pull request** = someone
  proposing a change for you to review and accept.

The folder you received already contains the history (`.git` inside it — hidden folder).
You will *not* lose anything by following the steps below.

## 1. One-time setup (15 minutes)

1. Make a GitHub account at https://github.com if you don't have one (free). Ask the
   collaboration whether a **POSSUM organisation** already exists on GitHub; if so, ask
   to be made an owner so the repo can live under it rather than your personal account.
2. Install **GitHub Desktop** from https://desktop.github.com and sign in.
3. Unzip `possum-sky-explorer_repo.zip` somewhere permanent, e.g.
   `~/Code/possum-sky-explorer`. (Not inside Dropbox — syncing tools and git fight.)
4. GitHub Desktop → **File → Add Local Repository…** → choose that folder. Desktop
   recognises the existing history and shows one commit, "Initial public release…".

## 2. Put it on GitHub (5 minutes)

1. In GitHub Desktop click **Publish repository**.
2. Name: `possum-sky-explorer`. Description: *Interactive all-sky viewer for the POSSUM
   rotation-measure grid*. **Untick "Keep this code private"** — the whole point is a
   public repo. Choose the POSSUM organisation if you have one. Click Publish.
3. That's it. The repo is at `https://github.com/<org-or-you>/possum-sky-explorer`.
   Within a minute the **Actions** tab shows the automatic build running: it generates
   synthetic demo data, assembles the viewer, and runs a browser smoke test. A green
   tick means everything works on a clean machine.

**Safety check:** on the repo's web page, confirm there is no `data/` folder with
catalogue files, no `build/sources.json`, no `dist/`. The `.gitignore` file prevents
these from ever being committed, so they shouldn't be there — but look once.

```
# command-line equivalent
cd ~/Code/possum-sky-explorer
git remote add origin https://github.com/<org>/possum-sky-explorer.git
git push -u origin main
```

## 3. Let others contribute (5 minutes, optional but recommended)

1. Repo page → **Settings → Collaborators** (or the organisation's Teams) → invite people
   who should be able to merge changes.
2. **Settings → Branches → Add rule** for `main`: tick *Require a pull request before
   merging*. Now nobody (including you) can push straight to `main`; changes arrive as
   pull requests you can read and accept with one click. The CI tick on each pull request
   tells you it didn't break the build.
3. Anyone else: they click **Fork** on GitHub, make changes in their fork, and open a
   pull request. They never need the real data — `python3 build/make_demo_data.py` gives
   them a fake catalogue that exercises every feature.

## 4. Your day-to-day loop

When you (or Claude) change something in `src/` or `build/`:

1. GitHub Desktop shows the changed files on the left. Tick them, write a one-line
   summary at the bottom ("Fix cutout aspect ratio"), click **Commit to main**.
2. Click **Push origin**. Done — the change is public and CI re-tests it.

When someone else's change is merged on GitHub: click **Fetch origin** then **Pull**
to bring it to your machine.

**Tagging a release** (do this whenever you deploy a new viewer build to the wiki):
repo page → **Releases → Draft a new release** → tag `v3.4`, title the same, one line of
notes → Publish. Deployments are then traceable as (viewer tag, data version).

## 5. Building the real data package (your machine only)

The real catalogue never goes to GitHub. On your Mac, in the repo folder:

1. Copy `build/sources.example.json` to `build/sources.json` and edit the four paths to
   point at your files (the polsel parquet, the dedup parquet, the SPICE-RACS extract
   folder, the ATNF pulsar file). This file is git-ignored.
2. Put `erass1cl_primary_v3.2.fits` (you have it in
   `SPICE-RACS_RMStructureFunctions/data/`) and `DR5_cluster-catalog_v1.1.fits` (URL in
   `docs/BUILD_KIT_README.md`) into `build/overlay_sources/`. Also git-ignored.
3. In Terminal (this part does need a terminal, but it's three lines):
   ```
   cd ~/Code/possum-sky-explorer
   pip install numpy scipy pyarrow pandas astropy matplotlib cmasher
   python3 build/build_payload.py --version 2026-11 --out data/2026-11
   python3 build/assemble.py --data data/2026-11
   ```
   This writes `dist/` — the exact folder to upload to the wiki (next section). Add
   `--mode embed` for the single 17 MB file instead.

Until you do this yourself, the `explorer_members_deploy_2026-11-02.zip` you already have
*is* the `dist/` folder for the current data.

## 6. Putting it on the wiki (members-only)

Full detail in `docs/DEPLOYMENT.md` §3. The short version:

1. Ask whoever administers possum-survey.org for a directory inside the members area —
   something like `/members/explorer/` — that is covered by the same login as other
   members-only files, and for SFTP or file-manager access to it.
2. Upload the *contents* of `dist/` there: `index.html`, `config.json`, and the `data/`
   folder, keeping the layout.
3. Open the page while logged in: the explorer should load with "data 2026-11-…" in the
   header. Then open `…/explorer/data/2026-11-02/manifest.json` in a **private window
   while logged out** — it must be refused. If it loads, the data is public: stop and get
   the login rule fixed before linking.
4. Add a link to `…/explorer/` on the wiki.

**Updating the data later:** run step 5 with a new `--version`, upload only the new
`data/<version>/` folder and the new `config.json`. Re-upload `index.html` only when the
viewer code changed.

## 7. Public release (when DR1 clears the proprietary period)

Build a package from released data only (`--version DR1`), host that package anywhere
public — simplest is a `gh-pages` branch of this very repo, or Zenodo for a citable DOI —
and deploy a second copy of `index.html` + a `config.json` pointing at it. Same code,
different config. `docs/DEPLOYMENT.md` §4 has the exact commands.

## 8. If something goes wrong

- **"Cannot publish" / permission errors in GitHub Desktop** → you're not an owner of the
  organisation; publish under your own account and transfer later (Settings → Transfer).
- **CI shows a red cross** → click it to read the log; usually a syntax error in `src/`.
  You can also ask Claude to look at the log.
- **The page shows "The hosted build must be served over http(s)"** → you double-clicked
  `index.html`. Use the single-file build for that, or serve the folder.
- **Stalls at "Decompressing…"** → the web host is gzip-compressing the already-gzipped
  `.bin.gz` files a second time; ask the admin to exclude `*.gz` from compression.
- Anything else: open an issue on the repo, or paste the error to Claude together with
  `docs/DEPLOYMENT.md` — every design decision is recorded there and in
  `docs/BUILD_KIT_README.md`.
