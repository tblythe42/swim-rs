# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pandas",
#   "pyarrow",
#   "geopandas",
#   "pyproj",
#   "shapely",
#   "fiona",
# ]
# ///
"""Build ESPA cohort manifest for all site-years in the ECOSTRESS era.

Orchestrates the existing scene-list and extent builders to produce:
  - a manifest CSV with one row per site-year
  - per-site-year scene CSVs (Landsat L2 product IDs)
  - per-site-year extent CSVs (UTM chip coordinates)

Example:
    uv run examples/6_Flux_International/espa/build_espa_manifest.py \
        --output-dir /data/ssd1/swim/6_Flux_International/data/remote_sensing/espa \
        --start-date 2018-01-01 --end-date 2025-12-31
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pandas as pd

_EX6_DIR = Path(__file__).resolve().parent.parent


def _import_from_file(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_order_mod = _import_from_file("build_espa_order_csv", _EX6_DIR / "build_espa_order_csv.py")
_extent_mod = _import_from_file("build_espa_extent", _EX6_DIR / "build_espa_extent.py")

build_espa_order = _order_mod.build_espa_order
DEFAULT_METADATA = _order_mod.DEFAULT_METADATA
DEFAULT_NDVI_DIR = _order_mod.DEFAULT_NDVI_DIR
DEFAULT_PTJPL_DIR = _order_mod.DEFAULT_PTJPL_DIR
build_espa_extent = _extent_mod.build_espa_extent

DEFAULT_SHP = Path("/data/ssd1/swim/6_Flux_International/data/gis/flux_intl_150m_23MAR2026.shp")

MANIFEST_COLUMNS = [
    "site",
    "year",
    "start_date",
    "end_date",
    "chip_size_m",
    "n_scenes",
    "scene_csv",
    "extent_csv",
    "payload_json",
    "order_id",
    "order_status",
    "download_status",
    "extract_status",
    "output_dir",
    "notes",
]


def _get_sites(shapefile: Path) -> list[str]:
    import geopandas as gpd

    gdf = gpd.read_file(shapefile, engine="fiona")
    return sorted(gdf["sid"].unique().tolist())


def _count_scenes(scene_csv: Path) -> int:
    if not scene_csv.exists():
        return 0
    df = pd.read_csv(scene_csv)
    return len(df)


def build_manifest(
    output_dir: Path,
    shapefile: Path = DEFAULT_SHP,
    metadata_path: Path = DEFAULT_METADATA,
    start_year: int = 2018,
    end_year: int = 2025,
    chip_size_m: float = 4000.0,
    overwrite: bool = False,
    sites: list[str] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "espa_manifest.csv"
    scenes_dir = output_dir / "scene_lists"
    extents_dir = output_dir / "extents"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    extents_dir.mkdir(parents=True, exist_ok=True)

    existing = None
    if manifest_path.exists() and not overwrite:
        existing = pd.read_csv(manifest_path, dtype=str)
        existing_keys = set(zip(existing["site"], existing["year"].astype(str)))
    else:
        existing_keys = set()

    all_sites = sites or _get_sites(shapefile)
    source_dirs = [DEFAULT_NDVI_DIR, DEFAULT_PTJPL_DIR]

    rows: list[dict] = []
    for site in all_sites:
        for year in range(start_year, end_year + 1):
            key = (site, str(year))
            if key in existing_keys:
                row = existing[(existing["site"] == site) & (existing["year"] == str(year))].iloc[0]
                rows.append(row.to_dict())
                continue

            start_date = f"{year}-01-01"
            end_date = f"{year}-12-31"
            scene_csv = scenes_dir / f"{site}_{year}_scenes.csv"
            extent_csv = extents_dir / f"{site}_extent.csv"

            # Build scene list
            n_scenes = 0
            try:
                build_espa_order(
                    sites=[site],
                    metadata_path=metadata_path,
                    output_csv=scene_csv,
                    source_dirs=source_dirs,
                    start_date=start_date,
                    end_date=end_date,
                )
                n_scenes = _count_scenes(scene_csv)
            except (ValueError, FileNotFoundError) as e:
                print(f"  SKIP {site}/{year}: {e}")

            # Build extent (once per site, reuse if exists)
            if not extent_csv.exists():
                try:
                    build_espa_extent(
                        site=site,
                        output_csv=extent_csv,
                        shapefile=shapefile,
                        chip_size_m=chip_size_m,
                    )
                except (ValueError, FileNotFoundError) as e:
                    print(f"  SKIP extent {site}: {e}")

            row_dict = {
                "site": site,
                "year": str(year),
                "start_date": start_date,
                "end_date": end_date,
                "chip_size_m": str(chip_size_m),
                "n_scenes": str(n_scenes),
                "scene_csv": str(scene_csv) if scene_csv.exists() else "",
                "extent_csv": str(extent_csv) if extent_csv.exists() else "",
                "payload_json": "",
                "order_id": "",
                "order_status": "",
                "download_status": "",
                "extract_status": "",
                "output_dir": str(output_dir / "orders" / site / str(year)),
                "notes": "" if n_scenes > 0 else "no_scenes",
            }
            rows.append(row_dict)
            print(f"  {site}/{year}: {n_scenes} scenes")

    manifest = pd.DataFrame(rows, columns=MANIFEST_COLUMNS)
    # Drop rows with zero scenes
    manifest = manifest[manifest["n_scenes"].astype(int) > 0].reset_index(drop=True)
    manifest.to_csv(manifest_path, index=False)
    print(f"\nManifest: {manifest_path}")
    print(f"Total site-years: {len(manifest)}")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ESPA cohort manifest")
    parser.add_argument("--output-dir", required=True, help="Root output directory for ESPA data")
    parser.add_argument("--shapefile", default=str(DEFAULT_SHP), help="Example 6 shapefile")
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA), help="USGS metadata parquet")
    parser.add_argument("--start-date", default="2018-01-01", help="Start of ECOSTRESS era")
    parser.add_argument("--end-date", default="2025-12-31", help="End date")
    parser.add_argument("--chip-size-m", type=float, default=4000.0, help="Chip size in meters")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing manifest rows")
    parser.add_argument(
        "--site", action="append", default=None, help="Restrict to specific site(s)"
    )
    args = parser.parse_args()

    start_year = int(args.start_date.split("-")[0])
    end_year = int(args.end_date.split("-")[0])

    build_manifest(
        output_dir=Path(args.output_dir),
        shapefile=Path(args.shapefile),
        metadata_path=Path(args.metadata),
        start_year=start_year,
        end_year=end_year,
        chip_size_m=args.chip_size_m,
        overwrite=args.overwrite,
        sites=sorted(set(args.site)) if args.site else None,
    )


if __name__ == "__main__":
    main()
