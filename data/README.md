# data/

Data packages live here **locally only** — this directory is git-ignored apart from this
file. A package is a versioned folder produced by `build/build_payload.py` (real data,
proprietary during the POSSUM proprietary period) or `build/make_demo_data.py`
(synthetic, free to share):

    data/2026-11-02/        manifest.json  main_catalogue.bin.gz  sr_catalogue.bin.gz
                            overlays.json.gz  luts.json  (+ *.b64 twins for the embedded build)
    data/demo/              same layout, synthetic

The viewer never needs to know where the data came from: `config.json` in the deployed
folder names a `dataBase` URL and `dataVersion`, and the page fetches the package at
start-up. Publish a new package by uploading a new folder next to the old one and
bumping those two fields.
