"""Build publication-track shapefiles for Example 6.

Provenance chain:
    flux_crop_ag_96_150m.shp  (96 cropland flux sites, enriched with flux/LULC metadata)
    └── flux_crop_pub_75_150m.shp  (75-site POR publication cohort)

The 75-site cohort excludes 21 sites that lack post-2013 flux tower data,
which is the minimum required for the OLI-era LS Ensemble and Triple ETf
POR calibration experiments (2013-01-01 to 2025-12-31).

Both publication TOMLs reference this shapefile:
    - 6_Flux_International_LSEnsemble_POR.toml
    - 6_Flux_International_TripleETf_POR.toml

Usage:
    python shapefile.py [--gis-dir PATH]
"""

import argparse
from pathlib import Path

import geopandas as gpd

# 21 sites excluded from the 96-site cropland cohort because they lack
# any post-2013 flux tower data (required by the POR calibration window).
EXCLUDED_NO_POST2013_FLUX = {
    "CA-MA1",
    "CA-MA2",
    "CA-MA3",
    "CH-Oe1",
    "CN-Cng",
    "DE-Seh",
    "FI-Jok",
    "IT-PT1",
    "US-ARM",
    "US-Bo1",
    "US-Bo2",
    "US-Br1",
    "US-Br3",
    "US-Dia",
    "US-Dk1",
    "US-KS2",
    "US-Lin",
    "US-Pon",
    "US-SFP",
    "US-SP2",
    "US-Wi6",
}


def build_pub75(gis_dir: Path) -> Path:
    """Filter crop96 to the 75-site POR publication cohort."""
    crop96_path = gis_dir / "flux_crop_ag_96_150m.shp"
    out_path = gis_dir / "flux_crop_pub_75_150m.shp"

    gdf = gpd.read_file(crop96_path, engine="fiona")
    assert "sid" in gdf.columns, f"Expected 'sid' column, got {list(gdf.columns)}"

    pub = gdf[~gdf["sid"].isin(EXCLUDED_NO_POST2013_FLUX)].copy()

    dropped = set(gdf["sid"]) - set(pub["sid"])
    assert dropped == EXCLUDED_NO_POST2013_FLUX, (
        f"Exclusion mismatch: expected {len(EXCLUDED_NO_POST2013_FLUX)} dropped, got {len(dropped)}"
    )
    assert len(pub) == 75, f"Expected 75 sites, got {len(pub)}"

    pub.to_file(out_path, engine="fiona")
    print(f"Wrote {len(pub)} sites to {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Example 6 publication shapefiles")
    default_gis = str(Path(__file__).resolve().parent / "data" / "gis")
    parser.add_argument(
        "--gis-dir",
        type=str,
        default=default_gis,
        help="GIS directory containing flux_crop_ag_96_150m.shp (default: in-repo data/gis/)",
    )
    args = parser.parse_args()
    build_pub75(Path(args.gis_dir))
