import numpy as np, os, json, time, sys

SRC = os.path.expanduser('~/mnt/SPICE-RACS_DR2_data_validation/data/spice-racs.dr2.published.fits')
OUT = os.path.expanduser('~/mnt/SPICE-RACS_data/claude_sr_extract')
DATA_START, NAXIS1, NROWS = 100800, 1030, 9294225

# column -> (offset, fmt) computed from the TFORM list
forms = [('cat_id','18A'),('ra','D'),('ra_err','D'),('dec','D'),('dec_err','D'),
('total_I_flux','D'),('total_I_flux_err','D'),('peak_I_flux','D'),('peak_I_flux_err','D'),
('maj_axis','D'),('maj_axis_err','D'),('min_axis','D'),('min_axis_err','D'),('pa','D'),('pa_err','D'),
('dc_maj_axis','D'),('dc_maj_axis_err','D'),('dc_min_axis','D'),('dc_min_axis_err','D'),
('dc_pa','D'),('dc_pa_err','D'),('stokesI_err','D'),('stokesQ_err','D'),('stokesU_err','D'),
('stokesI_bkg','D'),('stokesQ_bkg','D'),('stokesU_bkg','D'),('beamdist','D'),('N_Gaus','K'),
('source_id','18A'),('tile_id','12A'),('sbid','K'),('start_time','D'),('separation_tile_centre','D'),
('s_code','1A'),('rm','D'),('rm_err','D'),('polint','D'),('polint_err','D'),('stokesQ','D'),
('stokesU','D'),('polangle','D'),('polangle_err','D'),('derot_polangle','D'),('derot_polangle_err','D'),
('fracpol','D'),('reffreq_pol','D'),('reffreq_beam','D'),('reffreq_I','D'),('fdf_noise_th','D'),
('rmsf_fwhm','D'),('refwave_sq_pol','D'),('stokesI','D'),
('f54','L'),('f55','L'),('f56','L'),('f57','L'),('stokesI_chi2_red','D'),('snr_polint','D'),
('minfreq','D'),('maxfreq','D'),('channelwidth','D'),('Nchan','K'),('rm_width','D'),
('coef','51A'),('coeferr','53A'),('model_order','D'),('noise_chan','D'),('fdf_noise_mad','D'),
('fdf_noise_rms','D'),('beam_maj','D'),('beam_min','D'),('beam_pa','D'),('l_tile','D'),('m_tile','D'),
('sigma_add','D'),('sigma_add_err','D'),('snr_flag','L'),('leakage_flag','L'),('channel_flag','L'),
('stokesI_fit_flag','L'),('cs_flag','L'),('cm_flag','L'),('local_rm_flag','L'),('is_blended_flag','L'),
('blend_ratio','D'),('N_blended','K'),('spectral_index','D'),('spectral_index_err','D'),
('int_time','D'),('epoch','D'),('l','D'),('b','D'),('pos_err','D'),('rm_method','38A'),
('telescope','5A'),('pol_bias','19A'),('ionosphere','5A'),('flux_type','4A'),('aperture','D'),
('leakage','D'),('complex_flag','L'),('rm_width_err','E'),('complex_test','1A'),('Ncomp','J'),
('fracpol_err','E'),('stokesV','E'),('stokesV_err','E'),('obs_interval','E'),('catalog_name','14A'),
('dataref','44A'),('type','4A'),('notes','4A'),('goodI_flag','L'),('goodRM_flag','L'),
('nn_rm_count','J'),('nn_rm_med','D'),('nn_rm_mean','D'),('nn_rm_mad_std','D'),('nn_rm_std','D'),
('nn_rm_se','D'),('nn_rm_wmean','D'),('nn_rm_wmean_err','D'),('nn_rm_sep_max_deg','D'),('nn_rm_sep_min_deg','D')]
def size(fmt):
    return int(fmt[:-1])*1 if fmt.endswith('A') else {'D':8,'K':8,'L':1,'E':4,'J':4}[fmt[0]]
off = {}
o = 0
for nm, fmt in forms:
    off[nm] = (o, fmt); o += size(fmt)
assert o == NAXIS1, f"row size mismatch {o} != {NAXIS1}"

WANT_F8 = ['ra','dec','l','b','rm','rm_err','polint','fracpol','snr_polint','stokesI','spectral_index','derot_polangle']
WANT_U1 = ['channel_flag','complex_flag','local_rm_flag','is_blended_flag']

state_f = os.path.join(OUT, 'state.json')
state = json.load(open(state_f)) if os.path.exists(state_f) else {'row': 0, 'kept': 0}
CHUNK = 250000
t0 = time.time()
fh = open(SRC, 'rb')
outs = {k: open(os.path.join(OUT, k + '.f8.bin'), 'ab') for k in WANT_F8}
outs.update({k: open(os.path.join(OUT, k + '.u1.bin'), 'ab') for k in WANT_U1})
cat_out = open(os.path.join(OUT, 'cat_id.18s.bin'), 'ab')

while state['row'] < NROWS and time.time() - t0 < 32:
    nr = min(CHUNK, NROWS - state['row'])
    fh.seek(DATA_START + state['row']*NAXIS1)
    buf = fh.read(nr*NAXIS1)
    a = np.frombuffer(buf, dtype=np.uint8).reshape(nr, NAXIS1)
    def colf8(nm):
        o, fmt = off[nm]
        return a[:, o:o+8].copy().view('>f8')[:, 0]
    def colL(nm):
        o, fmt = off[nm]
        return a[:, o]
    snr = colf8('snr_polint')
    goodI = colL('goodI_flag') == ord('T')
    leak = colL('leakage_flag') == ord('T')
    keep = np.isfinite(snr) & (snr >= 6) & goodI & (~leak)
    idx = np.nonzero(keep)[0]
    if idx.size:
        for k in WANT_F8:
            outs[k].write(colf8(k)[idx].astype('<f8').tobytes())
        for k in WANT_U1:
            outs[k].write((colL(k) == ord('T')).astype(np.uint8)[idx].tobytes())
        o0, _ = off['cat_id']
        cat_out.write(a[idx][:, o0:o0+18].tobytes())
        state['kept'] += int(idx.size)
    state['row'] += nr
json.dump(state, open(state_f, 'w'))
print(f"progress: {state['row']:,}/{NROWS:,} rows scanned, kept {state['kept']:,}  ({100*state['row']/NROWS:.1f}%)")
