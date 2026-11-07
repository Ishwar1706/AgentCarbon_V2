"""Different sensor fleets per company (count, zones, planted faults)."""
from __future__ import annotations

from typing import Any

# zone -> (co2 gain, co2 offset, temp offset, humidity offset, noise ppm)
ZONES: dict[str, tuple[float, float, float, float, float]] = {
    "PAINT": (1.12, 18.0, 1.4, 4.0, 14.0),
    "BODY": (1.00, 0.0, 2.6, -6.0, 12.0),
    "PRESS": (0.95, -12.0, 1.9, -3.0, 10.0),
    "ASSEMBLY": (1.05, 8.0, 0.2, 1.0, 11.0),
    "UTILITIES": (0.90, -20.0, 3.1, -8.0, 9.0),
}
ZONE_LABEL = {
    "PAINT": "Paint Shop", "BODY": "Body Shop", "PRESS": "Press Shop",
    "ASSEMBLY": "Assembly Shop", "UTILITIES": "Utilities / Compressor House",
}


def _s(code: str, zone: str, n: int, label: str, *faults: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "zone": zone, "n": n, "label": label, "faults": list(faults)}


def _f(month: int, kind: str, day: float, hours: float, magnitude: float = 0.0) -> dict[str, Any]:
    return {"month": month, "kind": kind, "start_day": day, "hours": hours, "magnitude": magnitude}


# short code -> list of sensors.  Different sensor counts: 5, 4, 3, 6, 8.
FLEETS: dict[str, tuple[str, list[dict[str, Any]]]] = {
    "sim-northstar-mobility": ("NSM", [
        _s("PNT", "PAINT", 1, "Paint Shop - Booth A"),
        _s("BDY", "BODY", 1, "Body Shop - Weld Line"),
        _s("PRS", "PRESS", 1, "Press Shop - Floor", _f(3, "STUCK", 11, 36)),
        _s("ASM", "ASSEMBLY", 1, "Assembly Shop - Line 1"),
        _s("UTL", "UTILITIES", 1, "Utilities - Compressor Room"),
    ]),
    "sim-ironwood-automotive": ("IRW", [
        _s("PNT", "PAINT", 1, "Paint Shop - Booth A"),
        _s("BDY", "BODY", 1, "Body Shop - Weld Line", _f(4, "DRIFT", 3, 14 * 24, 260)),
        _s("PRS", "PRESS", 1, "Press Shop - Floor"),
        _s("ASM", "ASSEMBLY", 1, "Assembly Shop - Line 1", _f(2, "DROPOUT", 20, 30)),
    ]),
    "sim-crestline-motors": ("CRM", [
        _s("PNT", "PAINT", 1, "Paint Shop - Booth A", _f(4, "DRIFT", 0, 25 * 24, 350)),
        _s("ASM", "ASSEMBLY", 1, "Assembly Shop - Line 1"),
        _s("UTL", "UTILITIES", 1, "Utilities - Compressor Room"),
    ]),
    "sim-redwood-vehicle-systems": ("RDW", [
        _s("PNT", "PAINT", 1, "Paint Shop - Booth A"),
        _s("PNT", "PAINT", 2, "Paint Shop - Booth B", _f(3, "SPIKE", 8, 48, 2600)),
        _s("BDY", "BODY", 1, "Body Shop - Weld Line"),
        _s("PRS", "PRESS", 1, "Press Shop - Floor", _f(5, "DROPOUT", 4, 60)),
        _s("ASM", "ASSEMBLY", 1, "Assembly Shop - Line 1"),
        _s("UTL", "UTILITIES", 1, "Utilities - Compressor Room", _f(2, "STUCK", 14, 30)),
    ]),
    "sim-summit-auto-works": ("SMT", [
        _s("PNT", "PAINT", 1, "Paint Shop - Booth A"),
        _s("PNT", "PAINT", 2, "Paint Shop - Booth B"),
        _s("BDY", "BODY", 1, "Body Shop - Weld Line A"),
        _s("BDY", "BODY", 2, "Body Shop - Weld Line B", _f(4, "STUCK", 20, 24)),
        _s("PRS", "PRESS", 1, "Press Shop - Floor"),
        _s("ASM", "ASSEMBLY", 1, "Assembly Shop - Line 1"),
        _s("ASM", "ASSEMBLY", 2, "Assembly Shop - Line 2", _f(3, "DRIFT", 5, 18 * 24, 300)),
        _s("UTL", "UTILITIES", 1, "Utilities - Compressor Room", _f(1, "DROPOUT", 6, 40)),
    ]),
}


def sensor_profiles(company_id: str, legal_name: str) -> list[dict[str, Any]]:
    prefix, fleet = FLEETS[company_id]
    profiles = []
    for item in fleet:
        gain, offset, t_off, h_off, noise = ZONES[item["zone"]]
        profiles.append({
            "sensor_id": f"SCD40-{prefix}-{item['code']}-{item['n']:02d}",
            "zone": item["zone"],
            "location": f"{legal_name} - {item['label']}",
            "gain": gain, "offset": offset, "temp_offset": t_off,
            "hum_offset": h_off, "noise": noise, "faults": item["faults"],
        })
    return profiles
