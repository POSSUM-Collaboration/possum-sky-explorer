# POSSUM Sky Explorer — hosting, access control & rolling releases

*Updated 2026-11-02 for the split code/data architecture.*

## 1. The architecture in one picture

```
PUBLIC  — GitHub: possum-sky-explorer          PRIVATE — your web host / wiki members area
  src/, build/, tests/, docs/                    explorer/
  CI builds + tests a SYNTHETIC demo             ├─ index.html      ← built from the repo (211 KB)
  no catalogue data, ever (.gitignore)           ├─ config.json     ← { dataBase: "data/2026-11/", dataVersion: … }
                                                 └─ data/2026-11/   ← the data package (13 MB)
                                                      manifest.json  main_catalogue.bin.gz
                                                      sr_catalogue.bin.gz  overlays.json.gz  luts.json
```

The page fetches `config.json` at start-up, then the package it names. Everything else
(tessellation, filters, exports) runs in the visitor's browser; the host only serves
static files. Three consequences:

* **Access control = who can fetch the data folder.** Put `explorer/` behind the
  members login and the proprietary data is protected; the public repo is just code.
* **Updating data = adding a folder and bumping two fields in `config.json`.**
  Old packages can stay for provenance (old links keep working if you keep them).
* **The same `index.html` can serve any package**: `index.html?config=other.json`
  overrides the default, so one deployed page can offer e.g. members and public
  packages side by side.

## 2. Build outputs

| Command | Output | Use |
|---|---|---|
| `python3 build/assemble.py --data data/<ver>` | `dist/index.html`, `dist/config.json`, `dist/data/<ver>/` | upload to the host (http/https only) |
| `python3 build/assemble.py --data data/<ver> --mode embed` | `dist/POSSUM_Sky_Explorer_<ver>.html` | single 17 MB file: works from file://, e-mail, USB |
| `python3 build/assemble.py --data data/demo --out dist-demo` | demo site | for development / public GitHub Pages |

## 3. Deploy to the wiki / possum-survey.org (members build)

Wikis differ in how they serve raw HTML; two reliable patterns:

**A. Static subfolder on the same host (recommended).** Most wiki hosts (WordPress,
MediaWiki, Confluence on-prem) sit on a web server where you — or the admin — can create a
directory such as `https://possum-survey.org/members/explorer/`:

1. Build: `python3 build/assemble.py --data data/2026-11`.
2. Upload the *contents* of `dist/` (index.html, config.json, data/) via SFTP or the host's
   file manager, into a directory that is covered by the members-area authentication
   (same `.htaccess` / login rule as the other members-only files). Keep `data/` next to
   `index.html`; relative `dataBase` then needs no CORS configuration.
3. Confirm the server sends `Content-Type: text/html` for index.html and
   `application/gzip` (or `application/octet-stream`) for `.bin.gz`. Do **not** let the
   server apply a second transfer-encoding gzip to `.bin.gz` files (most hosts skip
   already-compressed types; if the page stalls at "Decompressing", that's the symptom).
4. **Test in a logged-out private window**: `…/explorer/data/2026-11/manifest.json` must
   be refused. If it loads, the data is public — fix the auth rule before linking.
5. Link to `…/explorer/` from the wiki page (a plain link opening a full tab; iframes work
   but cramp the UI).

**B. Wiki attachments + external app.** If the wiki can only hold attachments and refuses
raw HTML: host `index.html` + `config.json` on GitHub Pages (public code, fine), attach the
data package files to a members-only wiki page, and set `dataBase` to the attachment
URL. This only works if the wiki serves attachments with CORS headers
(`Access-Control-Allow-Origin` for the Pages origin) *and* the browser sends the login
cookie cross-origin — many wikis do neither. Prefer A.

## 4. Public build (released data only)

Once a data tranche clears the proprietary period (DR1 at first):

1. Build a package from released-only inputs: `python3 build/build_payload.py
   --sources build/sources.public.json --version DR1 --out data/DR1`.
2. Host it anywhere public — GitHub Pages from a `gh-pages` branch of this repo, or
   Zenodo for a DOI'd, citable copy; `assemble.py --data-url https://…/data/DR1/` points
   the page at a remote package (that host must send CORS headers; GitHub Pages does).
3. Same `index.html` as the members build; only `config.json` differs.

## 5. Rolling releases (weekly / monthly)

On the machine that holds the live snapshot:

1. Cut a fresh goodpol selection + refresh the dedup cache (see `docs/BUILD_KIT_README.md`).
2. `python3 build/build_payload.py --version 2026-12 --out data/2026-12` (sources.json
   already points at the new parquet files; add `--no-sr` if SPICE-RACS is unchanged
   and you want speed — otherwise the POSSUM-footprint flag is recomputed automatically).
3. `python3 build/assemble.py --data data/2026-12` → `dist/`.
4. Upload `dist/data/2026-12/` next to the previous package; upload the new
   `config.json` (dataVersion/dataBase bumped). Only re-upload `index.html` if the
   viewer code changed (git tag the repo when it does; the About panel shows both the
   data version and the build mode).
5. Reload in a browser: header shows `data 2026-12`. Done. Previous packages can be
   deleted when nobody needs them; they are ~13 MB each.

Automate with a tiny `make_release.sh` wrapping steps 2–3 if desired; CI cannot do it
because the 8 GB snapshot never leaves your machine.

## 6. Git workflow for the collaboration

* `main` is protected; contributors fork/branch and open PRs; CI builds the demo and runs
  the smoke test on every PR, so nobody needs the real data to contribute.
* Tag viewer releases `v3.4`, `v3.5`… ; data packages are versioned by date in their own
  world. A deployment is a (tag, dataVersion) pair — note both in the wiki's change log.
* `build/sources.json`, `data/`, `dist/`, FITS inputs, `*.b64`/`*.bin.gz` are ignored by
  `.gitignore`; keep it that way. If something proprietary ever lands in a commit, treat
  it as a leak (rewrite history before pushing).

## 7. FAQ

* **Why not just commit the data privately?** Git is poor at 13 MB binaries that change
  monthly, and a private repo would also hide the code. Static hosting with a login is
  simpler, auditable, and matches how the collaboration already shares files.
* **Can the hosted build work offline?** No — use the embedded build for that.
* **Browser support:** Chrome/Edge ≥ 80, Firefox ≥ 113, Safari ≥ 16.4 (WebGL2 +
  DecompressionStream).
* **Bandwidth:** ~13 MB per first visit (cached afterwards; the app itself is 211 KB).
