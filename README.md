# POSSUM Sky Explorer

An interactive, all-client-side sky viewer for the POSSUM rotation-measure grid
(Polarisation Sky Survey of the Universe's Magnetism, ASKAP), with SPICE-RACS
folded in, built for the POSSUM Data Release 1 paper and the collaboration's
discovery work.

* Live spherical-Voronoi (nearest-neighbour) tessellation of 300k+ components in a
  web worker — the DR1 paper's headline-figure method, recomputed as you filter.
* RM, polarised intensity, fractional polarisation, S/N, Stokes I, spectral index,
  B-angle; globe or Mollweide; Galactic or equatorial; any colour map and stretch.
* Classic RM bubble plot; blink comparator between POSSUM and SPICE-RACS.
* Region tool: circle-drag a region, get RM statistics (mean/median/σ/1.4826×MAD),
  histograms, an RM-vs-separation profile with windowed dispersion curves, a cutout
  map you can nudge with the arrow keys, CSV export, and DS9/Aladin `.reg` export
  with RM circles and polarisation/B-field sticks.
* Identify tool: nearest known objects (clusters incl. eRASS1, groups, galaxies,
  pulsars) + live SIMBAD query + SIMBAD/NED/Aladin link-outs.
* Overlays with virial-radius circles; import your own CSV catalogue at runtime.
* No server, no database, no framework: one HTML page (raw WebGL2) plus data files.

**Code is public; data is not (yet).** This repository contains the viewer and its
build tools only. Catalogue data is a separate, versioned *data package* that the
page fetches at run time from wherever you host it (`config.json` says where). During
POSSUM's proprietary period the real package lives behind the collaboration's login;
a synthetic demo package lets anyone develop the viewer without it.

## Quick start (no real data needed)

```bash
pip install numpy scipy astropy matplotlib cmasher        # build-time only
python3 build/make_demo_data.py --out data/demo           # synthetic catalogue
python3 build/assemble.py --data data/demo --out dist-demo
cd dist-demo && python3 -m http.server 8000               # open http://localhost:8000/
```

The hosted build must be served over http(s) — browsers refuse `fetch()` from
`file://`. For a double-clickable single file use `--mode embed`.

## Building with real data

1. `cp build/sources.example.json build/sources.json` and point it at your local
   POSSUM selection/dedup parquet files, the SPICE-RACS column extracts (made on a
   machine that has the DR2 FITS, with `build/sr_extract/extract.py`), and the ATNF
   pulsar file. `sources.json` is git-ignored.
2. Drop the two large overlay FITS files into `build/overlay_sources/` (eRASS1
   primary catalogue; ACT DR5 from the PSZ2Explorer GitHub mirror) — optional, the
   builder skips those overlays if absent.
3. `python3 build/build_payload.py --version 2026-11 --out data/2026-11`
4. `python3 build/assemble.py --data data/2026-11` → `dist/` ready to upload
   (`index.html`, `config.json`, `data/2026-11/…`), and/or
   `python3 build/assemble.py --data data/2026-11 --mode embed` → one 17 MB file.

See `docs/DEPLOYMENT.md` for wiki/web hosting, access control during the
proprietary period, and the rolling-release routine, and `docs/BUILD_KIT_README.md`
for data-format details.

## Repository layout

```
src/        part1_skeleton.html  (markup + CSS)      part3_render.html (WebGL, projections)
            part2_data.html      (payload loading,   part4_ui.html     (UI, region/identify,
                                  worker, filters)                      exports, boot)
build/      assemble.py          build_payload.py    make_demo_data.py  make_luts.py
            famous_objects.py    sources.example.json  overlay_sources/  sr_extract/
tests/      smoke.js             (boots a URL, filter regression, region check)
docs/       DEPLOYMENT.md        BUILD_KIT_README.md
data/       (git-ignored) data packages
```

`assemble.py` concatenates the four source parts and substitutes either the config
URL (hosted) or the inlined payloads (embedded). Edit `src/`, re-run `assemble.py`.

## Testing

```bash
npm install playwright && npx playwright install chromium
node tests/smoke.js http://localhost:8000/index.html
```

CI (GitHub Actions) builds the demo package, assembles both outputs and runs the smoke
test on every push.

## Contributing

Issues and pull requests welcome. Keep changes in `src/` and `build/`; never commit
data packages, `build/sources.json`, or `dist/`. Run the smoke test against the demo
build before opening a PR. Design notes: all state lives in `VIEW`, `DATA`, `REGION`;
rendering is `render()` in part 3; anything that touches the catalogue goes through
`pipelineFilterChanged()` so the tessellation and every panel stay consistent.

## Licence and credit

Software: MIT (see `LICENSE`). Data packages: POSSUM collaboration data policy.
Overlay catalogues: MCXC-II (Sadibekova+ 2024), PSZ2 (Planck 2016), ACT DR5 (Hilton+
2021), eRASS1 (Bulbul+ 2024), Kourkchi & Tully (2017), OpenNGC, ATNF pulsar catalogue.
Please cite the POSSUM DR1 paper when using the explorer in published work.
