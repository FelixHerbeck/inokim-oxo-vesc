#!/usr/bin/env python3
"""Fit the rear motor's two-node thermal model to measured winding temperatures.

Usage:
    python3 fit_thermal.py log_030_2026-11-07_09-12-00.csv log_031_....csv [...]

Give the logs of one day in order. The gap between logs is taken from the
timestamps in the file names, and the model keeps cooling through it.

Needs the Lisp script's log fields: iq, id, Speed VESC, Time, Temp Fet and
"Wind M1 meas" (rear winding temperature from the resistance measurements at
stops and from (therm-cooldown n period)). Each change of "Wind M1 meas" is
one measurement.

The front motor cannot be measured (select-motor is global in LispBM), so
its constants are scaled from the rear fit by --front-scale.

Prints setq lines to paste into the VESC Tool REPL, and the values to put in
the defs at the top of dash_esc_lights.lisp.
"""
import argparse
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

ALPHA = 0.00393
# name, start value, lower, upper
PARAMS = [
    ("cw", 900.0, 200.0, 5000.0),     # winding + stator, J/K
    ("cs", 1600.0, 300.0, 8000.0),    # shell + magnets, J/K
    ("rws", 0.25, 0.03, 2.0),         # winding -> shell, K/W
    ("g0", 1.0, 0.1, 10.0),           # shell -> air standing, W/K
    ("g1", 0.08, 0.0, 0.5),           # extra W/K per km/h
    ("iron", 25.0, 0.0, 200.0),       # W at 55 km/h
]
LISP = {"cw": "therm-cw1", "cs": "therm-cs1", "rws": "therm-rws1",
        "g0": "therm-g0-1", "g1": "therm-g1-1", "iron": "therm-iron1"}


def file_time(path):
    m = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", path)
    return datetime.strptime(m.group(1), "%Y-%m-%d_%H-%M-%S") if m else None


def load(path):
    d = pd.read_csv(path, sep=";")
    d.columns = [c.split(":")[0] for c in d.columns]
    d = d.dropna(subset=["t_day", "iq"]).reset_index(drop=True)
    return d


def build(paths):
    """One continuous series: dt, iq, id, km/h, and measurement points."""
    segs, meas = [], []
    t_off, prev_end, prev_ft = 0.0, None, None
    for p in paths:
        d = load(p)
        ft = file_time(p)
        t = d["t_day"].values - d["t_day"].values[0]
        if prev_end is not None:
            gap = (ft - prev_ft).total_seconds() - prev_end if ft and prev_ft else 60.0
            gap = max(gap, 0.0)
            n = int(gap // 1.0)
            if n:  # parked: zero current, zero speed, 1 s steps
                segs.append(pd.DataFrame({"dt": np.ones(n), "iq": 0.0, "id": 0.0,
                                          "kmh": 0.0, "t": t_off + np.arange(n)}))
                t_off += n
        dt = np.r_[0.1, np.diff(t)].clip(0, 1.0)
        segs.append(pd.DataFrame({"dt": dt, "iq": d["iq"].values,
                                  "id": d["id"].fillna(0).values,
                                  "kmh": d["kmh_vesc"].abs().fillna(0).values,
                                  "t": t_off + t}))
        if "Wind M1 meas" in d:
            w = d["Wind M1 meas"]
            ch = (w.diff().abs() > 1e-6) & (w > 0)
            for i in d.index[ch]:
                meas.append((len(pd.concat(segs)) - len(d) + i, float(w[i])))
        prev_end, prev_ft = t[-1], ft
        t_off += t[-1] + 0.1
    s = pd.concat(segs, ignore_index=True)
    fet = pd.concat([load(p)["Temp Fet"] for p in paths])
    return s, meas, float(fet[fet > -30].min())


def simulate(x, s, amb, r0, t0, t_init):
    cw, cs, rws, g0, g1, iron = x
    tw = ts = t_init
    out = np.empty(len(s))
    dt, iq, idd, v = s.dt.values, s.iq.values, s["id"].values, s.kmh.values
    for k in range(len(s)):
        r = r0 * (1 + ALPHA * (tw - t0))
        sp = v[k] / 55.0
        p = 1.5 * r * (iq[k] ** 2 + idd[k] ** 2) + iron * sp * np.sqrt(sp)
        q = (tw - ts) / rws
        tw += dt[k] * (p - q) / cw
        ts += dt[k] * (q - (ts - amb) * (g0 + g1 * v[k])) / cs
        out[k] = tw
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--r0", type=float, default=0.0564, help="rear R0 in Ohm (therm-cal)")
    ap.add_argument("--t0", type=float, default=25.0, help="temperature at R0")
    ap.add_argument("--amb", type=float, help="ambient degC (default: lowest FET)")
    ap.add_argument("--front-scale", type=float, default=0.67,
                    help="front heat capacities relative to rear (1500 W vs 2500 W hub)")
    a = ap.parse_args()

    s, meas, fet_min = build(a.logs)
    amb = a.amb if a.amb is not None else fet_min
    if len(meas) < 4:
        sys.exit(f"Only {len(meas)} measurements found; need at least 4, better 15+.")
    idx = np.array([m[0] for m in meas])
    y = np.array([m[1] for m in meas])
    # start temperature: first measurement if it comes early, else ambient
    t_init = y[0] if idx[0] < 600 else amb
    print(f"{len(s)/36000:.2f} h of data, {len(meas)} measurements, ambient {amb:.1f} degC")

    x0 = np.array([p[1] for p in PARAMS])
    lo = np.array([p[2] for p in PARAMS])
    hi = np.array([p[3] for p in PARAMS])

    # Priors: one ride cannot pin down six constants, so each is pulled gently
    # towards its physical estimate (a factor of ~2 counts as one degC of misfit
    # per measurement-weight). Constants the data does determine move freely.
    z0 = np.log(np.maximum(x0, 1e-3))
    w_prior = np.sqrt(len(y)) / np.log(2.0) * 0.5

    def resid_data(z):  # fit in log space, parameters span decades
        return simulate(np.exp(z), s, amb, a.r0, a.t0, t_init)[idx] - y

    def resid(z):
        return np.r_[resid_data(z), w_prior * (z - z0) / np.sqrt(len(y))]

    # iron loss may be 0: log space cannot reach 0, so floor it
    lo_l = np.log(np.maximum(lo, 1e-3))
    r = least_squares(resid, np.log(np.maximum(x0, 1e-3)), bounds=(lo_l, np.log(hi)),
                      diff_step=1e-3)
    x = np.exp(r.x)
    before = resid_data(z0)
    after = resid_data(r.x)
    print(f"RMS error: start constants {np.sqrt(np.mean(before**2)):.1f} K, "
          f"fitted {np.sqrt(np.mean(after**2)):.1f} K, worst {np.abs(after).max():.1f} K")

    # rough uncertainty from the data part of the Jacobian (prior excluded)
    try:
        J = r.jac[:len(y)]
        cov = np.linalg.pinv(J.T @ J) * max(np.mean(after ** 2), 1.0)
        rel = np.sqrt(np.diag(cov))  # in log space = relative
    except np.linalg.LinAlgError:
        rel = np.full(len(x), np.nan)

    print("\nRear (paste into the REPL):")
    for (name, *_), v, e in zip(PARAMS, x, rel):
        flag = "  (mostly the prior: the data says little about it)" if e > 0.5 else ""
        print(f"(setq {LISP[name]} {v:.4g})   ; +/-{e*100:.0f}%{flag}")
    fs = a.front_scale
    print("\nFront, scaled from the rear:")
    print(f"(setq therm-cw2 {x[0]*fs:.4g})\n(setq therm-cs2 {x[1]*fs:.4g})\n"
          f"(setq therm-rws2 {x[2]/fs:.4g})\n(setq therm-g0-2 {x[3]*fs:.4g})\n"
          f"(setq therm-g1-2 {x[4]*fs:.4g})\n(setq therm-iron2 {x[5]*fs:.4g})")

    # what matters: the climb you care about. 10 min at 60 A and 25 km/h from cold
    st = pd.DataFrame({"dt": np.full(6000, 0.1), "iq": 60.0, "id": 0.0, "kmh": 25.0})
    print(f"\nPrediction, 10 min at 60 A / 25 km/h from {amb:.0f} degC: "
          f"start constants {simulate(x0, st, amb, a.r0, a.t0, amb)[-1]:.0f} degC, "
          f"fitted {simulate(x, st, amb, a.r0, a.t0, amb)[-1]:.0f} degC")

    tw = simulate(x, s, amb, a.r0, a.t0, t_init)
    print(f"\nModelled rear winding peak over these logs: {tw.max():.0f} degC")
    rtot = x[2] + 1 / (x[3] + x[4] * 25)
    print(f"Steady state at 25 km/h: {rtot:.2f} K/W -> {100*rtot:.0f} K rise per 100 W loss")


if __name__ == "__main__":
    main()
