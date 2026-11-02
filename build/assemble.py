#!/usr/bin/env python3
"""
Assemble the POSSUM Sky Explorer from its source parts.

Two outputs from the same source:

  hosted   (default)  dist/index.html + dist/config.json + dist/data/<version>/...
                      The page is ~300 KB and fetches its data at runtime from the
                      location named in config.json. Serve over http(s). This is what
                      goes on the wiki / web host. Data stays a separate, versioned
                      folder that is NOT in the git repo.

  embed               dist/POSSUM_Sky_Explorer_<version>.html — one self-contained
                      file with the data inlined (base64). Works from file://, email,
                      USB stick. ~17 MB.

    python3 build/assemble.py --data data/2026-11                 # hosted
    python3 build/assemble.py --data data/2026-11 --mode embed    # single file
    python3 build/assemble.py --data data/demo --out dist-demo    # synthetic demo data
"""
import argparse, json, shutil
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
PARTS = ["part1_skeleton.html", "part2_data.html", "part3_render.html", "part4_ui.html"]

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--data", type=Path, required=True, help="data package directory (from build_payload.py)")
ap.add_argument("--mode", choices=["hosted", "embed"], default="hosted")
ap.add_argument("--out", type=Path, default=ROOT / "dist", help="output directory")
ap.add_argument("--data-url", default=None,
                help="hosted mode: URL/base path the page should fetch data from "
                     "(default: copy the package into <out>/data/<version>/ and use a relative path)")
ap.add_argument("--title", default="POSSUM Sky Explorer")
args = ap.parse_args()

html = "".join((ROOT / "src" / p).read_text() for p in PARTS)
manifest = json.loads((args.data / "manifest.json").read_text())
version = manifest.get("version", "unversioned")
args.out.mkdir(parents=True, exist_ok=True)

if args.mode == "embed":
    luts = (args.data / "luts.json").read_text()
    html = (html.replace("__MANIFEST__", json.dumps(manifest))
                .replace("__LUTS__", luts)
                .replace("__MAIN_B64__", (args.data / "main_catalogue.bin.gz.b64").read_text().strip())
                .replace("__SR_B64__", (args.data / "sr_catalogue.bin.gz.b64").read_text().strip())
                .replace("__OVERLAYS_B64__", (args.data / "overlays.json.gz.b64").read_text().strip())
                .replace("__CONFIG_URL__", ""))
    out = args.out / f"POSSUM_Sky_Explorer_{version}.html"
    out.write_text(html)
    print(f"embedded build: {out} ({out.stat().st_size/1e6:.1f} MB)")
else:
    html = (html.replace("__MANIFEST__", "null").replace("__LUTS__", "null")
                .replace("__MAIN_B64__", "").replace("__SR_B64__", "").replace("__OVERLAYS_B64__", "")
                .replace("__CONFIG_URL__", "config.json"))
    (args.out / "index.html").write_text(html)
    if args.data_url:
        data_base = args.data_url.rstrip("/") + "/"
    else:
        dest = args.out / "data" / version
        dest.mkdir(parents=True, exist_ok=True)
        for f in ["manifest.json", "luts.json", "main_catalogue.bin.gz",
                  "sr_catalogue.bin.gz", "overlays.json.gz"]:
            shutil.copy(args.data / f, dest / f)
        data_base = f"data/{version}/"
    config = {
        "title": args.title,
        "dataVersion": version,
        "dataBase": data_base,
        "files": {
            "manifest": "manifest.json", "luts": "luts.json",
            "possum": "main_catalogue.bin.gz", "spiceracs": "sr_catalogue.bin.gz",
            "overlays": "overlays.json.gz",
        },
        "_notes": "dataBase may be relative to index.html or an absolute URL (that host must "
                  "send CORS headers if it differs from the page origin). Bump dataVersion and "
                  "dataBase together when you publish a new data package.",
    }
    (args.out / "config.json").write_text(json.dumps(config, indent=2))
    (args.out / ".nojekyll").write_text("")
    print(f"hosted build: {args.out}/index.html ({(args.out/'index.html').stat().st_size/1e3:.0f} KB), "
          f"config.json -> {data_base}")
