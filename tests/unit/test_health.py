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


class _FakeGroup:
    def __init__(self, mapping: dict):
        self._mapping = mapping

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
    irr_data = ['{"2020": 0, "2021": 0}'] * 5
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
