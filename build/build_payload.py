#!/usr/bin/env python3
"""
Build the data package for the POSSUM Sky Explorer.

Reads the POSSUM polarised-source selection + de-duplication mask, the SPICE-RACS
column extracts, and the overlay catalogues, and writes a versioned DATA PACKAGE:

    <out>/manifest.json              column specs, quantisation, counts, provenance, version
    <out>/main_catalogue.bin.gz      POSSUM column store (raw gzip)        -> hosted build
    <out>/sr_catalogue.bin.gz        SPICE-RACS column store (raw gzip)    -> hosted build
    <out>/overlays.json.gz           overlay catalogues (raw gzip JSON)    -> hosted build
    <out>/luts.json                  colormap LUTs
    <out>/*.b64                      base64 twins of the above             -> embedded build

Input locations are NOT hard-coded: they come from a sources JSON (default
build/sources.json, git-ignored — copy build/sources.example.json). Proprietary
inputs and the output package never enter the public repository.

    python3 build/build_payload.py --sources build/sources.json --version 2026-11 \
        --out data/2026-11
"""
import argparse, base64, gzip, io, json, re, sys, datetime
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
ap = argparse.ArgumentParser(description="Build the Sky Explorer data package")
ap.add_argument("--sources", type=Path, default=HERE / "sources.json",
                help="JSON with input paths (see sources.example.json)")
ap.add_argument("--out", type=Path, default=None,
                help="output package directory (default: data/<version>)")
ap.add_argument("--version", default=datetime.date.today().isoformat(),
                help="data version stamp written into the manifest")
ap.add_argument("--no-sr", action="store_true", help="skip SPICE-RACS")
args = ap.parse_args()

if not args.sources.exists():
    sys.exit(f"sources file {args.sources} not found — copy build/sources.example.json "
             f"to build/sources.json and fill in your local paths")
SRC = json.loads(args.sources.read_text())
OUT = args.out or (HERE.parent / "data" / args.version)
OUT.mkdir(parents=True, exist_ok=True)

SRC_POLSEL = SRC["possum_polsel_parquet"]
SRC_DEDUP = SRC["possum_dedup_parquet"]
DATA = HERE / "overlay_sources"          # overlay catalogue inputs (CSV/FITS)
VERSION = args.version

def write_pair(name: str, raw: bytes):
    """Write raw gzip (hosted build) and its base64 twin (embedded build)."""
    gz = gzip.compress(raw, 9)
    (OUT / name).write_bytes(gz)
    (OUT / (name + ".b64")).write_text(base64.b64encode(gz).decode())
    return gz

# ---------------------------------------------------------------- helpers
def b64gz(raw: bytes) -> str:
    return base64.b64encode(gzip.compress(raw, 9)).decode()

def qlog(v, lo, hi):
    """uint16 quantisation of log10(v) over [lo, hi] dex."""
    x = np.log10(np.clip(v.astype(float), 10**lo, 10**hi))
    return np.round((x - lo) / (hi - lo) * 65535).astype(np.uint16)

def qlin(v, lo, hi):
    x = np.clip(v.astype(float), lo, hi)
    return np.round((x - lo) / (hi - lo) * 65535).astype(np.uint16)

# ---------------------------------------------------------------- main catalogue
print("== main catalogue ==")
pol = pq.read_table(SRC_POLSEL).to_pandas()
ded = pq.read_table(SRC_DEDUP).to_pandas()
pol["cat_id"] = pol["cat_id"].astype(str)
sel = pol[pol["cat_id"].isin(set(ded["cat_id"].astype(str)))].copy()
# sort by galactic longitude for delta-friendly compression
sel = sel.sort_values(["l", "b"]).reset_index(drop=True)
n = len(sel)
print(f"selected {n:,} of {len(pol):,} rows (dedup mask: {len(ded):,})")

pat = re.compile(r"^SB(\d+)_component_(\d+)([a-z])$")
m = sel["cat_id"].str.extract(pat)
sbids = np.sort(sel["sbid"].unique())
sbid_idx = {s: i for i, s in enumerate(sbids)}
comp_num = m[1].astype(int).values
assert comp_num.max() < 65536, "component number no longer fits uint16"
comp_let = np.array([ord(c) - 97 for c in m[2]], dtype=np.uint8)

# fixed-point positions (1e-5 deg) with delta-encoded longitude (sorted by l),
# every column byte-shuffled: both make the gzip stream substantially smaller.
l32 = np.round((sel["l"].values % 360.0) * 100000).astype(np.uint32)
dl = np.diff(l32, prepend=np.uint32(0)).astype(np.uint32)   # cumsum restores l32
b32 = np.round((sel["b"].values + 90.0) * 100000).astype(np.uint32)

cols = {}
cols["l"]       = dl
cols["b"]       = b32
cols["rm"]      = sel["rm"].values.astype(np.float32)
Q = {  # uint16 log-quantised columns: name -> (source col, lo dex, hi dex)
    "rm_err":   ("rm_err",   -2.75, 1.15),
    "polint":   ("polint",   -4.10, 0.30),
    "fracpol":  ("fracpol",  -3.05, 0.30),
    "snr":      ("SNR_PI",    0.75, 4.25),
    "stokesI":  ("stokesI",  -3.40, 1.20),
}
for k, (src, lo, hi) in Q.items():
    cols[k] = qlog(sel[src].values, lo, hi)
cols["spidx"]   = np.round(np.clip(sel["spectral_index"].values, -9, 9) * 1000).astype(np.int16)
cols["polang"]  = np.round(np.clip(sel["derot_polangle"].values, 0, 180) / 180.0 * 255).astype(np.uint8)
cols["sbid"]    = sel["sbid"].map(sbid_idx).values.astype(np.uint16)
cols["compnum"] = comp_num.astype(np.uint16)
cols["complet"] = comp_let

def byte_shuffle(a):
    a = np.ascontiguousarray(a)
    return a.view(np.uint8).reshape(-1, a.dtype.itemsize).T.copy().tobytes()

order = ["l", "b", "rm", "rm_err", "polint", "fracpol", "snr", "stokesI",
         "spidx", "polang", "sbid", "compnum", "complet"]
buf = io.BytesIO()
colspec = []
for k in order:
    a = np.ascontiguousarray(cols[k])
    colspec.append(dict(name=k, dtype=str(a.dtype), offset=buf.tell(), bytes=a.nbytes,
                        shuffled=True))
    buf.write(byte_shuffle(a))
raw = buf.getvalue()
gz = write_pair("main_catalogue.bin.gz", raw)
print(f"raw {len(raw)/1e6:.1f} MB -> gz {len(gz)/1e6:.1f} MB")

manifest = dict(
    version=VERSION, built=datetime.datetime.now().isoformat(timespec="seconds"),
    survey="POSSUM DR1", n_sources=int(n),
    selection="goodpol, SNR_PI>=6, de-duplicated (one row per component)",
    source_files=dict(polsel=Path(SRC_POLSEL).name, dedup=Path(SRC_DEDUP).name),
    note="polsel snapshot 2026-01-26 covers 333,781 of the 336,283 components "
         "in the July dedup mask; missing rows are dominated by SB72954/SB75088.",
    columns=colspec,
    quant={k: dict(lo=lo, hi=hi, kind="log10-uint16") for k, (s, lo, hi) in Q.items()},
    quant_extra=dict(spidx="int16 x1000", polang="uint8 linear 0..180 deg (0.71 deg steps)",
                     positions="uint32 fixed-point 1e-5 deg; l delta-encoded; byte-shuffled"),
    sbids=[int(s) for s in sbids],
)
(OUT / "manifest.json").write_text(json.dumps(manifest))

# ---------------------------------------------------------------- SPICE-RACS
print("== SPICE-RACS ==")
SR_DIR = Path(SRC.get("spiceracs_extract_dir", "")) if not args.no_sr else None
if SR_DIR is None or not SR_DIR.exists():
    print("  (no SPICE-RACS extract dir — writing an empty SR package)")
SR_SELECTION = ("DR2 published; snr_polint>=6 & goodI_flag & ~leakage_flag; "
                "positional dedup 15 arcsec keep max-snr; all retained, with a flag "
                "marking sources within 0.4 deg of an embedded POSSUM component")

if SR_DIR is None or not SR_DIR.exists():
    write_pair("sr_catalogue.bin.gz", b"")
    manifest["sr"] = dict(n_sources=0, selection="none", columns=[], quant={}, tiles=[])
else:
    def sr_f8(name):
        return np.fromfile(SR_DIR / f"{name}.f8.bin", dtype="<f8")

    def build_sr_keep():
        """Replicate the notebook's dedup; return (dedup_indices, in_possum_flag)."""
        from scipy.spatial import cKDTree
        ra, dec = sr_f8("ra"), sr_f8("dec")
        snr = sr_f8("snr_polint")
        nsr = ra.size
        def uv(lon, lat):
            lo, la = np.radians(lon), np.radians(lat)
            return np.column_stack([np.cos(la)*np.cos(lo), np.cos(la)*np.sin(lo), np.sin(la)])
        tree = cKDTree(uv(ra, dec))
        pairs = tree.query_pairs(2*np.sin(np.radians(15/3600)/2), output_type="ndarray")
        parent = np.arange(nsr)
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for a_, b_ in pairs:
            ra_, rb_ = find(a_), find(b_)
            if ra_ != rb_:
                parent[rb_] = ra_
        roots = np.array([find(i) for i in range(nsr)])
        keep = np.zeros(nsr, bool)
        seen = set()
        for i in np.argsort(-snr):
            r = roots[i]
            if r not in seen:
                seen.add(r)
                keep[i] = True
        lg, bg = sr_f8("l"), sr_f8("b")
        ptree = cKDTree(uv(sel["l"].values, sel["b"].values))
        d, _ = ptree.query(uv(lg[keep], bg[keep]), k=1, workers=-1)
        sepd = np.degrees(2*np.arcsin(np.clip(d/2, 0, 1)))
        return np.nonzero(keep)[0], (sepd <= 0.4).astype(np.uint8)

    sr_idx, sr_inp = build_sr_keep()
    nsr = sr_idx.size
    print(f"SR embedded: {nsr:,} ({int(sr_inp.sum()):,} inside POSSUM coverage)")

    sr_cat = np.fromfile(SR_DIR / "cat_id.18s.bin", dtype="S18")[sr_idx]
    sr_tiles_all = np.array([s.decode().strip().split("_")[1] for s in sr_cat])
    sr_nums_all = np.array([int(s.decode().strip().split("_")[2]) for s in sr_cat], dtype=np.uint16)
    sr_l = sr_f8("l")[sr_idx] % 360.0
    sr_b = sr_f8("b")[sr_idx]
    srt = np.lexsort((sr_b, sr_l))          # sort by l for delta coding
    sr_l, sr_b = sr_l[srt], sr_b[srt]
    sr_tiles_all, sr_nums_all = sr_tiles_all[srt], sr_nums_all[srt]
    sr_inp = sr_inp[srt]
    tiles = sorted(set(sr_tiles_all))
    tile_idx = {t: i for i, t in enumerate(tiles)}

    SRQ = {  # SR quantisation windows (wider than POSSUM where SR ranges demand)
        "rm_err":  ("rm_err",         -2.0, 1.60),
        "polint":  ("polint",         -3.6, 0.45),
        "fracpol": ("fracpol",        -3.0, 0.42),
        "snr":     ("snr_polint",      0.75, 3.50),
        "stokesI": ("stokesI",        -3.0, 1.75),
    }
    sr_l32 = np.round(sr_l * 100000).astype(np.uint32)
    sr_cols = {}
    sr_cols["l"] = np.diff(sr_l32, prepend=np.uint32(0)).astype(np.uint32)
    sr_cols["b"] = np.round((sr_b + 90.0) * 100000).astype(np.uint32)
    sr_cols["rm"] = sr_f8("rm")[sr_idx][srt].astype(np.float32)
    for k, (src, lo, hi) in SRQ.items():
        v = sr_f8(src)[sr_idx][srt]
        v = np.where(np.isfinite(v), v, 10**lo)      # NaN -> floor sentinel
        sr_cols[k] = qlog(v, lo, hi)
    spx = sr_f8("spectral_index")[sr_idx][srt]
    sr_cols["spidx"] = np.round(np.clip(np.where(np.isfinite(spx), spx, 0), -9, 9) * 1000).astype(np.int16)
    pang = sr_f8("derot_polangle")[sr_idx][srt]
    sr_cols["polang"] = np.round(np.clip(np.where(np.isfinite(pang), pang, 0), 0, 180) / 180.0 * 255).astype(np.uint8)
    sr_cols["tile"] = np.array([tile_idx[t] for t in sr_tiles_all], dtype=np.uint16)
    sr_cols["num"] = sr_nums_all
    sr_cols["inp"] = sr_inp        # 1 = within 0.4 deg of a POSSUM component

    sr_order = ["l", "b", "rm", "rm_err", "polint", "fracpol", "snr", "stokesI",
                "spidx", "polang", "tile", "num", "inp"]
    buf = io.BytesIO()
    sr_colspec = []
    for k in sr_order:
        a = np.ascontiguousarray(sr_cols[k])
        sr_colspec.append(dict(name=k, dtype=str(a.dtype), offset=buf.tell(), bytes=a.nbytes,
                               shuffled=True))
        buf.write(byte_shuffle(a))
    sr_gz = write_pair("sr_catalogue.bin.gz", buf.getvalue())
    print(f"SR raw {buf.tell()/1e6:.1f} MB -> gz {len(sr_gz)/1e6:.1f} MB")

    manifest["sr"] = dict(
        n_sources=int(nsr),
        selection=SR_SELECTION,
        source_file="spice-racs.dr2.published.fits (2026-08 copy)",
        columns=sr_colspec,
        quant={k: dict(lo=lo, hi=hi, kind="log10-uint16") for k, (s, lo, hi) in SRQ.items()},
        tiles=tiles,
    )
(OUT / "manifest.json").write_text(json.dumps(manifest))

# ---------------------------------------------------------------- overlays
print("== overlays ==")
overlays = {}

def gal_from_eq(ra, dec):
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    c = SkyCoord(np.asarray(ra, float) * u.deg, np.asarray(dec, float) * u.deg,
                 frame="icrs").galactic
    return np.asarray(c.l.deg), np.asarray(c.b.deg)

from astropy.cosmology import FlatLambdaCDM
COSMO = FlatLambdaCDM(H0=70, Om0=0.3)

def theta500_deg(m500_1e14, z):
    """Angular radius (deg) subtended by R500 for M500 [1e14 Msun] at z."""
    m = np.asarray(m500_1e14, float) * 1e14 * 1.989e30           # kg
    zz = np.clip(np.asarray(z, float), 1e-3, None)
    rho_c = COSMO.critical_density(zz).si.value                  # kg/m3
    r500 = (3 * m / (4 * np.pi * 500 * rho_c)) ** (1 / 3)        # m
    dA = COSMO.angular_diameter_distance(zz).si.value            # m
    return np.degrees(r500 / dA)

# ---- clusters: MCXC-II + PSZ2 + ACT DR5, de-duplicated in that priority ----
mc = pd.read_csv(DATA / "mcxc2.csv.gz")
mc = mc[np.isfinite(mc["z"]) & np.isfinite(mc["M500"]) & (mc["z"] > 0)]
mname = mc["Aname"].fillna("").astype(str)
mname = np.where(mname.str.len() > 1, mname, mc["MCXC"].astype(str))
cl = pd.DataFrame(dict(name=mname, ra=mc["RAdeg"], dec=mc["DEdeg"], z=mc["z"],
                       m500=mc["M500"], src="MCXC-II"))

ps = pd.read_csv(DATA / "Catalogo.csv", sep=";", decimal=",")
for c in ["ra", "dec", "redshift", "mass_sz"]:
    ps[c] = pd.to_numeric(ps[c].astype(str).str.replace(",", "."), errors="coerce")
ps = ps[(ps["redshift"] > 0) & (ps["mass_sz"] > 0)]
cl2 = pd.DataFrame(dict(name=ps["name"].astype(str).str.strip(), ra=ps["ra"], dec=ps["dec"],
                        z=ps["redshift"], m500=ps["mass_sz"], src="PSZ2"))

from astropy.io import fits
ACT_FITS = DATA / "DR5_cluster-catalog_v1.1.fits"
if ACT_FITS.exists():
    act = fits.open(ACT_FITS)[1].data
else:
    print("  (DR5_cluster-catalog_v1.1.fits not present — skipping ACT DR5)")
    act = {"redshift": np.array([]), "M500cCal": np.array([]), "name": np.array([]),
           "RADeg": np.array([]), "decDeg": np.array([])}
ok = np.isfinite(act["redshift"]) & (act["redshift"] > 0) & np.isfinite(act["M500cCal"]) & (act["M500cCal"] > 0)
cl3 = pd.DataFrame(dict(name=[str(x) for x in act["name"][ok]],
                        ra=act["RADeg"][ok].astype(float), dec=act["decDeg"][ok].astype(float),
                        z=act["redshift"][ok].astype(float), m500=act["M500cCal"][ok].astype(float),
                        src="ACT-DR5"))

def dedup_sky(base, add, sep_deg=0.12):
    """Append rows of `add` whose position is not within sep_deg of `base`."""
    from scipy.spatial import cKDTree
    def uv(r, d):
        r, d = np.radians(np.asarray(r, float)), np.radians(np.asarray(d, float))
        return np.column_stack([np.cos(d) * np.cos(r), np.cos(d) * np.sin(r), np.sin(d)])
    t = cKDTree(uv(base["ra"], base["dec"]))
    dist, _ = t.query(uv(add["ra"], add["dec"]), k=1)
    keep = dist > 2 * np.sin(np.radians(sep_deg) / 2)
    return pd.concat([base, add[keep]], ignore_index=True)

cl = dedup_sky(dedup_sky(cl, cl2), cl3)
gl, gb = gal_from_eq(cl["ra"], cl["dec"])
th500 = theta500_deg(cl["m500"], cl["z"])
overlays["clusters"] = dict(
    label="Galaxy clusters (MCXC-II + PSZ2 + ACT DR5)",
    kind="circles",
    desc="X-ray/SZ-selected clusters; circle = R500, dashed = ~Rvir (1.36 x R500).",
    fields=["name", "l", "b", "z", "m500", "th500", "src"],
    filters=[dict(field="z", label="redshift", min=0.0, max=1.5),
             dict(field="m500", label="M500 / 10^14 Msun", min=0.0, max=25.0, log=True),
             dict(field="th500", label="theta500 / deg", min=0.0, max=3.0, log=True)],
    rows=[[nm, round(float(a), 3), round(float(bb), 3),
           round(float(z), 3), round(float(m), 2), round(float(t), 3), s]
          for nm, a, bb, z, m, t, s in zip(cl["name"], gl, gb,
                                           cl["z"], cl["m500"], th500, cl["src"])],
)
print(f"clusters: {len(cl):,}")

# ---- eRASS1 primary cluster catalogue (Bulbul et al. 2024) ----
ER_FITS = DATA / "erass1cl_primary_v3.2.fits"
er = fits.open(ER_FITS)[1].data if ER_FITS.exists() else None
if er is None:
    print("  (erass1cl_primary_v3.2.fits not present — skipping eRASS1 overlay)")
    ez = np.array([]); em = np.array([]); er500 = np.array([]); eok = np.array([], bool)
    egl = egb = eth = np.array([])
else:
  ez = np.asarray(er["BEST_Z"], float)
  em = np.asarray(er["M500"], float) / 10.0        # 1e13 -> 1e14 Msun
  er500 = np.asarray(er["R500"], float) / 1000.0   # kpc -> Mpc
  eok = np.isfinite(ez) & (ez > 0) & np.isfinite(em) & (em > 0)
  egl, egb = gal_from_eq(np.asarray(er["RA"], float)[eok], np.asarray(er["DEC"], float)[eok])
  edA = COSMO.angular_diameter_distance(np.clip(ez[eok], 1e-3, None)).to_value("Mpc")
  eth = np.degrees(er500[eok] / edA)
if er is not None: overlays["erass1"] = dict(
    label="eRASS1 clusters (Bulbul et al. 2024)",
    kind="circles",
    desc="eROSITA first-survey primary cluster sample; circle = R500 (catalogue), faint = ~Rvir.",
    fields=["name", "l", "b", "z", "m500", "th500"],
    filters=[dict(field="z", label="redshift", min=0.0, max=1.4),
             dict(field="m500", label="M500 / 10^14 Msun", min=0.0, max=25.0, log=True),
             dict(field="th500", label="theta500 / deg", min=0.0, max=2.0, log=True)],
    rows=[[str(nm).strip(), round(float(a), 3), round(float(bb), 3), round(float(z), 3),
           round(float(m), 2), round(float(t), 3)]
          for nm, a, bb, z, m, t in zip(np.asarray(er["NAME"])[eok], egl, egb,
                                        ez[eok], em[eok], eth)],
)
if er is not None: print(f"eRASS1: {int(eok.sum()):,}")

# ---- Kourkchi & Tully 2017 groups + galaxies ----
kt = pd.read_csv(DATA / "all.iter.2.v40.group", sep=r"\s*\|\s*", engine="python",
                 skiprows=[1])
kt.columns = [c.strip().lstrip("#").strip() for c in kt.columns]
kt = kt.apply(pd.to_numeric, errors="coerce")
grp = kt[kt["flag"] == 2].copy()
# Angular second-turnaround radius: KT17's own R_theta column (radians) where valid;
# fall back to R2t_lum / distance with distance = mDist, else Vls/74.6 Mpc.
rth = grp["R_theta"].values.astype(float)
r2t = grp["R2t_lum"].values.astype(float)
dist = grp["mDist"].values.astype(float)
vdist = np.clip(grp["Vls"].values.astype(float), 100, None) / 74.6
dist = np.where(dist > 0.2, dist, vdist)
th2t = np.where(rth > 1e-5, np.degrees(rth), np.degrees(np.arctan2(r2t, dist)))
th2t = np.clip(np.where(np.isfinite(th2t), th2t, 0.1), 0.02, 25.0)
overlays["ktgroups"] = dict(
    label="Galaxy groups (Kourkchi & Tully 2017)",
    kind="circles",
    desc="Local-volume groups (cz < 3500 km/s); circle = second-turnaround radius R2t.",
    fields=["name", "l", "b", "vls", "dist", "logMlum", "ngal", "th2t"],
    filters=[dict(field="vls", label="V_LS / km/s", min=0, max=3600),
             dict(field="ngal", label="members", min=1, max=300, log=True),
             dict(field="logMlum", label="log10 M_lum / Msun", min=9.0, max=15.5)],
    rows=[[f"PGC{int(p)}", round(float(l), 3), round(float(b), 3), int(v), round(float(d), 1),
           round(float(np.log10(max(m, 1e8))), 1), int(ng), round(float(t), 3)]
          for p, l, b, v, d, m, ng, t in zip(grp["pgc"], grp["gl"], grp["gb"], grp["Vls"],
                                             grp["mDist"], grp["Mv_lum"], grp["No_Galaxies"], th2t)],
)
gal = kt[kt["flag"].isin([0, 1])].copy()
overlays["ktgalaxies"] = dict(
    label="Local-volume galaxies (Kourkchi & Tully 2017)",
    kind="points",
    desc="16.5k galaxies with cz < 3500 km/s.",
    fields=["name", "l", "b", "vls", "ks"],
    filters=[dict(field="vls", label="V_LS / km/s", min=0, max=3600),
             dict(field="ks", label="Ks mag", min=0.0, max=14.0)],
    rows=[[f"PGC{int(p)}", round(float(l), 3), round(float(b), 3), int(v),
           round(float(k), 1) if np.isfinite(k) else 99.0]
          for p, l, b, v, k in zip(gal["pgc"], gal["gl"], gal["gb"], gal["Vls"], gal["Ks"])],
)
print(f"KT17: {len(grp):,} groups, {len(gal):,} galaxies")

# ---- OpenNGC galaxies ----
ngc = pd.read_csv(DATA / "NGC.csv", sep=";")
g = ngc[ngc["Type"].isin(["G", "GPair", "GTrpl", "GGroup"])].copy()
g = g.dropna(subset=["RA", "Dec"])
def sex2deg(s, ra=False):
    p = [float(x) for x in str(s).replace("+", " ").split(":")]
    sign = -1 if str(s).strip().startswith("-") else 1
    v = abs(p[0]) + p[1] / 60 + p[2] / 3600
    return v * 15 if ra else sign * v
g["ra"] = g["RA"].apply(lambda s: sex2deg(s, True))
g["dec"] = g["Dec"].apply(lambda s: sex2deg(s, False))
mag = g["V-Mag"].fillna(g["B-Mag"])
g = g[np.isfinite(mag)]
mag = mag[np.isfinite(mag)]
gl, gb = gal_from_eq(g["ra"], g["dec"])
common = g["Common names"].fillna("").astype(str)
disp = np.where(common.str.len() > 1, g["Name"].astype(str) + " (" + common.str.split(",").str[0] + ")",
                g["Name"].astype(str))
overlays["ngc"] = dict(
    label="NGC/IC galaxies (OpenNGC)",
    kind="points",
    desc="NGC + IC galaxies with V (or B) magnitude; size filter uses major axis.",
    fields=["name", "l", "b", "mag", "majax", "cz"],
    filters=[dict(field="mag", label="V mag", min=4.0, max=18.0),
             dict(field="majax", label="major axis / arcmin", min=0.0, max=700.0, log=True)],
    rows=[[nm, round(float(a), 3), round(float(bb), 3), round(float(m), 1),
           round(float(mx), 1) if np.isfinite(mx) else 0.0,
           int(v) if np.isfinite(v) else -99999]
          for nm, a, bb, m, mx, v in zip(disp, gl, gb, mag, g["MajAx"], g["RadVel"])],
)
print(f"NGC/IC galaxies: {len(g):,}")

# ---- ATNF pulsars (with RM where measured) ----
rows = []
pat = re.compile(r"^\s*\d+\s+(\S+)\s+(\S+)\s+([+\-]\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)")
PSR_FILE = Path(SRC.get("atnf_pulsar_dat", ""))
for line in (open(PSR_FILE) if PSR_FILE.exists() else []):
    if line.startswith("#") or line.startswith("---") or not line.strip():
        continue
    p = line.split()
    if len(p) < 8 or not p[0].isdigit():
        continue
    try:
        raj, dcj = p[1], p[3]
        rm = np.nan if p[5] == "*" else float(p[5])
        s1400 = np.nan if p[7] == "*" else float(p[7])
        rows.append((raj, dcj, rm, s1400))
    except (ValueError, IndexError):
        continue
pu = pd.DataFrame(rows, columns=["raj", "dcj", "rm", "s1400"])
def hms2deg(s):
    p = [float(x) for x in s.split(":")] + [0, 0]
    return (p[0] + p[1] / 60 + p[2] / 3600) * 15
def dms2deg(s):
    sign = -1 if s.startswith("-") else 1
    p = [float(x) for x in s.lstrip("+-").split(":")] + [0, 0]
    return sign * (p[0] + p[1] / 60 + p[2] / 3600)
def psr_name(raj, dcj):
    rp = raj.split(":") + ["00"]
    dp = dcj.lstrip("+-").split(":") + ["00"]
    sign = "-" if dcj.startswith("-") else "+"
    return f"PSR J{rp[0]}{rp[1]}{sign}{dp[0]}{dp[1]}"
pu["ra"] = pu["raj"].apply(hms2deg)
pu["dec"] = pu["dcj"].apply(dms2deg)
gl, gb = gal_from_eq(pu["ra"], pu["dec"])
overlays["pulsars"] = dict(
    label="ATNF pulsars",
    kind="points",
    desc="ATNF pulsar catalogue; markers coloured by pulsar RM where measured.",
    fields=["name", "l", "b", "rm", "s1400"],
    filters=[dict(field="s1400", label="S1400 / mJy", min=0.0, max=1200.0, log=True),
             dict(field="rm", label="|RM| / rad m^-2", min=0.0, max=3000.0, absval=True)],
    rows=[[psr_name(r, d),
           round(float(a), 3), round(float(bb), 3),
           round(float(rm), 1) if np.isfinite(rm) else None,
           round(float(s), 2) if np.isfinite(s) else None]
          for r, d, rm, s, a, bb in zip(pu["raj"].str[:5], pu["dcj"], pu["rm"], pu["s1400"], gl, gb)],
)
print(f"pulsars: {len(pu):,} ({np.isfinite(pu['rm']).sum()} with RM)")

# ---- curated famous objects ----
from famous_objects import FAMOUS as famous
ra = [f[1] for f in famous]; dec = [f[2] for f in famous]
gl, gb = gal_from_eq(ra, dec)
overlays["famous"] = dict(
    label="Objects of interest",
    kind="labels",
    desc="Curated nearby galaxies, clusters, radio sources and Galactic objects.",
    fields=["name", "l", "b", "type", "size", "note"],
    filters=[],
    rows=[[f[0], round(float(a), 3), round(float(bb), 3), f[3], f[4], f[5]]
          for f, a, bb in zip(famous, gl, gb)],
)
print(f"famous: {len(famous)}")

def sanitize(o):
    if isinstance(o, dict):
        return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, list):
        return [sanitize(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o

overlays = sanitize(overlays)
ov_json = json.dumps(overlays, separators=(",", ":"), allow_nan=False)
ov_gz = write_pair("overlays.json.gz", ov_json.encode())
print(f"overlays json {len(ov_json)/1e6:.2f} MB -> gz {len(ov_gz)/1e6:.2f} MB")

# ---------------------------------------------------------------- colormap LUTs
print("== LUTs ==")
from make_luts import make_luts
luts = make_luts()
(OUT / "luts.json").write_text(json.dumps(luts, separators=(",", ":")))
(OUT / "manifest.json").write_text(json.dumps(manifest))
print(f"\nData package {VERSION} written to {OUT}")
