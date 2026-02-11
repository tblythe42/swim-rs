"""SID data diagnostics — observation frequency, missingness, and irrigation detection QC.

Standalone script (no SwimContainer dependency) that reads a SID netCDF and
produces console stats + plotly figures for one or more fields.

Usage:
    python scripts/sid_diagnostics.py --county 099 --field 099_001434 \
        [--root /nas/swim/sid] [--out-dir ~/Downloads/figures/sid_qc]
"""

import argparse
import os
import re
from glob import glob

import pandas as pd
import plotly.graph_objects as go
import xarray as xr
from plotly.subplots import make_subplots


def read_irr_csv(csv_path, feature_id="FID"):
    """Read IrrMapper CSV and return DataFrame with fid index, year columns."""
    df = pd.read_csv(csv_path)
    df.index = df[feature_id]
    irr_cols = sorted([c for c in df.columns if re.match(r"irr_\d{4}$", c)])
    return df[irr_cols]


def load_data(root, county):
    """Load netCDF and IrrMapper properties for a county.

    Returns (xr.Dataset, pd.DataFrame or None).
    """
    nc_path = os.path.join(root, f"{county}_remote_sensing_ndvi.nc")
    if not os.path.exists(nc_path):
        raise FileNotFoundError(f"NetCDF not found: {nc_path}")
    ds = xr.open_dataset(nc_path)

    irr_files = glob(os.path.join(root, county, "properties", "irr_*.csv"))
    irr_df = read_irr_csv(irr_files[0]) if irr_files else None

    return ds, irr_df


def print_stats(ds, irr_df, field):
    """Print per-year observation counts, coverage, and irrigation stats."""
    ct = ds["ndvi_irr_ct"].sel(fid=field).values.astype(bool)
    dates = pd.to_datetime(ds["date"].values)

    irr_days = None
    if "irr_days" in ds:
        irr_days = ds["irr_days"].sel(fid=field).values.astype(bool)

    print(f"\n{'=' * 60}")
    print(f"  Field: {field}")
    print(f"  Date range: {dates[0].date()} to {dates[-1].date()}")
    print(f"  Total days: {len(dates)}")
    print(f"  Total observations: {ct.sum()}")
    print(f"  Overall coverage: {ct.sum() / len(dates) * 100:.1f}%")
    print(f"{'=' * 60}")

    print(f"\n{'Year':>6}  {'Obs':>5}  {'Irr Days':>9}  {'IrrMapper Prob':>15}")
    print(f"{'----':>6}  {'---':>5}  {'--------':>9}  {'--------------':>15}")

    years = sorted(set(dates.year))
    for yr in years:
        yr_mask = dates.year == yr
        yr_obs = ct[yr_mask].sum()

        yr_irr = ""
        if irr_days is not None:
            yr_irr = str(irr_days[yr_mask].sum())

        irr_prob = ""
        if irr_df is not None:
            col = f"irr_{yr}"
            if col in irr_df.columns and field in irr_df.index:
                irr_prob = f"{irr_df.at[field, col]:.2f}"

        print(f"{yr:>6}  {yr_obs:>5}  {yr_irr:>9}  {irr_prob:>15}")

    print()


def coverage_figure(ds, irr_df, field, out_dir=None):
    """Multi-year bar chart of observation counts with irrigation day overlay."""
    ct = ds["ndvi_irr_ct"].sel(fid=field).values.astype(bool)
    dates = pd.to_datetime(ds["date"].values)
    years = sorted(set(dates.year))

    obs_counts = []
    irr_counts = []
    has_irr = "irr_days" in ds

    if has_irr:
        irr_vals = ds["irr_days"].sel(fid=field).values.astype(bool)

    for yr in years:
        yr_mask = dates.year == yr
        obs_counts.append(int(ct[yr_mask].sum()))
        if has_irr:
            irr_counts.append(int(irr_vals[yr_mask].sum()))

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=years,
            y=obs_counts,
            name="Landsat Observations",
            marker_color="steelblue",
            opacity=0.7,
        ),
        secondary_y=False,
    )

    if has_irr and any(c > 0 for c in irr_counts):
        fig.add_trace(
            go.Scatter(
                x=years,
                y=irr_counts,
                mode="lines+markers",
                name="Irrigation Days",
                line=dict(color="firebrick", width=2),
                marker=dict(size=5),
            ),
            secondary_y=True,
        )

    fig.update_layout(
        title=f"{field} — Observation Density & Irrigation Activity",
        xaxis_title="Year",
        legend=dict(x=0.01, y=0.99),
        template="plotly_white",
        width=1200,
        height=500,
    )
    fig.update_yaxes(title_text="Observations / Year", secondary_y=False)
    fig.update_yaxes(title_text="Irrigation Days / Year", secondary_y=True)

    _save_or_show(fig, out_dir, f"{field}_coverage.png")


def yearly_figures(ds, irr_df, field, out_dir=None):
    """Per-year NDVI timeseries with raw observations and irrigation markers."""
    ndvi = ds["ndvi_irr"].sel(fid=field).values.astype(float)
    ct = ds["ndvi_irr_ct"].sel(fid=field).values.astype(bool)
    dates = pd.to_datetime(ds["date"].values)

    has_irr = "irr_days" in ds
    if has_irr:
        irr_vals = ds["irr_days"].sel(fid=field).values.astype(bool)

    years = sorted(set(dates.year))

    for yr in years:
        yr_mask = dates.year == yr
        yr_dates = dates[yr_mask]
        yr_ndvi = ndvi[yr_mask]
        yr_ct = ct[yr_mask]

        if yr_ct.sum() == 0:
            continue

        # 10-day rolling mean (matches detect_cuttings_nc smoothing)
        ndvi_series = pd.Series(yr_ndvi, index=yr_dates)
        ndvi_smooth = ndvi_series.rolling(window=10, center=True).mean()

        # Raw observation dates/values
        obs_dates = yr_dates[yr_ct]
        obs_values = yr_ndvi[yr_ct]

        # IrrMapper probability for title
        irr_prob_str = ""
        if irr_df is not None:
            col = f"irr_{yr}"
            if col in irr_df.columns and field in irr_df.index:
                irr_prob_str = f" | IrrMapper P={irr_df.at[field, col]:.2f}"

        fig = go.Figure()

        fig.add_trace(
            go.Scatter(
                x=yr_dates,
                y=ndvi_smooth,
                mode="lines",
                name="NDVI (10-day mean)",
                line=dict(color="green", width=2),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=obs_dates,
                y=obs_values,
                mode="markers",
                name="Raw Observations",
                marker=dict(size=6, color="darkgreen", symbol="circle"),
            )
        )

        if has_irr:
            yr_irr = irr_vals[yr_mask]
            irr_dates = yr_dates[yr_irr]
            if len(irr_dates) > 0:
                irr_ndvi = ndvi_smooth.reindex(irr_dates)
                fig.add_trace(
                    go.Scatter(
                        x=irr_dates,
                        y=irr_ndvi,
                        mode="markers",
                        name="Irrigation Days",
                        marker=dict(
                            size=10,
                            color="blue",
                            symbol="circle-open",
                            line=dict(width=2),
                        ),
                    )
                )

        fig.update_layout(
            title=f"{field} — {yr}{irr_prob_str}",
            xaxis_title="Date",
            yaxis_title="NDVI",
            template="plotly_white",
            width=1200,
            height=500,
            legend=dict(x=0.01, y=0.99),
        )

        _save_or_show(fig, out_dir, f"{field}_{yr}.png")


def _save_or_show(fig, out_dir, filename):
    """Write figure to PNG or show interactively."""
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, filename)
        fig.write_image(path)
        print(f"  Wrote {path}")
    else:
        fig.show()


def main():
    parser = argparse.ArgumentParser(
        description="SID data diagnostics — observation frequency, missingness, irrigation QC"
    )
    parser.add_argument("--county", required=True, help="County code (e.g. 099)")
    parser.add_argument(
        "--field", required=True, help="Field ID (e.g. 099_001434). Comma-separated for multiple."
    )
    parser.add_argument("--root", default="/nas/swim/sid", help="SID root directory")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for figures (default: show interactively)",
    )
    args = parser.parse_args()

    out_dir = os.path.expanduser(args.out_dir) if args.out_dir else None
    ds, irr_df = load_data(args.root, args.county)

    fields = [f.strip() for f in args.field.split(",")]

    for field in fields:
        if field not in ds["fid"].values:
            print(f"WARNING: field {field} not found in dataset, skipping")
            continue

        print_stats(ds, irr_df, field)
        coverage_figure(ds, irr_df, field, out_dir=out_dir)
        yearly_figures(ds, irr_df, field, out_dir=out_dir)

    ds.close()


if __name__ == "__main__":
    main()

# ========================= EOF ====================================================================
