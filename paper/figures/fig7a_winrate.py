"""
Figure 7a: Site-Level Win Rate Map

160 sites plotted geographically, marker color = SWIM wins (blue) or
SSEBop wins (orange) on monthly R², marker size = magnitude of R² delta.

Usage:
    python paper/figures/fig7a_winrate.py
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update(
    {
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "font.family": "sans-serif",
    }
)

MONTHLY_CSV = "/data/ssd1/swim/4_Flux_Network/results/evaluation_monthly_metrics.csv"
SHP = "/data/ssd1/swim/4_Flux_Network/data/gis/flux_fields.shp"

OUT_DIR = Path(__file__).resolve().parent
OUT_PNG = OUT_DIR / "fig7a_winrate.png"
OUT_PDF = OUT_DIR / "fig7a_winrate.pdf"

SWIM_COLOR = "#4C72B0"
SSEBOP_COLOR = "#DD8452"


def main():
    df = pd.read_csv(MONTHLY_CSV)
    shp = gpd.read_file(SHP, engine="fiona")
    lulc_map = dict(zip(shp["site_id"], shp["lc_class"]))

    # Merge lat/lon from shapefile centroids
    shp_latlon = shp.copy().to_crs(epsg=4326)
    shp_latlon["lon"] = shp_latlon.geometry.centroid.x
    shp_latlon["lat"] = shp_latlon.geometry.centroid.y
    coord_map = dict(zip(shp_latlon["site_id"], zip(shp_latlon["lon"], shp_latlon["lat"])))

    df["lulc"] = df["fid"].map(lulc_map)
    df["lon"] = df["fid"].map(lambda f: coord_map.get(f, (np.nan, np.nan))[0])
    df["lat"] = df["fid"].map(lambda f: coord_map.get(f, (np.nan, np.nan))[1])
    df["delta"] = df["r2_swim"] - df["r2_ssebop"]
    df["swim_wins"] = df["delta"] > 0
    df = df.dropna(subset=["lon", "lat", "delta"])

    # Background: US states
    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature

        fig = plt.figure(figsize=(12, 6))
        ax = fig.add_subplot(
            1, 1, 1, projection=ccrs.AlbersEqualArea(central_longitude=-96, central_latitude=37.5)
        )
        ax.set_extent([-125, -66, 24, 50], crs=ccrs.PlateCarree())
        ax.add_feature(cfeature.STATES, linewidth=0.3, edgecolor="gray")
        ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
        transform = ccrs.PlateCarree()
    except ImportError:
        fig, _ = plt.subplots(1, 1, figsize=(12, 6))
        ax = fig.axes[0]
        transform = None

    # Size by |delta|, color by winner
    sizes = np.clip(np.abs(df["delta"].values) * 150, 15, 200)
    colors = [SWIM_COLOR if w else SSEBOP_COLOR for w in df["swim_wins"]]

    if transform is not None:
        ax.scatter(
            df["lon"],
            df["lat"],
            s=sizes,
            c=colors,
            alpha=0.7,
            edgecolors="white",
            linewidths=0.3,
            transform=transform,
            zorder=5,
        )
    else:
        ax.scatter(
            df["lon"],
            df["lat"],
            s=sizes,
            c=colors,
            alpha=0.7,
            edgecolors="white",
            linewidths=0.3,
            zorder=5,
        )
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")

    # Legend
    wins = df["swim_wins"].sum()
    total = len(df)
    from matplotlib.lines import Line2D

    legend_elements = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=SWIM_COLOR,
            markersize=10,
            label=f"SWIM wins ({wins}/{total}, {100 * wins / total:.0f}%)",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=SSEBOP_COLOR,
            markersize=10,
            label=f"SSEBop wins ({total - wins}/{total}, {100 * (total - wins) / total:.0f}%)",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="gray",
            markersize=6,
            label="Small |R² delta|",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="gray",
            markersize=12,
            label="Large |R² delta|",
        ),
    ]
    ax.legend(handles=legend_elements, loc="lower left", framealpha=0.9, fontsize=9)

    ax.set_title(f"Monthly R²: SWIM vs SSEBop ({total} paired sites)", fontweight="bold")

    fig.savefig(OUT_PNG, bbox_inches="tight")
    fig.savefig(OUT_PDF, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {OUT_PNG}")
    print(f"Saved {OUT_PDF}")


if __name__ == "__main__":
    main()
