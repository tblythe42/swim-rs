"""CLI single-site flow integration tests for current command behavior."""

from __future__ import annotations

import types
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

import swimrs.cli as cli

pytestmark = pytest.mark.integration

FID = "S2"


def _fixture_config() -> str:
    return str(Path(__file__).resolve().parent.parent / "fixtures" / "S2" / "S2.toml")


def _parse_and_run(argv: list[str]) -> int:
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


def _make_shapefile(tmp_path: Path) -> str:
    shp_dir = tmp_path / "data" / "gis"
    shp_dir.mkdir(parents=True, exist_ok=True)
    shp_path = shp_dir / "fields.shp"
    gdf = gpd.GeoDataFrame(
        {"FID": [FID], "geometry": [Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])]},
        crs="EPSG:4326",
    )
    gdf.to_file(shp_path)
    return str(shp_path)


def _make_prep_dirs(tmp_path: Path) -> None:
    # NDVI directories used by cmd_prep existence checks
    (tmp_path / "data" / "landsat" / "extracts" / "ndvi" / "irr").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "landsat" / "extracts" / "ndvi" / "inv_irr").mkdir(
        parents=True, exist_ok=True
    )
    # ETF directories used by cmd_prep existence checks (target model in S2.toml is ssebop)
    (tmp_path / "data" / "landsat" / "extracts" / "ssebop_etf" / "irr").mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / "data" / "landsat" / "extracts" / "ssebop_etf" / "inv_irr").mkdir(
        parents=True, exist_ok=True
    )
    (tmp_path / "data" / "met").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "snodas" / "extracts").mkdir(parents=True, exist_ok=True)


def test_cli_extract_single_site_smoke(tmp_path, monkeypatch):
    cfg = _fixture_config()
    calls = {
        "ndvi": 0,
        "gridmet_ids": 0,
        "gridmet_dl": 0,
    }

    monkeypatch.setattr(cli, "is_authorized", lambda: True)
    monkeypatch.setattr(
        cli, "sparse_sample_ndvi", lambda *a, **k: calls.__setitem__("ndvi", calls["ndvi"] + 1)
    )
    monkeypatch.setattr(
        cli,
        "assign_gridmet_ids",
        lambda *a, **k: calls.__setitem__("gridmet_ids", calls["gridmet_ids"] + 1),
    )
    monkeypatch.setattr(
        cli,
        "download_gridmet",
        lambda *a, **k: calls.__setitem__("gridmet_dl", calls["gridmet_dl"] + 1),
    )

    rc = _parse_and_run(
        [
            "extract",
            cfg,
            "--out-dir",
            str(tmp_path),
            "--sites",
            FID,
            "--export",
            "drive",
            "--no-snodas",
            "--no-properties",
        ]
    )

    assert rc == 0
    assert calls["ndvi"] >= 2  # irr + inv_irr masks
    assert calls["gridmet_ids"] == 1
    assert calls["gridmet_dl"] == 1


def test_cli_extract_fails_loudly_on_stage_error(tmp_path, monkeypatch):
    cfg = _fixture_config()

    monkeypatch.setattr(cli, "is_authorized", lambda: True)
    monkeypatch.setattr(cli, "assign_gridmet_ids", lambda *a, **k: None)
    monkeypatch.setattr(
        cli, "download_gridmet", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    rc = _parse_and_run(
        [
            "extract",
            cfg,
            "--out-dir",
            str(tmp_path),
            "--sites",
            FID,
            "--no-snodas",
            "--no-properties",
            "--no-rs",
        ]
    )

    assert rc == 1


def test_cli_prep_single_site_smoke(tmp_path, monkeypatch):
    cfg = _fixture_config()
    _make_prep_dirs(tmp_path)
    shp_path = _make_shapefile(tmp_path)

    calls = {
        "properties": 0,
        "ndvi": 0,
        "etf": 0,
        "gridmet": 0,
        "snodas": 0,
        "merged_ndvi": 0,
        "dynamics": 0,
    }

    class _FakeIngest:
        def properties(self, **kwargs):
            calls["properties"] += 1

        def ndvi(self, *args, **kwargs):
            calls["ndvi"] += 1

        def etf(self, *args, **kwargs):
            calls["etf"] += 1

        def gridmet(self, *args, **kwargs):
            calls["gridmet"] += 1

        def era5(self, *args, **kwargs):
            raise AssertionError("ERA5 should not be called in this fixture")

        def snodas(self, *args, **kwargs):
            calls["snodas"] += 1

    class _FakeCompute:
        def merged_ndvi(self, **kwargs):
            calls["merged_ndvi"] += 1

        def dynamics(self, **kwargs):
            calls["dynamics"] += 1

    class _FakeContainer:
        def __init__(self):
            self.ingest = _FakeIngest()
            self.compute = _FakeCompute()

        def close(self):
            return None

    monkeypatch.setattr(cli, "_ensure_shapefile", lambda *a, **k: shp_path)
    monkeypatch.setattr(cli.SwimContainer, "create", staticmethod(lambda *a, **k: _FakeContainer()))
    monkeypatch.setattr(cli.SwimContainer, "open", staticmethod(lambda *a, **k: _FakeContainer()))

    rc = _parse_and_run(["prep", cfg, "--out-dir", str(tmp_path), "--sites", FID])

    assert rc == 0
    assert calls["properties"] == 1
    assert calls["ndvi"] >= 2
    assert calls["etf"] >= 2
    assert calls["gridmet"] == 1
    assert calls["snodas"] == 1
    assert calls["merged_ndvi"] == 1
    assert calls["dynamics"] == 1


def test_cli_prep_fails_loudly_on_stage_error(tmp_path, monkeypatch):
    cfg = _fixture_config()
    _make_prep_dirs(tmp_path)
    shp_path = _make_shapefile(tmp_path)

    class _FakeIngest:
        def properties(self, **kwargs):
            return None

        def ndvi(self, *args, **kwargs):
            return None

        def etf(self, *args, **kwargs):
            return None

        def gridmet(self, *args, **kwargs):
            return None

        def snodas(self, *args, **kwargs):
            return None

    class _FakeCompute:
        def merged_ndvi(self, **kwargs):
            return None

        def dynamics(self, **kwargs):
            raise RuntimeError("dynamics failure")

    class _FakeContainer:
        def __init__(self):
            self.ingest = _FakeIngest()
            self.compute = _FakeCompute()

        def close(self):
            return None

    monkeypatch.setattr(cli, "_ensure_shapefile", lambda *a, **k: shp_path)
    monkeypatch.setattr(cli.SwimContainer, "create", staticmethod(lambda *a, **k: _FakeContainer()))
    monkeypatch.setattr(cli.SwimContainer, "open", staticmethod(lambda *a, **k: _FakeContainer()))

    rc = _parse_and_run(["prep", cfg, "--out-dir", str(tmp_path), "--sites", FID])
    assert rc == 1


def test_cli_run_persists_to_container(tmp_path, monkeypatch):
    cfg = _fixture_config()
    container_path = tmp_path / "existing.swim"
    container_path.write_text("placeholder")

    calls = {"run": [], "save": 0, "close": 0}

    class _FakeRuns:
        @staticmethod
        def metadata(run_id):
            return {"run_id": run_id, "profile": "state_only", "n_days": 3, "field_count": 1}

    class _FakeContainer:
        runs = _FakeRuns()

        def run(self, **kwargs):
            calls["run"].append(kwargs)
            return types.SimpleNamespace(run_id=kwargs.get("run_id") or "auto_run")

        def save(self):
            calls["save"] += 1

        def close(self):
            calls["close"] += 1

    fake_container = _FakeContainer()
    monkeypatch.setattr(cli.SwimContainer, "open", staticmethod(lambda *a, **k: fake_container))

    rc = _parse_and_run(
        [
            "run",
            cfg,
            "--out-dir",
            str(tmp_path),
            "--container",
            str(container_path),
            "--run-id",
            "demo_run",
            "--profile",
            "state_only",
            "--restart-from",
            "previous_run",
            "--start-date",
            "2020-01-01",
            "--end-date",
            "2020-01-03",
            "--sites",
            FID,
        ]
    )

    assert rc == 0
    assert calls["save"] == 1
    assert calls["close"] == 1
    assert len(calls["run"]) == 1

    kwargs = calls["run"][0]
    assert kwargs["run_id"] == "demo_run"
    assert kwargs["profile"] == "state_only"
    assert kwargs["restart_from"] == "previous_run"
    assert kwargs["start_date"] == "2020-01-01"
    assert kwargs["end_date"] == "2020-01-03"
    assert kwargs["fields"] == [FID]
    assert kwargs["ndvi_mode"] == "observed"
