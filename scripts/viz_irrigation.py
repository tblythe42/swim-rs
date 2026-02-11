"""Plot annual irrigation dynamics from SID netCDF data.

Standalone script (no SwimContainer dependency) that reads a SID netCDF and
produces per-year NDVI timeseries with irrigation event markers.

Usage:
    python scripts/viz_irrigation.py --county 001 --field 001_000001,001_000667 \
        [--root /nas/swim/sid] [--out-dir ~/Downloads/figures/sid_qc] \
        [--years 2015-2023]
"""

import argparse
import os
import re
from glob import glob

import pandas as pd
import plotly.graph_objects as go
import xarray as xr


def read_irr_csv(csv_path, feature_id="FID"):
    """Read IrrMapper CSV and return DataFrame with fid index, year columns."""
    df = pd.read_csv(csv_path)
    df.index = df[feature_id]
    irr_cols = sorted([c for c in df.columns if re.match(r"irr_\d{4}$", c)])
    return df[irr_cols]


def load_data(root, county):
    """Load netCDF and IrrMapper properties for a county."""
    nc_path = os.path.join(root, f"{county}_remote_sensing_ndvi.nc")
    if not os.path.exists(nc_path):
        raise FileNotFoundError(f"NetCDF not found: {nc_path}")
    ds = xr.open_dataset(nc_path)

    irr_files = glob(os.path.join(root, county, "properties", "irr_*.csv"))
    irr_df = read_irr_csv(irr_files[0]) if irr_files else None

    return ds, irr_df


def plot_field_year(ds, irr_df, field, year, out_dir=None):
    """Plot NDVI timeseries with raw obs and irrigation markers for one field-year."""
    dates = pd.to_datetime(ds["date"].values)
    yr_mask = dates.year == year
    yr_dates = dates[yr_mask]

    ndvi = ds["ndvi_irr"].sel(fid=field).values.astype(float)[yr_mask]
    ct = ds["ndvi_irr_ct"].sel(fid=field).values.astype(bool)[yr_mask]

    if ct.sum() == 0:
        return

    # 32-day rolling mean (matching irrigation_dynamics.py)
    ndvi_series = pd.Series(ndvi, index=yr_dates)
    ndvi_smooth = ndvi_series.rolling(window=32, center=True).mean()

    # Raw observation points
    obs_dates = yr_dates[ct]
    obs_values = ndvi[ct]

    # IrrMapper probability for title
    irr_prob_str = ""
    if irr_df is not None:
        col = f"irr_{year}"
        if col in irr_df.columns and field in irr_df.index:
            prob = irr_df.at[field, col]
            irr_prob_str = f" | IrrMapper P={prob:.2f}"

    fig = go.Figure()

    # Smoothed NDVI line
    fig.add_trace(
        go.Scatter(
            x=yr_dates,
            y=ndvi_smooth,
            mode="lines",
            name="Irrigated NDVI (32-day Mean)",
            line=dict(color="green", width=2),
        )
    )

    # Raw Landsat observations
    fig.add_trace(
        go.Scatter(
            x=obs_dates,
            y=obs_values,
            mode="markers",
            name="Landsat Observation",
            marker=dict(size=7, color="darkgreen", symbol="circle"),
        )
    )

    # Irrigation day markers
    if "irr_days" in ds:
        irr_vals = ds["irr_days"].sel(fid=field).values.astype(bool)[yr_mask]
        irr_dates = yr_dates[irr_vals]
        if len(irr_dates) > 0:
            irr_ndvi = ndvi_smooth.reindex(irr_dates)
            fig.add_trace(
                go.Scatter(
                    x=irr_dates,
                    y=irr_ndvi,
                    mode="markers",
                    name="Potential Irrigation Day",
                    marker=dict(
                        size=12,
                        color="blue",
                        symbol="circle-open",
                        line=dict(width=2),
                    ),
                )
            )

    fig.update_layout(
        title=f"{field} — {year}{irr_prob_str}",
        xaxis_title="Date",
        yaxis_title="NDVI",
        template="plotly_white",
        width=1200,
        height=500,
        legend=dict(x=0.01, y=0.99),
        yaxis=dict(range=[0, 1]),
    )

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{field}_{year}.png")
        fig.write_image(path)
        print(f"  {path}")
    else:
        fig.show()


def parse_years(year_str, available_years):
    """Parse year range string like '2015-2023' or 'all'."""
    if year_str is None:
        return available_years
    if "-" in year_str:
        start, end = year_str.split("-")
        return [y for y in available_years if int(start) <= y <= int(end)]
    return [int(y) for y in year_str.split(",") if int(y) in available_years]


def main():
    parser = argparse.ArgumentParser(description="Plot annual irrigation dynamics from SID netCDF")
    parser.add_argument("--county", required=True, help="County code (e.g. 001)")
    parser.add_argument(
        "--field", required=True, help="Field IDs, comma-separated (e.g. 001_000001,001_000667)"
    )
    parser.add_argument("--root", default="/nas/swim/sid", help="SID root directory")
    parser.add_argument("--out-dir", default=None, help="Output directory (default: interactive)")
    parser.add_argument("--years", default=None, help="Year range (e.g. 2015-2023) or all")
    args = parser.parse_args()

    out_dir = os.path.expanduser(args.out_dir) if args.out_dir else None
    ds, irr_df = load_data(args.root, args.county)
    dates = pd.to_datetime(ds["date"].values)
    all_years = sorted(set(dates.year))

    fields = [f.strip() for f in args.field.split(",")]
    years = parse_years(args.years, all_years)

    for field in fields:
        if field not in ds["fid"].values:
            print(f"WARNING: {field} not in dataset, skipping")
            continue
        print(f"\n{field}: {len(years)} years")
        for yr in years:
            plot_field_year(ds, irr_df, field, yr, out_dir=out_dir)

    ds.close()


if __name__ == "__main__":
    main()

# ========================= EOF ====================================================================
