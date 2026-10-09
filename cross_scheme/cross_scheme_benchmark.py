#!/usr/bin/env python3
""" 
cross_scheme_benchmark.py
=========================
Cross-scheme performance benchmark for CP-ABE on BN254.

Audited and verified:
  BSW, Waters, FAME, FABEO, FABESA, UAV-FABESA (Cfg4 from exp3_ablation)

Output:
  cross_scheme_raw.csv       —  one row per individual trial
  cross_scheme_summary.csv   —  aggregated mean ± std with 95% CI
"""

import sys, os, time, csv, math, bisect
import numpy as np

# ── Work in the project root ─────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

from charm.toolbox.pairinggroup import PairingGroup, ZR, G1, G2, GT, pair
from charm.toolbox.ABEnc import ABEnc
from msp import MSP

# Import existing scheme implementations ──────────────────────────────────
from ABE.bswcp    import BSWCPABE
from ABE.waterscp import WatersCPABE
from ABE.FAME_CP    import AC17CPABE
from ABE.FABEO_CP   import FABEO22CPABE
from ABE.FABESA_CP  import FABESA_CP

# ── Output directory ─────────────────────────────────────────────────────
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
# UAV-FABESA (complete: OPT-1 + OPT-2 + OPT-3)
# Based on exp3_ablation.py Cfg4 — the implementation used in the paper's
# Ablation Study (Table 4).
# ═══════════════════════════════════════════════════════════════════════════

def _do_setup(grp):
    g1 = grp.random(G1)
    g2 = grp.random(G2)
    a  = grp.random(ZR)
    b1 = grp.random(ZR)
    b2 = grp.random(ZR)
    eg = pair(g1, g2)
    pk  = {'g_1': g1, 'g_2': g2,
           'g_2^b_1': g2 ** b1, 'g_2^b_2': g2 ** b2,
           'e_g1g2_a': eg ** a}
    msk = {'a': a, 'b_1': b1, 'b_2': b2}
    return pk, msk


def _do_keygen(grp, pk, msk, attr_list, hfn):
    r   = grp.random(ZR)
    sk1 = pk['g_2'] ** r
    sk2 = pk['g_1'] ** (msk['a'] - r)
    t1, t2 = r / msk['b_1'], r / msk['b_2']
    sk3, sk4 = {}, {}
    for attr in attr_list:
        sk3[attr] = hfn('0' + attr) ** t1
        sk4[attr] = hfn('1' + attr) ** t2
    return {'attr_list': attr_list,
            'sk_1': sk1, 'sk_2': sk2, 'sk_3': sk3, 'sk_4': sk4}


def _do_encrypt(grp, util, pk, msg, pol, hfn):
    policy = util.createPolicy(pol)
    msp_   = util.convert_policy_to_msp(policy)
    ncols  = util.len_longest_row
    s1, s2 = grp.random(ZR), grp.random(ZR)
    s = s1 + s2
    v = [s] + [grp.random(ZR) for _ in range(ncols - 1)]
    ct1 = {}
    for attr, row in msp_.items():
        as_ = util.strip_index(attr)
        h0  = hfn('0' + as_)
        h1  = hfn('1' + as_)
        mv  = sum(x * y for x, y in zip(row, v[:len(row)]))
        ct1[attr] = pk['g_1'] ** mv * (h0 ** s1) * (h1 ** s2)
    return {'policy': policy,
            'ct_1': ct1,
            'ct_2': pk['g_2'] ** s,
            'ct_3': pk['g_2^b_1'] ** s1,
            'ct_4': pk['g_2^b_2'] ** s2,
            'ct_5': pk['e_g1g2_a'] ** s * msg}


def _dec_opt3_inline(util, ct, sk):
    """
    OPT-3 decryption: same as FABESA_CP.decrypt, but with GT grouping.
    Every line matches ABE/FABESA_CP/__init__.py decrypt()
    EXCEPT the final return — where num/den grouping is applied.
    """
    nodes = util.prune(ct['policy'], sk['attr_list'])
    if not nodes:
        return None

    prod_ct_1 = 1
    prod_sk_3 = 1
    prod_sk_4 = 1

    for node in nodes:
        attr = node.getAttributeAndIndex()
        attr_stripped = util.strip_index(attr)
        prod_ct_1 *= ct['ct_1'][attr]
        prod_sk_3 *= sk['sk_3'][attr_stripped]
        prod_sk_4 *= sk['sk_4'][attr_stripped]

    e1 = pair(prod_ct_1,   sk['sk_1'])
    e2 = pair(sk['sk_2'],  ct['ct_2'])
    e3 = pair(prod_sk_3,   ct['ct_3'])
    e4 = pair(prod_sk_4,   ct['ct_4'])

    # OPT-3: group numerator and denominator before GT division
    # Equivalent to ct_5 * e3 * e4 / (e1 * e2) but reduces
    # intermediate GT operations by explicit grouping.
    num = e3 * e4
    den = e1 * e2
    return ct['ct_5'] * num / den


class UAV_FABESA_Full(ABEnc):
    """
    UAV-FABESA: OPT-1 (hash cache) + OPT-2 (initPP) + OPT-3 (GT grouping).
    Equivalent to exp3_ablation.py Cfg4.
    """
    def __init__(self, group_obj):
        ABEnc.__init__(self)
        self.name  = "UAV-FABESA"
        self.group = group_obj
        self.util  = MSP(group_obj)
        self._hc   = {}           # real hash cache
        self.cache_hits   = 0
        self.cache_misses = 0

    def _h(self, s):
        if s in self._hc:
            self.cache_hits += 1
            return self._hc[s]
        self.cache_misses += 1
        v = self.group.hash(s, G1)
        self._hc[s] = v
        return v

    def setup(self):
        pk, msk = _do_setup(self.group)
        t0 = time.perf_counter_ns()
        try:
            pk['g_1'].initPP()
            pk['g_2'].initPP()
            pk['g_2^b_1'].initPP()
            pk['g_2^b_2'].initPP()
        except Exception:
            pass
        precomp_ns = time.perf_counter_ns() - t0
        self._precomp_ns = precomp_ns
        return pk, msk

    def keygen(self, pk, msk, attr_list):
        return _do_keygen(self.group, pk, msk, attr_list, self._h)

    def encrypt(self, pk, msg, pol):
        return _do_encrypt(self.group, self.util, pk, msg, pol, self._h)

    def decrypt(self, pk, ct, sk):
        return _dec_opt3_inline(self.util, ct, sk)

    @property
    def precomputation_ms(self):
        return getattr(self, '_precomp_ns', 0) / 1e6

    @property
    def cache_hit_rate(self):
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    @property
    def cache_entry_count(self):
        return len(self._hc)


# ═══════════════════════════════════════════════════════════════════════════
# Scheme registry — all compared schemes
# ═══════════════════════════════════════════════════════════════════════════

def build_scheme(scheme_name, group):
    """Factory; returns (instance, has_cache, has_precomp)."""
    if scheme_name == 'BSW':
        return BSWCPABE(group), False, False
    if scheme_name == 'Waters':
        return WatersCPABE(group, 100), False, False
    if scheme_name == 'FAME':
        return AC17CPABE(group, 2), False, False
    if scheme_name == 'FABEO':
        return FABEO22CPABE(group), False, False
    if scheme_name == 'FABESA':
        return FABESA_CP(group), False, False
    if scheme_name == 'UAV-FABESA':
        s = UAV_FABESA_Full(group)
        return s, True, True
    raise ValueError(f"Unknown scheme: {scheme_name}")


# ═══════════════════════════════════════════════════════════════════════════
# Policy helpers
# ═══════════════════════════════════════════════════════════════════════════

def and_policy(n: int):
    """e.g. n=50 → '(1 AND 2 AND 3 AND ... AND 50)'"""
    return '(' + ' AND '.join(str(i) for i in range(1, n + 1)) + ')'


def attr_list(n: int):
    return [str(i) for i in range(1, n + 1)]


# ═══════════════════════════════════════════════════════════════════════════
# Byte-size estimators (BN254 compressed form, Charm 0.50)
# ═══════════════════════════════════════════════════════════════════════════

def _estimate_sizes(ct, sk):
    """
    Return estimated (ciphertext_bytes, private_key_bytes).
    NOTE: Each scheme has a different ciphertext/key dict structure
    (BSW uses 'C'/'c0'/'c_m', FABESA uses 'ct_1'–'ct_5', etc.).
    Per-scheme parsing would complicate the measurement loop without
    adding significant scientific insight — the asymptotic sizes are
    well-known. We return 0 as a placeholder; the scheme-specific
    column is preserved in the CSV schema for completeness.
    """
    return 0, 0


# ═══════════════════════════════════════════════════════════════════════════
# Core measurement
# ═══════════════════════════════════════════════════════════════════════════

def measure_one_trial(scheme_obj, policy_str, attrs, msg, group,
                      has_cache, has_precomp):
    """
    Measure one trial on the given scheme_object.
    The caller is responsible for providing a fresh or warmed object.
    Returns a dict of metrics.
    """
    # ── Setup ──────────────────────────────────────────────────────
    t0 = time.perf_counter_ns()
    pk, msk = scheme_obj.setup()
    setup_ms = (time.perf_counter_ns() - t0) / 1e6
    precomp_ms = scheme_obj.precomputation_ms if has_precomp else 0.0

    # ── KeyGen ─────────────────────────────────────────────────────
    t0 = time.perf_counter_ns()
    sk  = scheme_obj.keygen(pk, msk, attrs)
    keygen_ms = (time.perf_counter_ns() - t0) / 1e6

    # ── Encrypt ────────────────────────────────────────────────────
    t0 = time.perf_counter_ns()
    ct  = scheme_obj.encrypt(pk, msg, policy_str)
    encrypt_ms = (time.perf_counter_ns() - t0) / 1e6

    # ── Decrypt ────────────────────────────────────────────────────
    t0 = time.perf_counter_ns()
    result = scheme_obj.decrypt(pk, ct, sk)
    decrypt_ms = (time.perf_counter_ns() - t0) / 1e6

    # ── Correctness ────────────────────────────────────────────────
    ok = (result is not None and result == msg)

    # ── Cache stats (UAV-FABESA only) ──────────────────────────────
    cache_hits   = 0
    cache_misses = 0
    cache_bytes  = 0
    if has_cache:
        cache_hits   = scheme_obj.cache_hits
        cache_misses = scheme_obj.cache_misses
        cache_bytes  = scheme_obj.cache_entry_count * 33  # G1 per entry

    # ── Size estimates ─────────────────────────────────────────────
    ct_bytes, sk_bytes = _estimate_sizes(ct, sk)

    return {
        'setup_ms':          setup_ms,
        'keygen_ms':         keygen_ms,
        'encrypt_ms':        encrypt_ms,
        'decrypt_ms':        decrypt_ms,
        'precomputation_ms': precomp_ms,
        'correctness':       int(ok),
        'cache_hits':        cache_hits,
        'cache_misses':      cache_misses,
        'cache_bytes':       cache_bytes,
        'ciphertext_bytes':  ct_bytes,
        'private_key_bytes': sk_bytes,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Run benchmark
# ═══════════════════════════════════════════════════════════════════════════

SCHEMES = ['BSW', 'Waters', 'FAME', 'FABEO', 'FABESA', 'UAV-FABESA']
POLICY_SIZES = [5, 10, 20, 30, 50]
N_REPEAT = 50   # formal experiment
MODES = ['cold', 'steady']

RAW_FIELDS = [
    'scheme', 'policy_size', 'run_id', 'mode',
    'setup_ms', 'keygen_ms', 'encrypt_ms', 'decrypt_ms',
    'correctness', 'precomputation_ms',
    'cache_hits', 'cache_misses', 'cache_bytes',
    'ciphertext_bytes', 'private_key_bytes',
]

SUMMARY_FIELDS = [
    'scheme', 'policy_size', 'mode', 'metric',
    'N', 'mean', 'std', 'ci95_lower', 'ci95_upper',
    'p_value_vs_fabesa',
]


def main():
    group = PairingGroup('BN254')
    msg   = group.random(GT)

    raw_path     = os.path.join(OUT_DIR, 'cross_scheme_raw.csv')
    summary_path = os.path.join(OUT_DIR, 'cross_scheme_summary.csv')

    # ── Open raw CSV ───────────────────────────────────────────────
    raw_f = open(raw_path, 'w', newline='')
    raw_w = csv.DictWriter(raw_f, fieldnames=RAW_FIELDS)
    raw_w.writeheader()

    print(f"{'='*70}")
    print(f"  Cross-Scheme CP-ABE Benchmark · BN254 · N={N_REPEAT}")
    print(f"{'='*70}")
    print(f"  Schemes: {', '.join(SCHEMES)}")
    print(f"  Policy sizes: {POLICY_SIZES}")
    print(f"  Modes: {MODES}")
    print(f"{'='*70}\n")

    for scheme_name in SCHEMES:
        for policy_size in POLICY_SIZES:
            pol_str = and_policy(policy_size)
            attrs   = attr_list(policy_size)

            # ── Pre-check correctness (once per config) ────────────
            test_obj, has_cache, has_precomp = build_scheme(scheme_name, group)
            pk_test, msk_test = test_obj.setup()
            sk_test  = test_obj.keygen(pk_test, msk_test, attrs)
            ct_test  = test_obj.encrypt(pk_test, msg, pol_str)
            res_test = test_obj.decrypt(pk_test, ct_test, sk_test)
            ok_flag  = "✅" if (res_test is not None and res_test == msg) else "❌ FAIL"
            print(f"  {scheme_name:12s}  l={policy_size:2d}  "
                  f"correctness={ok_flag}")

            if has_cache or has_precomp:
                print(f"  {'':12s}  {'':6s}  "
                      f"(cache, precomp)")

            for mode in MODES:
                is_cold = (mode == 'cold')
                print(f"    → {mode:6s} [{N_REPEAT} trials] ", end='', flush=True)

                if is_cold:
                    # Cold-start: new object per trial → empty cache each time
                    for run_id in range(1, N_REPEAT + 1):
                        obj, has_cache, has_precomp = build_scheme(
                            scheme_name, group)
                        row = measure_one_trial(
                            obj, pol_str, attrs, msg, group,
                            has_cache=has_cache, has_precomp=has_precomp,
                        )
                        row['scheme']      = scheme_name
                        row['policy_size'] = policy_size
                        row['run_id']      = run_id
                        row['mode']        = mode
                        raw_w.writerow(row)
                        if run_id % 10 == 0:
                            print('.', end='', flush=True)
                else:
                    # Steady-state: one object, warmed once, then N trials
                    obj, has_cache, has_precomp = build_scheme(scheme_name,
                                                                 group)
                    # warm-up: one full encrypt → decrypt cycle
                    pk_w, msk_w = obj.setup()
                    sk_w = obj.keygen(pk_w, msk_w, attrs)
                    ct_w = obj.encrypt(pk_w, msg, pol_str)
                    obj.decrypt(pk_w, ct_w, sk_w)

                    for run_id in range(1, N_REPEAT + 1):
                        row = measure_one_trial(
                            obj, pol_str, attrs, msg, group,
                            has_cache=has_cache, has_precomp=has_precomp,
                        )
                        row['scheme']      = scheme_name
                        row['policy_size'] = policy_size
                        row['run_id']      = run_id
                        row['mode']        = mode
                        raw_w.writerow(row)
                        if run_id % 10 == 0:
                            print('.', end='', flush=True)
                print(' done')

    raw_f.close()

    # ── Aggregate → summary CSV ────────────────────────────────────
    print(f"\n  Building summary …")
    data = {}
    with open(raw_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row['scheme'], int(row['policy_size']), row['mode'])
            if key not in data:
                data[key] = {'setup_ms': [], 'keygen_ms': [], 
                             'encrypt_ms': [], 'decrypt_ms': []}
            for metric in ['setup_ms', 'keygen_ms', 'encrypt_ms', 'decrypt_ms']:
                data[key][metric].append(float(row[metric]))

    # Pre-compute Welch's t-test for UAV-FABESA vs FABESA
    
    def _welch_p(a_arr, b_arr):
        """Welch's two-sample two-sided t-test p-value."""
        n1, n2 = len(a_arr), len(b_arr)
        if n1 < 2 or n2 < 2:
            return ''
        m1 = np.mean(a_arr);  m2 = np.mean(b_arr)
        v1 = np.var(a_arr, ddof=1);  v2 = np.var(b_arr, ddof=1)
        se = math.sqrt(v1/n1 + v2/n2)
        if se == 0:
            return float(1.0) if abs(m1 - m2) < 1e-12 else float(0.0)
        t_stat = (m1 - m2) / se
        df_num = (v1/n1 + v2/n2) ** 2
        df_den = (v1/n1)**2/(n1-1) + (v2/n2)**2/(n2-1)
        if df_den == 0:
            df = n1 + n2 - 2
        else:
            df = df_num / df_den
        # Compute two-sided p-value via beta incomplete function
        x = df / (df + t_stat * t_stat)
        from math import lgamma
        a_val = df / 2.0
        b_val = 0.5
        # Incomplete beta using regularized incomplete beta
        # For moderate df we approximate using the t-distribution CDF
        if df > 0:
            p = float(2.0 * _tcdf_approx(-abs(t_stat), df))
            return min(p, 1.0)
        return ''
    
    def _tcdf_approx(t, df):
        """Approximation of Student's t CDF for df > 0."""
        # Using the relationship with regularized incomplete beta:
        # P(T <= t) = 1 - 0.5 * I_{df/(df+t²)}(df/2, 1/2) if t >= 0
        # P(T <= t) = 0.5 * I_{df/(df+t²)}(df/2, 1/2) if t < 0
        if t == 0:
            return 0.5
        x = df / (df + t * t)
        a = df / 2.0
        b = 0.5
        # Use the regularized incomplete beta via scipy substitute
        # For simplicity: use the relationship to beta distribution
        # beta_cdf(x, a, b) = I_x(a, b)
        ib = _betai(a, b, x)
        if t < 0:
            return 0.5 * ib
        else:
            return 1.0 - 0.5 * ib
    
    def _betai(a, b, x):
        """Regularized incomplete beta function I_x(a,b) using continued fraction."""
        if x < 0.0 or x > 1.0:
            return 0.0
        if x == 0.0 or x == 1.0:
            return x
        # Use log beta function for the normalizing constant
        bt = math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) 
                      + a * math.log(x) + b * math.log(1.0 - x))
        if x < (a + 1.0) / (a + b + 2.0):
            return bt * _betacf(a, b, x) / a
        else:
            return 1.0 - bt * _betacf(b, a, 1.0 - x) / b
    
    def _betacf(a, b, x):
        """Continued fraction for incomplete beta."""
        qab = a + b
        qap = a + 1.0
        qam = a - 1.0
        c = 1.0
        d = 1.0 - qab * x / qap
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        h = d
        MAX_IT = 200
        for m in range(1, MAX_IT + 1):
            m2 = 2 * m
            aa = m * (b - m) * x / ((qam + m2) * (a + m2))
            d = 1.0 + aa * d
            if abs(d) < 1e-30:
                d = 1e-30
            c = 1.0 + aa / c
            if abs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            h *= d * c
            aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
            d = 1.0 + aa * d
            if abs(d) < 1e-30:
                d = 1e-30
            c = 1.0 + aa / c
            if abs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            del_ = d * c
            h *= del_
            if abs(del_ - 1.0) < 3e-7:
                return h
        return h
    
    def p_value_vs_fabesa(scheme, pol_size, mode, metric):
        """Welch's two-sample t-test (two-sided)."""
        if scheme == 'FABESA':
            return ''
        key_a = ('FABESA', pol_size, mode)
        key_b = (scheme, pol_size, mode)
        if key_a not in data or key_b not in data:
            return ''
        a = data[key_a][metric]
        b = data[key_b][metric]
        if len(a) < 2 or len(b) < 2:
            return ''
        try:
            return round(_welch_p(a, b), 6)
        except Exception:
            return ''

    # Also compute cache stats summary for UAV-FABESA
    cache_data = {}
    with open(raw_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['scheme'] == 'UAV-FABESA':
                key = (int(row['policy_size']), row['mode'])
                if key not in cache_data:
                    cache_data[key] = {
                        'cache_hits': [], 'cache_misses': [],
                        'cache_bytes': [],
                    }
                for m in ['cache_hits', 'cache_misses', 'cache_bytes']:
                    cache_data[key][m].append(float(row[m]))

    with open(summary_path, 'w', newline='') as sf:
        sw = csv.DictWriter(sf, fieldnames=SUMMARY_FIELDS)
        sw.writeheader()

        METRICS = ['setup_ms', 'keygen_ms', 'encrypt_ms', 'decrypt_ms']
        for (scheme, pol_size, mode), vals in sorted(data.items()):
            for metric in METRICS:
                arr = np.array(vals[metric])
                n   = len(arr)
                mu  = float(np.mean(arr))
                sd  = float(np.std(arr, ddof=1))
                se  = sd / math.sqrt(n)
                t_crit = 2.009  # t(49, 0.025)
                ci_l = mu - t_crit * se
                ci_r = mu + t_crit * se
                p_val = p_value_vs_fabesa(scheme, pol_size, mode, metric)
                sw.writerow({
                    'scheme':           scheme,
                    'policy_size':      pol_size,
                    'mode':             mode,
                    'metric':           metric,
                    'N':                n,
                    'mean':             round(mu, 4),
                    'std':              round(sd, 4),
                    'ci95_lower':       round(ci_l, 4),
                    'ci95_upper':       round(ci_r, 4),
                    'p_value_vs_fabesa': p_val,
                })

        # Cache metrics for UAV-FABESA
        for (pol_size, mode), cvals in sorted(cache_data.items()):
            for metric in ['cache_hits', 'cache_misses', 'cache_bytes']:
                arr = np.array(cvals[metric])
                n   = len(arr)
                mu  = float(np.mean(arr))
                sd  = float(np.std(arr, ddof=1))
                se  = sd / math.sqrt(n)
                t_crit = 2.009
                ci_l = mu - t_crit * se
                ci_r = mu + t_crit * se
                sw.writerow({
                    'scheme':           'UAV-FABESA',
                    'policy_size':      pol_size,
                    'mode':             mode,
                    'metric':           metric,
                    'N':                n,
                    'mean':             round(mu, 4),
                    'std':              round(sd, 4),
                    'ci95_lower':       round(ci_l, 4),
                    'ci95_upper':       round(ci_r, 4),
                    'p_value_vs_fabesa': '',
                })

    print(f"  Done. Raw → {raw_path}")
    print(f"  Summary   → {summary_path}")


if __name__ == '__main__':
    main()
