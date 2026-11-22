import os
import tkinter as tk
from tkinter import filedialog

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import least_squares

# ============================================================
# SELECT EXCEL FILE THAT CONTAINS LET AND CROSS SECTION DATA
# ============================================================

root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)

excel_file = filedialog.askopenfilename(
    title="Select Excel file with LET and CrossSection data",
    filetypes=[
        ("Excel files", "*.xlsx *.xls"),
        ("All files", "*.*")
    ]
)

root.destroy()

if not excel_file:
    raise FileNotFoundError("No Excel file selected.")

sheet_name = "Sheet1"

LET_column = "LET"
sigma_column = "CrossSection"

floor_cutoff = 1e-17

# ============================================================
# Weibull cross-section model
# ============================================================

def weibull(LET, LET_th, sigma_sat, s, w):
    LET = np.array(LET, dtype=float)
    sigma = np.zeros_like(LET)

    idx = LET > LET_th
    sigma[idx] = sigma_sat * (
        1.0 - np.exp(-((LET[idx] - LET_th) / w) ** s)
    )

    return sigma

# ============================================================
# Log-space residuals
# ============================================================

def residuals(params, LET, log_sigma):
    LET_th, log_sigma_sat, s, w = params
    sigma_sat = 10 ** log_sigma_sat

    pred_sigma = weibull(LET, LET_th, sigma_sat, s, w)
    pred_log_sigma = np.log10(pred_sigma + 1e-30)

    return log_sigma - pred_log_sigma

# ============================================================
# Helper: safely convert Excel text/numbers to float
# Handles values like:
# 2.80 E-04, 2.80E-04, 2.80e-04, 4.73E-08
# ============================================================

def clean_numeric_column(series):
    return (
        series
        .astype(str)
        .str.strip()
        .str.replace(" ", "", regex=False)
        .str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )

# ============================================================
# Read data from selected Excel file
# ============================================================

df = pd.read_excel(excel_file, sheet_name=sheet_name)

if LET_column not in df.columns or sigma_column not in df.columns:
    raise ValueError(
        f"Excel file must contain columns named '{LET_column}' and '{sigma_column}'.\n"
        f"Columns found: {list(df.columns)}"
    )

LET_clean = clean_numeric_column(df[LET_column])
sigma_clean = clean_numeric_column(df[sigma_column])

clean_df = pd.DataFrame({
    LET_column: LET_clean,
    sigma_column: sigma_clean
})

clean_df = clean_df.dropna(subset=[LET_column, sigma_column])

LET_all = clean_df[LET_column].to_numpy(dtype=float)
sigma_all = clean_df[sigma_column].to_numpy(dtype=float)

# Sort by LET
sort_idx = np.argsort(LET_all)
LET_all = LET_all[sort_idx]
sigma_all = sigma_all[sort_idx]

print(f"\nSelected file:\n{excel_file}")

print("\nData read from Excel:")
for L, sig in zip(LET_all, sigma_all):
    print(f"LET={L:6.2f}  sigma={sig:.4e}")

# ============================================================
# Remove floor / no-event points
# ============================================================

fit_mask = sigma_all > floor_cutoff

LET = LET_all[fit_mask]
sigma = sigma_all[fit_mask]

if len(LET) < 4:
    raise ValueError("Not enough data points above floor_cutoff for Weibull fit.")

log_sigma = np.log10(sigma)

min_LET = np.min(LET)
max_LET = np.max(LET)
LET_span = max_LET - min_LET
max_sigma = np.max(sigma)

# ============================================================
# Data-driven LET threshold bounds
# ============================================================

real_idx = np.where(sigma_all > floor_cutoff)[0]
first_real_idx = real_idx[0]

if first_real_idx > 0:
    LET_th_low = LET_all[first_real_idx - 1]
    LET_th_high = LET_all[first_real_idx]
else:
    LET_th_low = LET_all[0] * 0.1
    LET_th_high = LET_all[0]

LET_th_low = max(LET_th_low, LET_all[0] * 0.1)
LET_th_high = min(LET_th_high, np.min(LET) * 0.999)

LET_th_guess = 0.5 * (LET_th_low + LET_th_high)

p0 = [
    LET_th_guess,
    np.log10(max_sigma * 2.0),
    1.2,
    LET_span
]

bounds_low = [
    LET_th_low,
    np.log10(max_sigma * 1.001),
    0.2,
    LET_span / 100.0
]

bounds_high = [
    LET_th_high,
    np.log10(max_sigma * 100.0),
    20.0,
    LET_span * 20.0
]

# ============================================================
# Fit in log space
# ============================================================

fit = least_squares(
    residuals,
    p0,
    bounds=(bounds_low, bounds_high),
    args=(LET, log_sigma),
    loss="soft_l1",
    f_scale=0.5,
    max_nfev=500000
)

LET_th, log_sigma_sat, s, w = fit.x
sigma_sat = 10 ** log_sigma_sat

print("\nWeibull fit:")
print(f"LET_th    = {LET_th:.4f} MeV·cm²/mg")
print(f"sigma_sat = {sigma_sat:.4e} cm²/device")
print(f"s         = {s:.4f}")
print(f"w         = {w:.4f} MeV·cm²/mg")

print("\nThreshold bounds used:")
print(f"LET_th_low  = {LET_th_low:.4f}")
print(f"LET_th_high = {LET_th_high:.4f}")

print("\nExcluded from fit:")
for L, sig in zip(LET_all[~fit_mask], sigma_all[~fit_mask]):
    print(f"LET={L:6.2f}  sigma={sig:.4e}")

# ============================================================
# R² and RMSE
# ============================================================

pred_sigma = weibull(LET, LET_th, sigma_sat, s, w)
pred_log_sigma = np.log10(pred_sigma + 1e-30)

SS_res_log = np.sum((log_sigma - pred_log_sigma) ** 2)
SS_tot_log = np.sum((log_sigma - np.mean(log_sigma)) ** 2)
R2_log = 1.0 - SS_res_log / SS_tot_log

SS_res_lin = np.sum((sigma - pred_sigma) ** 2)
SS_tot_lin = np.sum((sigma - np.mean(sigma)) ** 2)
R2_linear = 1.0 - SS_res_lin / SS_tot_lin

RMSE_decades = np.sqrt(np.mean((log_sigma - pred_log_sigma) ** 2))

print(f"\nR², log space    = {R2_log:.6f}")
print(f"R², linear space = {R2_linear:.6f}")
print(f"RMSE             = {RMSE_decades:.4f} decades")

# ============================================================
# Residuals
# ============================================================

resid = log_sigma - pred_log_sigma

print("\nLog-space residuals:")
for L, sig, pred, r in zip(LET, sigma, pred_sigma, resid):
    print(
        f"LET={L:6.2f}  "
        f"data={sig:.4e}  "
        f"fit={pred:.4e}  "
        f"residual={r:+.4f} decades"
    )

# ============================================================
# Plot
# ============================================================

LET_fit_min = LET_all[0] * 0.5
LET_fit_max = max_LET * 1.25

LET_fit = np.linspace(LET_fit_min, LET_fit_max, 1000)
sigma_fit = weibull(LET_fit, LET_th, sigma_sat, s, w)

plt.figure(figsize=(7, 5))

plt.semilogy(LET_all, sigma_all, "o", label="All data")
plt.semilogy(LET, sigma, "o", label="Fit data only")
plt.semilogy(LET_fit, sigma_fit, "-", label="Weibull fit")

plt.axvline(LET_th, linestyle="--", label=f"LET_th = {LET_th:.3f}")

plt.xlabel("LET (MeV·cm²/mg)")
plt.ylabel("Cross section (cm²/device)")
plt.grid(True, which="both")
plt.legend()
plt.tight_layout()

# ============================================================
# Save PNG with same name as selected Excel file
# Example:
# C:\SOULARCurriculum\CurveFit\SEE_Data.xlsx
# becomes
# C:\SOULARCurriculum\CurveFit\SEE_Data.png
# ============================================================

png_file = os.path.splitext(excel_file)[0] + ".png"

plt.savefig(png_file, dpi=300, bbox_inches="tight")

print(f"\nPlot saved to:\n{png_file}")

plt.show()