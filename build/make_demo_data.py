#!/usr/bin/env python3
"""
Generate a SYNTHETIC demo data package for developing the POSSUM Sky Explorer
without access to the proprietary catalogue.

The output has exactly the structure build_payload.py produces (same manifest
schema, column store encoding and overlay format), so every viewer feature works —
tessellation, filters, blink, region analysis, DS9 export — on fake but physically
plausible data: a Galactic-latitude-dependent RM foreground, random fields of
POSSUM-like coverage, a southern-sky SPICE-RACS-like layer, a few injected
"discoveries" (an RM-enhanced cluster, a sign-reversal patch), plus the public
curated-object overlay. Nothing in it is a measurement.

    python3 build/make_demo_data.py --out data/demo
    python3 build/assemble.py --data data/demo --out dist-demo
"""
import argparse, base64, gzip, io, json, datetime, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from famous_objects import FAMOUS
from make_luts import make_luts

ap = argparse.ArgumentParser()
ap.add_argument("--out", type=Path, default=HERE.parent / "data" / "demo")
ap.add_argument("--n-possum", type=int, default=60000)
ap.add_argument("--n-sr", type=int, default=30000)
ap.add_argument("--seed", type=int, default=42)
args = ap.parse_args()
rng = np.random.default_rng(args.seed)
OUT = args.out
OUT.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------ helpers (mirror build_payload)
def qlog(v, lo, hi):
    x = np.log10(np.clip(v.astype(float), 10**lo, 10**hi))
    return np.round((x - lo) / (hi - lo) * 65535).astype(np.uint16)

def byte_shuffle(a):
    a = np.ascontiguousarray(a)
    return a.view(np.uint8).reshape(-1, a.dtype.itemsize).T.copy().tobytes()

def write_pair(name, raw):
    gz = gzip.compress(raw, 9)
    (OUT / name).write_bytes(gz)
    (OUT / (name + ".b64")).write_text(base64.b64encode(gz).decode())
    return gz

def pack(cols, order):
    buf = io.BytesIO(); spec = []
    for k in order:
        a = np.ascontiguousarray(cols[k])
        spec.append(dict(name=k, dtype=str(a.dtype), offset=buf.tell(), bytes=a.nbytes, shuffled=True))
        buf.write(byte_shuffle(a))
    return buf.getvalue(), spec

GAL_R = np.array([[-0.0548755604, -0.8734370902, -0.4838350155],
                  [ 0.4941094279, -0.4448296300,  0.7469822445],
                  [-0.8676661490, -0.1980763734,  0.4559837762]])
def uv(lon, lat):
    lo, la = np.radians(lon), np.radians(lat)
    return np.column_stack([np.cos(la)*np.cos(lo), np.cos(la)*np.sin(lo), np.sin(la)])
def lonlat(v):
    return (np.degrees(np.arctan2(v[:, 1], v[:, 0])) % 360, np.degrees(np.arcsin(np.clip(v[:, 2], -1, 1))))
def gal_from_eq(ra, dec):
    return lonlat(uv(ra, dec) @ GAL_R.T)
def eq_from_gal(l, b):
    return lonlat(uv(l, b) @ GAL_R)

# ------------------------------------------------------------------ a fake sky
def foreground_rm(l, b):
    """Smooth, plausible Galactic RM pattern (rad/m2) + sign structure."""
    lr = np.radians(l)
    return (120*np.sin(lr)*np.exp(-np.abs(b)/12) + 25*np.cos(2*lr)*np.exp(-np.abs(b)/35)
            - 8*np.sign(b)*np.exp(-np.abs(b)/50))

def synth_sources(n, lon, lat, dense=True):
    rm = foreground_rm(lon, lat)
    # intrinsic scatter grows toward the plane
    rm = rm + rng.normal(0, 8 + 40*np.exp(-np.abs(lat)/10), n)
    # injected "discoveries": an RM-enhanced cluster and a sign-reversal patch
    for (cl, cb, rad, amp) in [(300.0, -35.0, 1.5, 90.0), (250.0, -50.0, 2.5, -60.0)]:
        d = np.degrees(np.arccos(np.clip(uv(lon, lat) @ uv([cl], [cb])[0], -1, 1)))
        rm += amp*np.exp(-(d/rad)**2)
    snr = np.exp(rng.normal(np.log(14), 0.9, n)); snr = np.clip(snr, 6, 3000)
    polint = snr*rng.lognormal(np.log(2.8e-5), 0.35, n)
    fracpol = np.clip(rng.lognormal(np.log(0.045), 0.7, n), 0.002, 0.9)
    stokesI = np.clip(polint/fracpol, 5e-4, 20)
    rm_err = np.clip(12.0/snr*rng.lognormal(0, 0.2, n), 0.02, 20)
    spidx = rng.normal(-0.75, 0.3, n)
    polang = (rng.uniform(0, 180, n))
    return dict(rm=rm, snr=snr, polint=polint, fracpol=fracpol, stokesI=stokesI,
                rm_err=rm_err, spidx=spidx, polang=polang)

# POSSUM-like coverage: ~90 circular fields (5.5 deg) scattered over the southern sky
nf = 90
fl = rng.uniform(0, 360, nf); fb = np.degrees(np.arcsin(rng.uniform(-0.98, 0.25, nf)))
per = rng.multinomial(args.n_possum, np.ones(nf)/nf)
L, B = [], []
for i in range(nf):
    r = 5.5*np.sqrt(rng.uniform(0, 1, per[i])); th = rng.uniform(0, 2*np.pi, per[i])
    c = uv([fl[i]], [fb[i]])[0]
    a = np.array([0, 0, 1.0]) if abs(c[2]) < 0.9 else np.array([1.0, 0, 0])
    u = np.cross(c, a); u /= np.linalg.norm(u); w = np.cross(c, u)
    v = (np.cos(np.radians(r))[:, None]*c + np.sin(np.radians(r))[:, None]*(np.cos(th)[:, None]*u + np.sin(th)[:, None]*w))
    ll, bb = lonlat(v); L.append(ll); B.append(bb)
pl, pb = np.concatenate(L), np.concatenate(B)
nP = pl.size
o = np.lexsort((pb, pl)); pl, pb = pl[o], pb[o]
P = synth_sources(nP, pl, pb)

Q = {"rm_err": (-2.75, 1.15), "polint": (-4.10, 0.30), "fracpol": (-3.05, 0.30),
     "snr": (0.75, 4.25), "stokesI": (-3.40, 1.20)}
l32 = np.round(pl*100000).astype(np.uint32)
cols = {"l": np.diff(l32, prepend=np.uint32(0)).astype(np.uint32),
        "b": np.round((pb + 90)*100000).astype(np.uint32),
        "rm": P["rm"].astype(np.float32)}
for k, (lo, hi) in Q.items(): cols[k] = qlog(P[k], lo, hi)
cols["spidx"] = np.round(np.clip(P["spidx"], -9, 9)*1000).astype(np.int16)
cols["polang"] = np.round(P["polang"]/180*255).astype(np.uint8)
sbids = list(range(90001, 90001 + nf))
field_of = np.concatenate([np.full(per[i], i) for i in range(nf)])[o]
cols["sbid"] = field_of.astype(np.uint16)
cols["compnum"] = (rng.integers(1, 20000, nP)).astype(np.uint16)
cols["complet"] = np.zeros(nP, np.uint8)
raw, spec = pack(cols, ["l", "b", "rm", "rm_err", "polint", "fracpol", "snr", "stokesI",
                        "spidx", "polang", "sbid", "compnum", "complet"])
write_pair("main_catalogue.bin.gz", raw)
version = "demo-" + datetime.date.today().isoformat()
manifest = dict(
    version=version, built=datetime.datetime.now().isoformat(timespec="seconds"),
    demo=True, survey="SYNTHETIC DEMO (not real data)", n_sources=int(nP),
    selection="synthetic sources, random fields, analytic RM foreground + injected features",
    note="THIS IS SYNTHETIC DEMO DATA generated by build/make_demo_data.py for development. "
         "Nothing here is a measurement.",
    columns=spec,
    quant={k: dict(lo=lo, hi=hi, kind="log10-uint16") for k, (lo, hi) in Q.items()},
    quant_extra=dict(spidx="int16 x1000", polang="uint8 linear 0..180 deg",
                     positions="uint32 fixed-point 1e-5 deg; l delta-encoded; byte-shuffled"),
    sbids=sbids,
)

# SPICE-RACS-like layer: whole southern sky, sparser
nS = args.n_sr
sl = rng.uniform(0, 360, nS); sb = np.degrees(np.arcsin(rng.uniform(-0.999, 0.45, nS)))
o = np.lexsort((sb, sl)); sl, sb = sl[o], sb[o]
S = synth_sources(nS, sl, sb)
from scipy.spatial import cKDTree
d, _ = cKDTree(uv(pl, pb)).query(uv(sl, sb), k=1)
inp = (np.degrees(2*np.arcsin(np.clip(d/2, 0, 1))) <= 0.4).astype(np.uint8)
SRQ = {"rm_err": (-2.0, 1.60), "polint": (-3.6, 0.45), "fracpol": (-3.0, 0.42),
       "snr": (0.75, 3.50), "stokesI": (-3.0, 1.75)}
sl32 = np.round(sl*100000).astype(np.uint32)
scols = {"l": np.diff(sl32, prepend=np.uint32(0)).astype(np.uint32),
         "b": np.round((sb + 90)*100000).astype(np.uint32),
         "rm": S["rm"].astype(np.float32)}
for k, (lo, hi) in SRQ.items(): scols[k] = qlog(S[k], lo, hi)
scols["spidx"] = np.round(np.clip(S["spidx"], -9, 9)*1000).astype(np.int16)
scols["polang"] = np.round(S["polang"]/180*255).astype(np.uint8)
tiles = [f"{h:02d}{m:02d}{'+' if dd >= 0 else '-'}{abs(dd):02d}" for h in range(0, 24, 2) for m in (0, 30) for dd in (-60, -30, 0, 30)]
scols["tile"] = rng.integers(0, len(tiles), nS).astype(np.uint16)
scols["num"] = rng.integers(1, 9000, nS).astype(np.uint16)
scols["inp"] = inp
sraw, sspec = pack(scols, ["l", "b", "rm", "rm_err", "polint", "fracpol", "snr", "stokesI",
                           "spidx", "polang", "tile", "num", "inp"])
write_pair("sr_catalogue.bin.gz", sraw)
manifest["sr"] = dict(n_sources=int(nS), selection="synthetic", columns=sspec,
                      quant={k: dict(lo=lo, hi=hi, kind="log10-uint16") for k, (lo, hi) in SRQ.items()},
                      tiles=tiles)

# overlays: the public curated list + a synthetic cluster catalogue matching the injected feature
gl, gb = gal_from_eq(np.array([f[1] for f in FAMOUS]), np.array([f[2] for f in FAMOUS]))
overlays = {
    "famous": dict(label="Objects of interest", kind="labels",
        desc="Curated nearby galaxies, clusters, radio sources and Galactic objects (real positions).",
        fields=["name", "l", "b", "type", "size", "note"], filters=[],
        rows=[[f[0], round(float(a), 4), round(float(bb), 4), f[3], f[4], f[5]] for f, a, bb in zip(FAMOUS, gl, gb)]),
    "clusters": dict(label="Synthetic clusters (demo)", kind="circles",
        desc="Fake cluster catalogue; the one at l=300 b=-35 sits on an injected RM enhancement.",
        fields=["name", "l", "b", "z", "m500", "th500", "src"],
        filters=[dict(field="z", label="redshift", min=0.0, max=1.5),
                 dict(field="m500", label="M500 / 10^14 Msun", min=0.0, max=25.0, log=True),
                 dict(field="th500", label="theta500 / deg", min=0.0, max=3.0, log=True)],
        rows=[["DEMO-CL-0001", 300.0, -35.0, 0.04, 6.0, 0.7, "demo"]] +
             [[f"DEMO-CL-{i:04d}", round(float(x), 3), round(float(y), 3), round(float(z), 3),
               round(float(m), 2), round(float(t), 3), "demo"]
              for i, (x, y, z, m, t) in enumerate(zip(rng.uniform(0, 360, 400), np.degrees(np.arcsin(rng.uniform(-0.99, 0.3, 400))),
                                                        rng.uniform(0.02, 0.6, 400), rng.lognormal(np.log(3), 0.6, 400),
                                                        rng.lognormal(np.log(0.12), 0.6, 400)), start=2)]),
}
ov = json.dumps(overlays, separators=(",", ":"), allow_nan=False).encode()
write_pair("overlays.json.gz", ov)
(OUT / "luts.json").write_text(json.dumps(make_luts(), separators=(",", ":")))
(OUT / "manifest.json").write_text(json.dumps(manifest))
print(f"demo package {version}: {nP:,} POSSUM-like + {nS:,} SR-like synthetic sources -> {OUT}")
