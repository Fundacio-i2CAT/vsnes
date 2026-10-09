#!/usr/bin/env python3
"""Generate a TLE file for N satellites in ONE orbital plane (a full ring by default,
or a tight arc with --spacing-deg so all of them stay in line of sight of each other).

Names are "<prefix><n>" (default SATELLITE-1..N) so they match the satellite
names in config.toml, which is how the emulator pairs a TLE with a node.
Defaults reproduce the walker66 orbit (86.4 deg, mean motion 14.35663288).

CLI:  python3 Class/tle_generator.py 5 test/configs/plane5.tle
"""
import argparse
import math
import os

MU_KM3_S2 = 398600.4418
R_EARTH_KM = 6378.137
DEFAULT_MEAN_MOTION = 14.35663288      # rev/day, as in walker66.tle
DEFAULT_EPOCH = "26191.00000000"       # YYDDD.DDDDDDDD (2026, day 191)


def mean_motion_from_altitude(altitude_km: float) -> float:
    a = R_EARTH_KM + altitude_km
    return 86400.0 / (2 * math.pi) * math.sqrt(MU_KM3_S2 / a ** 3)


def _checksum(line: str) -> int:
    return sum(int(c) if c.isdigit() else 1 if c == "-" else 0 for c in line[:68]) % 10


def generate_tle_text(num_sats: int, name_prefix: str = "SATELLITE-", first_index: int = 1,
                      inclination_deg: float = 86.4, raan_deg: float = 0.0,
                      eccentricity: float = 0.0001, arg_perigee_deg: float = 0.0,
                      mean_motion: float = DEFAULT_MEAN_MOTION, altitude_km: float = None,
                      phase_offset_deg: float = 0.0, epoch: str = DEFAULT_EPOCH,
                      spacing_deg: float = None) -> str:
    """altitude_km, if given, overrides mean_motion. spacing_deg: angle between
    consecutive satellites along the orbit; None spreads them evenly over 360."""
    if num_sats < 1:
        raise ValueError("num_sats must be >= 1")
    if first_index < 1 or first_index + num_sats - 1 > 99999:
        raise ValueError("catalog numbers must stay within 1..99999")
    if not 0 <= eccentricity < 1:
        raise ValueError("eccentricity must be in [0, 1)")
    if len(epoch) != 14:
        raise ValueError("epoch must be 14 chars, YYDDD.DDDDDDDD")
    if altitude_km is not None:
        mean_motion = mean_motion_from_altitude(altitude_km)

    out = []
    for i in range(num_sats):
        n = first_index + i
        step = 360.0 / num_sats if spacing_deg is None else spacing_deg
        anomaly = (phase_offset_deg + step * i) % 360.0
        l1 = f"1 {n:05d}U          {epoch}  .00000000  00000-0  00000+0 0    0"
        l2 = (f"2 {n:05d} {inclination_deg:8.4f} {raan_deg % 360:8.4f} "
              f"{int(round(eccentricity * 1e7)):07d} {arg_perigee_deg:8.4f} {anomaly:8.4f} "
              f"{mean_motion:11.8f}{0:5d}")
        out += [f"{name_prefix}{n}", l1 + str(_checksum(l1)), l2 + str(_checksum(l2))]
    return "\n".join(out) + "\n"


def write_tle(path: str, overwrite: bool = False, **kwargs) -> str:
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(f"{path} already exists")
    text = generate_tle_text(**kwargs)
    with open(path, "w") as f:
        f.write(text)
    return text


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("num_sats", type=int)
    ap.add_argument("output")
    ap.add_argument("--prefix", default="SATELLITE-", dest="name_prefix")
    ap.add_argument("--first-index", type=int, default=1)
    ap.add_argument("--inclination", type=float, default=86.4, dest="inclination_deg")
    ap.add_argument("--raan", type=float, default=0.0, dest="raan_deg")
    ap.add_argument("--altitude-km", type=float, default=None)
    ap.add_argument("--mean-motion", type=float, default=DEFAULT_MEAN_MOTION)
    ap.add_argument("--phase-offset", type=float, default=0.0, dest="phase_offset_deg")
    ap.add_argument("--spacing-deg", type=float, default=None,
                    help="angle between consecutive satellites (default: 360/N)")
    ap.add_argument("--epoch", default=DEFAULT_EPOCH)
    ap.add_argument("--overwrite", action="store_true")
    a = vars(ap.parse_args())
    out, overwrite = a.pop("output"), a.pop("overwrite")
    write_tle(out, overwrite=overwrite, **a)
    print(f"wrote {out}")
