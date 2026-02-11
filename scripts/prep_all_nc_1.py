# Code to process NDVI capture date data for the SID 1991-2023 and output to netcdf files.
# Reads from local CSVs (synced from GCS) instead of calling Earth Engine.
# 1/26/26 hannah.haugen@mt.gov

import os
import re
import time
from glob import glob

import numpy as np
import pandas as pd
import xarray
from tqdm import tqdm

FEATURE_ID = "FID"


def read_ndvi_csvs(csv_dir, mask_type, feature_id="FID"):
    """Read per-year NDVI CSVs from a county directory and concatenate.

    Auto-discovers years from filenames matching ndvi_{mask_type}_{year}*.csv.
    Returns DataFrame with FID index, scene-ID columns (same format as
    clustered_sample_ndvi_direct_2 output).
    """
    pattern = os.path.join(csv_dir, "ndvi", mask_type, f"ndvi_{mask_type}_*.csv")
    files = sorted(glob(pattern))
    if not files:
        raise FileNotFoundError(f"No NDVI CSVs found matching {pattern}")

    dfs = []
    for f in files:
        df = pd.read_csv(f)
        df.index = df[feature_id]
        # Drop the FID column (it's now the index) and any geo column
        df.drop(columns=[feature_id, "geo"], inplace=True, errors="ignore")
        dfs.append(df)

    return pd.concat(dfs, axis=1)


def read_irr_csv(csv_path, feature_id="FID"):
    """Read IrrMapper CSV and return xarray Dataset with dims (fid, year), var 'irr'."""
    df = pd.read_csv(csv_path)
    df.index = df[feature_id]

    irr_cols = [c for c in df.columns if re.match(r"irr_\d{4}$", c)]
    irr_cols = sorted(irr_cols)
    years = [int(c.split("_")[1]) for c in irr_cols]

    irr_data = df[irr_cols].values  # shape: (n_fid, n_year)
    ds = xarray.Dataset(
        {"irr": (["fid", "year"], irr_data)},
        coords={"fid": df.index.values, "year": years},
    )
    return ds


def discover_year_range(csv_dir, mask_type):
    """Discover min/max years from NDVI CSV filenames."""
    pattern = os.path.join(csv_dir, "ndvi", mask_type, f"ndvi_{mask_type}_*.csv")
    files = glob(pattern)
    years = []
    for f in files:
        basename = os.path.basename(f)
        match = re.search(r"ndvi_\w+_(\d{4})", basename)
        if match:
            years.append(int(match.group(1)))
    if not years:
        raise FileNotFoundError(f"No NDVI CSVs found matching {pattern}")
    return min(years), max(years)


def clustered_landsat_time_series_nc(
    image_df, start_yr=2000, end_yr=2024, feature_id="FID", var_name=None
):
    """
    Intended to process Earth Engine extracts of clustered field data. See e.g., ndvi_export.clustered_field_ndvi()
    to generate such data. The output of this function should be the same format and structure as that from
    landsat_time_series_image() and landsat_time_series_station().
    """
    dt_index = pd.date_range(f"{start_yr}-01-01", f"{end_yr}-12-31", freq="D")

    field = image_df
    cols = [c for c in field.columns if re.match(r"\d{8}$", c.split("_")[-1])]
    f_idx = [c.split("_")[-1] for c in cols]
    f_idx = [pd.to_datetime(i) for i in f_idx]
    field = pd.DataFrame(columns=field.index, data=field[cols].values.T, index=f_idx)
    duplicates = field[field.index.duplicated(keep=False)]
    if not duplicates.empty:
        field = field.resample("D").max()
    field = field.sort_index()

    field[field.values == 0.00] = np.nan

    # for both NDVI and ETf, values in agriculture and the vegetated land surface generally,
    # should not go below about 0.01
    # captures of these low values are likely small pixel samples on SLC OFF Landsat 7 or
    # on bad polygons that include water or some other land cover we don't want to use
    # see e.g., https://code.earthengine.google.com/5ea8bc8c6134845a8c0c81a4cdb99fc0
    # TODO: examine these thresholds, prob better to extract pixel count to filter data

    diff_back = field.diff().values
    field = pd.DataFrame(
        index=field.index,
        columns=field.columns,
        data=np.where(diff_back < -0.1, np.nan, field.values),
    )

    diff_for = field.shift(periods=2).diff()
    diff_for = diff_for.shift(periods=-3).values
    field = pd.DataFrame(
        index=field.index,
        columns=field.columns,
        data=np.where(diff_for > 0.1, np.nan, field.values),
    )

    field[field.values < 0.2] = np.nan

    ct = ~pd.isna(field)

    df = field.copy()
    df = df.astype(float).interpolate()
    df = df.reindex(dt_index)

    df = df.interpolate().bfill()
    df = df.interpolate().ffill()

    ct = ct.reindex(dt_index)
    ct = ct.fillna(0)
    ct = ct.astype(bool)

    adf = df.copy()
    ctdf = ct.copy()

    adf = adf.melt(var_name="FID", value_name=var_name, ignore_index=False)
    adf.index = adf.index.set_names("date")
    adf = adf.set_index("FID", append=True)

    ctdf = ctdf.melt(var_name="FID", value_name=f"{var_name}_ct", ignore_index=False)
    ctdf.index = ctdf.index.set_names("date")
    ctdf = ctdf.set_index("FID", append=True)

    axr = adf.to_xarray()
    ctxr = ctdf.to_xarray()

    return axr, ctxr


def detect_cuttings_nc(landsat, irr_ds, irr_threshold=0.1):
    lst = landsat
    years = list(set([i.year for i in pd.to_datetime(lst.date.values)]))
    irr = irr_ds

    mi = pd.MultiIndex.from_product([lst.date.values, lst.FID.values], names=["date", "FID"])
    irr_days = pd.DataFrame(np.zeros(len(mi), dtype="bool"), index=mi, columns=["irr_days"])

    for field in lst.FID.values:
        for yr in years:
            if yr not in irr.year.values:
                continue
            irrigated = irr.irr.sel(fid=field, year=yr) > irr_threshold
            if not irrigated:
                continue
            irr_doys = []

            df = lst.ndvi_irr.loc[f"{yr}-01-01" : f"{yr}-12-31", field].to_dataframe()
            df["doy"] = [i.dayofyear for i in df.index]
            df["ndvi_irr"] = df["ndvi_irr"].rolling(window=10, center=True).mean()
            df["diff"] = df["ndvi_irr"].diff()

            local_min_indices = df[(df["diff"] > 0) & (df["diff"].shift(1) < 0)].index

            positive_slope = df["diff"] > 0
            groups = (positive_slope != positive_slope.shift()).cumsum()
            df["groups"] = groups
            group_counts = positive_slope.groupby(groups).sum()
            long_positive_slope_groups = group_counts[group_counts >= 10].index

            for group in long_positive_slope_groups:
                group_indices = positive_slope[groups == group].index
                start_index = group_indices[0]
                end_index = group_indices[-1]

                if start_index in local_min_indices:
                    start_day = start_index - pd.Timedelta(days=5)
                    end_day = end_index - pd.Timedelta(days=5)
                    irr_doys.extend(pd.date_range(start_day, end_day))
                else:
                    end_day = end_index - pd.Timedelta(days=5)
                    irr_doys.extend(pd.date_range(start_index, end_day))

            irr_doys = sorted(list(set(irr_doys)))
            indices = [(i, field) for i in irr_doys]
            irr_days["irr_days"] = irr_days["irr_days"].where(~irr_days.index.isin(indices), True)

    irr_days = irr_days.to_xarray()
    return irr_days


def process_county(data_dir, out_file, do_inv_irr=True):
    """Process a county's NDVI and IrrMapper CSVs into a netCDF file.

    Parameters
    ----------
    data_dir : str
        Path to county directory under /nas/swim/sid/ containing ndvi/ and properties/ subdirs.
    out_file : str
        Path for output netCDF.
    do_inv_irr : bool
        Whether to also process inverse-irrigated NDVI.
    """
    if os.path.exists(out_file):
        print(f"{out_file} exists, skipping")
        return

    types_ = ["inv_irr", "irr"] if do_inv_irr else ["irr"]

    # Discover year range from the irr CSVs (they have the widest coverage)
    start_yr, end_yr = discover_year_range(data_dir, "irr")
    print(f"  Year range: {start_yr}-{end_yr}")

    ndvi_irr = None
    rs_xrs = []
    start_time = time.time()

    for mask_type in types_:
        imgs = read_ndvi_csvs(data_dir, mask_type, feature_id=FEATURE_ID)

        ts, count = clustered_landsat_time_series_nc(
            imgs,
            start_yr=start_yr,
            end_yr=end_yr,
            feature_id=FEATURE_ID,
            var_name=f"ndvi_{mask_type}",
        )

        rs_xrs.append(ts)
        rs_xrs.append(count)
        if mask_type == "irr":
            ndvi_irr = ts

    print(f"  NDVI processing: {time.time() - start_time:.2f}s")

    if ndvi_irr is not None:
        # Find the IrrMapper CSV
        irr_pattern = os.path.join(data_dir, "properties", "irr_*.csv")
        irr_files = glob(irr_pattern)
        if irr_files:
            irr_ds = read_irr_csv(irr_files[0], feature_id=FEATURE_ID)
            print("  Running detect_cuttings")
            irr_days = detect_cuttings_nc(ndvi_irr, irr_ds, irr_threshold=0.1)
            rs_xrs.append(irr_days)
        else:
            print(f"  No IrrMapper CSV found at {irr_pattern}, skipping detect_cuttings")
    else:
        print("  No irrigated ndvi info, skipping detect_cuttings")

    start_time = time.time()
    rs = xarray.merge(rs_xrs)
    rs = rs.rename({"FID": "fid"})
    print(rs)
    rs.to_netcdf(out_file)
    print(f"  Saved: {out_file} ({time.time() - start_time:.2f}s)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build SID NDVI netCDFs from local CSVs")
    parser.add_argument(
        "--counties",
        type=str,
        default=None,
        help="Comma-separated county codes to process (e.g., '001,073a,081a'). Default: all.",
    )
    parser.add_argument(
        "--root",
        type=str,
        default="/nas/swim/sid",
        help="Root directory containing county subdirectories.",
    )
    args = parser.parse_args()

    root = args.root

    # Auto-discover county directories (numeric subdirectories)
    all_counties = sorted(
        [
            d
            for d in os.listdir(root)
            if os.path.isdir(os.path.join(root, d)) and re.match(r"\d{3}[a-d]?$", d)
        ]
    )

    if args.counties:
        selected = {c.strip() for c in args.counties.split(",")}
        counties = [c for c in all_counties if c in selected]
        missing = selected - set(counties)
        if missing:
            print(f"Warning: requested counties not found: {missing}")
    else:
        counties = all_counties

    print(f"Processing {len(counties)} of {len(all_counties)} county directories")

    for county in tqdm(counties, total=len(counties)):
        county_dir = os.path.join(root, county)
        out_nc = os.path.join(root, f"{county}_remote_sensing_ndvi.nc")

        print(f"\n=== County {county} ===")
        try:
            process_county(county_dir, out_nc, do_inv_irr=True)
        except FileNotFoundError as e:
            print(f"  Skipping: {e}")

# ========================= EOF ====================================================================
