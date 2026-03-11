"""Tests for container health checking and reporting."""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from swimrs.container.health import (
    ContainerHealthCheck,
    ContainerHealthError,
    HealthPolicy,
    fingerprint_container,
    render_html_report,
)

# ---------------------------------------------------------------------------
# Fake zarr objects (same pattern as test_inventory.py)
# ---------------------------------------------------------------------------


class _FakeArray:
    def __init__(self, data, *, attrs=None):
        self._data = (
            np.asarray(data) if not isinstance(data, list) or not isinstance(data[0], str) else data
        )
        self.attrs = attrs or {}
        if isinstance(self._data, np.ndarray):
            self.shape = self._data.shape
            self.ndim = self._data.ndim
            self.dtype = self._data.dtype
        else:
            # String list
            self.shape = (len(data),)
            self.ndim = 1
            self.dtype = "object"

    def __getitem__(self, item):
        if isinstance(self._data, list):
            if item == slice(None):
                return self._data
            return self._data[item]
        return self._data[item]


class _FakeAttrs(dict):
    """Dict that also supports attribute-style access for fake zarr attrs."""

    pass


class _FakeGroup:
    def __init__(self, mapping: dict):
        self._mapping = mapping
        self.attrs = _FakeAttrs()

    def keys(self):
        # Return immediate child names
        seen = set()
        for k in self._mapping:
            parts = k.split("/")
            seen.add(parts[0])
        return list(seen)

    def __getitem__(self, key: str):
        if key in self._mapping:
            return self._mapping[key]
        # Check for sub-group
        prefix = f"{key}/"
        sub = {}
        for k, v in self._mapping.items():
            if k.startswith(prefix):
                sub[k[len(prefix) :]] = v
        if sub:
            return _FakeGroup(sub)
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        if key in self._mapping:
            return True
        prefix = f"{key}/"
        return any(k.startswith(prefix) for k in self._mapping)


class _FakeRoot(_FakeGroup):
    store = "test_container.swim"


def _make_healthy_root(n_fields=10):
    """Create a fake zarr root that passes all base health checks."""
    time_arr = np.array(["2020-01-01", "2020-01-02", "2020-01-03"], dtype="datetime64[D]")
    return _FakeRoot(
        {
            "time/daily": _FakeArray(time_arr),
            "geometry/uid": _FakeArray([f"{i}" for i in range(n_fields)]),
            "properties/soils/awc": _FakeArray(np.full(n_fields, 0.15)),
            "properties/soils/clay": _FakeArray(np.full(n_fields, 25.0)),
            "properties/soils/sand": _FakeArray(np.full(n_fields, 40.0)),
            "properties/soils/ksat": _FakeArray(np.full(n_fields, 10.0)),
            "properties/land_cover/modis_lc": _FakeArray(np.full(n_fields, 12, dtype="int16")),
            "properties/irrigation/irr": _FakeArray(np.full(n_fields, 0.5)),
            "properties/location/lat": _FakeArray(np.full(n_fields, 45.0)),
            "properties/location/lon": _FakeArray(np.full(n_fields, -107.0)),
            "properties/location/elevation": _FakeArray(np.full(n_fields, 1000.0)),
        }
    )


# ---------------------------------------------------------------------------
# HealthPolicy tests
# ---------------------------------------------------------------------------


def test_policy_base_rules_always_returned():
    rules = HealthPolicy.for_config({})
    # Should have at least 3 base rules
    assert len(rules) >= 3
    paths = [r.required_path for r in rules]
    assert "properties/soils/awc" in paths
    assert "properties/land_cover/modis_lc" in paths


def test_policy_mask_mode_irrigation_adds_irr_rules():
    rules = HealthPolicy.for_config({"mask_mode": "irrigation"})
    paths = [r.required_path for r in rules]
    assert "properties/irrigation/irr" in paths
    assert "properties/irrigation/irr_yearly" in paths


def test_policy_etf_target_model_adds_etf_rule():
    rules = HealthPolicy.for_config(
        {
            "etf_target_model": "ssebop",
            "mask_mode": "irrigation",
        }
    )
    paths = [r.required_path for r in rules]
    assert "remote_sensing/etf/landsat/ssebop/irr" in paths


def test_policy_ensemble_members_adds_member_rules():
    rules = HealthPolicy.for_config(
        {
            "etf_ensemble_members": ["ptjpl", "sims"],
            "mask_mode": "irrigation",
        }
    )
    paths = [r.required_path for r in rules]
    assert "remote_sensing/etf/landsat/ptjpl/irr" in paths
    assert "remote_sensing/etf/landsat/sims/irr" in paths


# ---------------------------------------------------------------------------
# ContainerHealthCheck tests
# ---------------------------------------------------------------------------


def test_all_nan_property_is_fail():
    root = _FakeRoot(
        {
            "time/daily": _FakeArray(np.array(["2020-01-01"], dtype="datetime64[D]")),
            "properties/soils/awc": _FakeArray(np.full(5, np.nan)),
        }
    )
    checker = ContainerHealthCheck(root, [str(i) for i in range(5)])
    report = checker.run()

    awc_checks = [
        c for c in report.checks if c.path == "properties/soils/awc" and c.section == "properties"
    ]
    assert len(awc_checks) == 1
    assert awc_checks[0].severity == "FAIL"


def test_valid_property_is_pass():
    root = _FakeRoot(
        {
            "time/daily": _FakeArray(np.array(["2020-01-01"], dtype="datetime64[D]")),
            "properties/soils/awc": _FakeArray(np.array([0.15, 0.2, 0.18])),
        }
    )
    checker = ContainerHealthCheck(root, ["0", "1", "2"])
    report = checker.run()

    awc_checks = [
        c for c in report.checks if c.path == "properties/soils/awc" and c.section == "properties"
    ]
    assert len(awc_checks) == 1
    assert awc_checks[0].severity == "PASS"


def test_partial_nan_property_is_warn():
    # 2/10 NaN = 20% > 10% threshold -> WARN
    data = np.array([0.15] * 8 + [np.nan, np.nan])
    root = _FakeRoot(
        {
            "time/daily": _FakeArray(np.array(["2020-01-01"], dtype="datetime64[D]")),
            "properties/soils/awc": _FakeArray(data),
        }
    )
    checker = ContainerHealthCheck(root, [str(i) for i in range(10)])
    report = checker.run()

    awc_checks = [
        c for c in report.checks if c.path == "properties/soils/awc" and c.section == "properties"
    ]
    assert len(awc_checks) == 1
    assert awc_checks[0].severity == "WARN"


def test_all_fill_lulc_is_fail():
    root = _FakeRoot(
        {
            "time/daily": _FakeArray(np.array(["2020-01-01"], dtype="datetime64[D]")),
            "properties/land_cover/modis_lc": _FakeArray(np.full(5, -1, dtype="int16")),
        }
    )
    checker = ContainerHealthCheck(root, [str(i) for i in range(5)])
    report = checker.run()

    lc_checks = [
        c
        for c in report.checks
        if c.path == "properties/land_cover/modis_lc" and c.section == "properties"
    ]
    assert len(lc_checks) == 1
    assert lc_checks[0].severity == "FAIL"


def test_policy_mask_mode_irrigation_without_irr_is_fail():
    root = _FakeRoot(
        {
            "time/daily": _FakeArray(np.array(["2020-01-01"], dtype="datetime64[D]")),
            "properties/soils/awc": _FakeArray(np.array([0.15])),
            "properties/land_cover/modis_lc": _FakeArray(np.array([12], dtype="int16")),
        }
    )
    config = {"mask_mode": "irrigation"}
    checker = ContainerHealthCheck(root, ["0"], config=config)
    report = checker.run()

    irr_policy = [c for c in report.checks if c.section == "policy" and "irrigation" in c.path]
    assert any(c.severity == "FAIL" for c in irr_policy)


def test_policy_etf_target_model_missing_is_fail():
    root = _FakeRoot(
        {
            "time/daily": _FakeArray(np.array(["2020-01-01"], dtype="datetime64[D]")),
            "properties/soils/awc": _FakeArray(np.array([0.15])),
            "properties/land_cover/modis_lc": _FakeArray(np.array([12], dtype="int16")),
        }
    )
    config = {"etf_target_model": "ssebop", "mask_mode": "irrigation"}
    checker = ContainerHealthCheck(root, ["0"], config=config)
    report = checker.run()

    etf_policy = [c for c in report.checks if "etf" in c.path and c.section == "policy"]
    assert any(c.severity == "FAIL" for c in etf_policy)


def test_zero_irrigated_fields_is_warn():
    irr_data = [
        '{"2020": {"irrigated": 0, "f_irr": 0.0}, "2021": {"irrigated": 0, "f_irr": 0.0}}'
    ] * 5
    root = _FakeRoot(
        {
            "time/daily": _FakeArray(np.array(["2020-01-01"], dtype="datetime64[D]")),
            "derived/dynamics/irr_data": _FakeArray(irr_data),
        }
    )
    checker = ContainerHealthCheck(root, [str(i) for i in range(5)])
    report = checker.run()

    irr_checks = [c for c in report.checks if "irr_data" in c.path]
    assert len(irr_checks) == 1
    assert irr_checks[0].severity == "WARN"


def test_irrigated_fields_detected_nested_format():
    """irr_data with nested dicts correctly counts irrigated fields."""
    irr_data = [
        '{"2020": {"irrigated": 1, "f_irr": 0.5}, "2021": {"irrigated": 0, "f_irr": 0.0}}',
        '{"2020": {"irrigated": 0, "f_irr": 0.0}, "2021": {"irrigated": 1, "f_irr": 0.3}}',
        '{"2020": {"irrigated": 0, "f_irr": 0.0}, "2021": {"irrigated": 0, "f_irr": 0.0}}',
    ]
    root = _FakeRoot(
        {
            "time/daily": _FakeArray(np.array(["2020-01-01"], dtype="datetime64[D]")),
            "derived/dynamics/irr_data": _FakeArray(irr_data),
        }
    )
    checker = ContainerHealthCheck(root, [str(i) for i in range(3)])
    report = checker.run()

    irr_checks = [c for c in report.checks if "irr_data" in c.path]
    assert len(irr_checks) == 1
    assert irr_checks[0].severity == "PASS"
    assert irr_checks[0].detail["n_irrigated"] == 2


def test_report_passed_property():
    root = _make_healthy_root(5)
    checker = ContainerHealthCheck(root, [str(i) for i in range(5)])
    report = checker.run()
    assert report.passed is True


def test_raise_on_fail():
    root = _FakeRoot(
        {
            "time/daily": _FakeArray(np.array(["2020-01-01"], dtype="datetime64[D]")),
            "properties/soils/awc": _FakeArray(np.full(5, np.nan)),
            "properties/land_cover/modis_lc": _FakeArray(np.full(5, -1, dtype="int16")),
        }
    )
    config = {"mask_mode": "irrigation"}
    checker = ContainerHealthCheck(root, [str(i) for i in range(5)], config=config)
    report = checker.run()
    assert not report.passed

    with pytest.raises(ContainerHealthError) as exc_info:
        raise ContainerHealthError(report)
    assert "FAIL" in str(exc_info.value)


def test_report_to_json_roundtrip():
    root = _make_healthy_root(5)
    checker = ContainerHealthCheck(root, [str(i) for i in range(5)])
    report = checker.run()

    data = report.to_json()
    assert isinstance(data, dict)
    assert "checks" in data
    assert "passed" in data
    assert data["passed"] is True

    # Roundtrip through JSON
    json_str = json.dumps(data)
    parsed = json.loads(json_str)
    assert parsed["n_fields"] == 5
    assert parsed["passed"] is True


def test_fingerprint_deterministic():
    root = _make_healthy_root(5)
    uids = [str(i) for i in range(5)]
    fp1 = fingerprint_container(root, uids)
    fp2 = fingerprint_container(root, uids)
    assert fp1 == fp2
    assert len(fp1) == 16


def test_html_report_renders():
    root = _make_healthy_root(5)
    checker = ContainerHealthCheck(root, [str(i) for i in range(5)])
    report = checker.run()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "health.html"
        result = render_html_report(report, out_path)
        assert result.exists()
        content = result.read_text()
        assert "Container Health Report" in content
        assert "PASS" in content


# ---------------------------------------------------------------------------
# Fix 1: Exception type matches public API
# ---------------------------------------------------------------------------


def test_exception_type_matches_public_api():
    """Inventory.report() raises the same ContainerHealthError exported from __init__."""
    from swimrs.container import ContainerHealthError as PublicCHE
    from swimrs.container.health import ContainerHealthError as HealthCHE

    # They must be the exact same class
    assert PublicCHE is HealthCHE


# ---------------------------------------------------------------------------
# Fix 3: Inventory.report() rejects non-dict config
# ---------------------------------------------------------------------------


def test_inventory_report_rejects_non_dict_config():
    """Passing a non-dict, non-None config to Inventory.report() raises TypeError."""
    from swimrs.container.inventory import Inventory

    root = _make_healthy_root(5)
    inv = Inventory(root, [str(i) for i in range(5)])

    # argparse.Namespace simulating a bad caller
    class FakeConfig:
        mask_mode = "irrigation"

    with pytest.raises(TypeError, match="config must be a dict or None"):
        inv.report(config=FakeConfig())


# ---------------------------------------------------------------------------
# Fix 4: field_coverage_union and field_coverage policy checks
# ---------------------------------------------------------------------------


def _make_irr_inv_irr_root(n_fields=5, irr_valid=None, inv_irr_valid=None):
    """Create a root with irr and inv_irr NDVI arrays.

    irr_valid/inv_irr_valid are boolean arrays indicating which fields have data.
    """
    n_time = 3
    time_arr = np.array(["2020-01-01", "2020-01-02", "2020-01-03"], dtype="datetime64[D]")

    irr_data = np.full((n_time, n_fields), np.nan)
    inv_irr_data = np.full((n_time, n_fields), np.nan)

    if irr_valid is not None:
        for i, v in enumerate(irr_valid):
            if v:
                irr_data[:, i] = 0.5

    if inv_irr_valid is not None:
        for i, v in enumerate(inv_irr_valid):
            if v:
                inv_irr_data[:, i] = 0.3

    return _FakeRoot(
        {
            "time/daily": _FakeArray(time_arr),
            "properties/soils/awc": _FakeArray(np.full(n_fields, 0.15)),
            "properties/land_cover/modis_lc": _FakeArray(np.full(n_fields, 12, dtype="int16")),
            "remote_sensing/ndvi/landsat/irr": _FakeArray(irr_data),
            "remote_sensing/ndvi/landsat/inv_irr": _FakeArray(inv_irr_data),
        }
    )


def test_field_coverage_union_pass():
    """All fields covered by irr union inv_irr -> PASS."""
    # Fields 0,1,2 have irr data; fields 3,4 have inv_irr data
    root = _make_irr_inv_irr_root(
        n_fields=5,
        irr_valid=[True, True, True, False, False],
        inv_irr_valid=[False, False, False, True, True],
    )
    config = {"mask_mode": "irrigation"}
    checker = ContainerHealthCheck(root, [str(i) for i in range(5)], config=config)
    report = checker.run()

    ndvi_coverage = [
        c
        for c in report.checks
        if c.section == "policy"
        and c.path == "remote_sensing/ndvi/landsat"
        and c.detail.get("check") == "field_coverage_union"
    ]
    assert len(ndvi_coverage) == 1
    assert ndvi_coverage[0].severity == "PASS"


def test_field_coverage_union_fail():
    """Field with zero obs in both irr and inv_irr -> FAIL."""
    # Field 4 has no data in either
    root = _make_irr_inv_irr_root(
        n_fields=5,
        irr_valid=[True, True, True, False, False],
        inv_irr_valid=[False, False, False, True, False],
    )
    config = {"mask_mode": "irrigation"}
    checker = ContainerHealthCheck(root, [str(i) for i in range(5)], config=config)
    report = checker.run()

    ndvi_coverage = [
        c
        for c in report.checks
        if c.section == "policy"
        and c.path == "remote_sensing/ndvi/landsat"
        and c.detail.get("check") == "field_coverage_union"
    ]
    assert len(ndvi_coverage) == 1
    assert ndvi_coverage[0].severity == "FAIL"
    assert "1/5" in ndvi_coverage[0].message


def test_field_coverage_no_mask_fail():
    """no_mask mode, field with zero obs -> FAIL."""
    n_fields = 5
    n_time = 3
    time_arr = np.array(["2020-01-01", "2020-01-02", "2020-01-03"], dtype="datetime64[D]")
    no_mask_data = np.full((n_time, n_fields), np.nan)
    # Fields 0-3 have data, field 4 does not
    for i in range(4):
        no_mask_data[:, i] = 0.5

    root = _FakeRoot(
        {
            "time/daily": _FakeArray(time_arr),
            "properties/soils/awc": _FakeArray(np.full(n_fields, 0.15)),
            "properties/land_cover/modis_lc": _FakeArray(np.full(n_fields, 12, dtype="int16")),
            "remote_sensing/ndvi/landsat/no_mask": _FakeArray(no_mask_data),
        }
    )

    config = {"mask_mode": "no_mask"}
    checker = ContainerHealthCheck(root, [str(i) for i in range(n_fields)], config=config)
    report = checker.run()

    ndvi_coverage = [
        c
        for c in report.checks
        if c.section == "policy"
        and c.path == "remote_sensing/ndvi/landsat/no_mask"
        and c.detail.get("check") == "field_coverage"
    ]
    assert len(ndvi_coverage) == 1
    assert ndvi_coverage[0].severity == "FAIL"
    assert "1/5" in ndvi_coverage[0].message


def test_report_stores_health_check_in_attrs():
    """Inventory.report() stores last_health_check in root attrs."""
    from swimrs.container.inventory import Inventory

    root = _make_healthy_root(5)
    inv = Inventory(root, [str(i) for i in range(5)])
    report = inv.report()

    stored = root.attrs.get("last_health_check")
    assert stored is not None
    assert stored["passed"] is True
    assert stored["fingerprint"] == report.container_fingerprint
    assert "timestamp" in stored


def test_irr_inv_irr_no_ts_warn_spam():
    """irr/inv_irr paired arrays should not produce time-series WARNs."""
    root = _make_irr_inv_irr_root(
        n_fields=5,
        irr_valid=[True, True, True, False, False],
        inv_irr_valid=[False, False, False, True, True],
    )
    config = {"mask_mode": "irrigation"}
    checker = ContainerHealthCheck(root, [str(i) for i in range(5)], config=config)
    report = checker.run()

    # No time_series checks should exist for the irr/inv_irr paths
    ts_irr_checks = [
        c
        for c in report.checks
        if c.section == "time_series" and ("irr" in c.path or "inv_irr" in c.path)
    ]
    assert len(ts_irr_checks) == 0
