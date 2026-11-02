# Data package format & regeneration notes

v2 additions: SPICE-RACS DR2 fold-in (embedded only outside POSSUM coverage, with
per-source catalogue flag, greyscale render modes, catalogue column in every export),
region tool + Region-analysis tab (circle drag ≤20°, RM stats incl. 1.4826×MAD,
histograms, region CSV), identify tool (local ranked search + live SIMBAD TAP +
SIMBAD/NED/Aladin link-outs), eRASS1 primary cluster overlay.

SR inputs: the builder reads column extracts under
/mnt/user-data/uploads/SPICE-RACS_data/claude_sr_extract (produced on-device from
spice-racs.dr2.published.fits by data/claude_sr_extract/extract.py — pure
python+numpy, no astropy needed). Selection: snr_polint>=6 & goodI_flag &
~leakage_flag, then 15" positional dedup keeping max snr (per Craig's SF notebook),
then exclusion within 0.4 deg of any embedded POSSUM component.

The explorer is a single self-contained HTML file with the catalogue and overlay
data embedded. This kit regenerates it from a newer snapshot.

## Contents
- `build_payload.py` — reads the polarised-source selection + dedup mask, quantises
  the catalogue into a compact binary column store, fetches nothing (overlay source
  files must sit in `data/`), and writes `payload/*`.
- `assemble.py` — splices the payloads into the HTML template parts.
- `part1_skeleton.html` … `part4_ui.html` — the viewer source (CSS/UI, data layer +
  worker, WebGL renderer, UI wiring).
- `data/` — overlay source catalogues (MCXC-II, PSZ2, ACT DR5, Kourkchi–Tully 2017,
  OpenNGC; ATNF pulsars are read from DR1_analysis).

## To regenerate with new data
1. Edit `SRC_POLSEL` / `SRC_DEDUP` at the top of `build_payload.py`.
   The polsel file needs columns: cat_id, sbid, l, b, rm, rm_err, polint, fracpol,
   SNR_PI, stokesI, spectral_index, derot_polangle. A goodpol cut of the live
   snapshot works directly, e.g. `python tools/make_dev_subset.py --flag goodpol
   --out .../POSSUM_DR1_polsel_new.parquet` (from the claude/tools folder).
2. `python3 build_payload.py`
3. `python3 assemble.py`  → `POSSUM_DR1_Sky_Explorer.html`

Requires: numpy, pandas, pyarrow, astropy, scipy, matplotlib, cmasher.

## Known data notes (as built, 2026-08-12)
- Embedded selection: 333,781 components = the goodpol SNR≥6 selection
  (POSSUM_DR1_polsel_SNR6.parquet, 2026-01-26) intersected with the July dedup
  mask (336,283 ids). 2,502 ids in the mask are missing from the older polsel
  file — dominated by SB72954 (1,837) and SB75088 (493). Cutting a fresh polsel
  from the July snapshot and rebuilding closes the gap.
- Quantisation: positions float32; rm float32; other quantities log-quantised
  uint16 (precision ≲0.02% relative) — see manifest.json in the payload folder.
- 6dFGS has no redistributable machine-readable mirror reachable from the build
  environment; load it at runtime via the viewer's Import panel instead
  (CSV with RA/Dec + z; numeric columns become filter sliders automatically).

## Large data files not bundled in this zip
Two overlay source files are excluded to keep the kit small; place them in `data/` before running:
- `erass1cl_primary_v3.2.fits` — already on your machine at
  `Projects/SPICE-RACS_RMStructureFunctions/data/erass1cl_primary_v3.2.fits`
- `DR5_cluster-catalog_v1.1.fits` — https://raw.githubusercontent.com/CodePhys/PSZ2Explorer/master/PSZ2Explorer/PSZ2Explorer/Data/DR5_cluster-catalog_v1.1.fits
