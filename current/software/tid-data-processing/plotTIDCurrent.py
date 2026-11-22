import os
import glob
import pandas as pd
import matplotlib.pyplot as plt

DATA_DIR = r"C:\SOULARCurriculum\PowerShow\Postprocessing"

# Only process text files
files = glob.glob(os.path.join(DATA_DIR, "RunOUT*_DUT*.txt"))

for file_path in files:
    file_name = os.path.basename(file_path)
    print(f"Processing: {file_name}")

    try:
        df = pd.read_csv(
            file_path,
            sep=r"\s+|,",
            engine="python"
        )
    except Exception as e:
        print(f"Skipping {file_name}: could not read file: {e}")
        continue

    # Remove leading/trailing spaces from column names
    df.columns = df.columns.str.strip()

    # Determine which current columns exist
    if {"I1", "I2", "I3"}.issubset(df.columns):
        I1_col = "I1"
        I2_col = "I2"
        I3_col = "I3"
        current_units = "Current (A)"

    elif {"I1_uA", "I2_uA", "I3_uA"}.issubset(df.columns):
        I1_col = "I1_uA"
        I2_col = "I2_uA"
        I3_col = "I3_uA"
        current_units = "Current (uA)"

    else:
        print(f"Skipping {file_name}: could not find current columns")
        continue

    required_cols = ["datetime", "mysec", "V1", "V2", "V3"]

    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        print(f"Skipping {file_name}: missing columns {missing}")
        continue

    # Convert to numeric
    for col in ["mysec", I1_col, I2_col, I3_col]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Remove rows with invalid values
    df = df.dropna(subset=["mysec", I1_col, I2_col, I3_col])

    if df.empty:
        print(f"Skipping {file_name}: no valid data")
        continue

    # Build elapsed time axis (mysec contains delta time)
    time_sec = df["mysec"].cumsum()
    time_sec -= time_sec.iloc[0]

    # Determine board name
    file_upper = file_name.upper()

    if "_DUT1" in file_upper:
        board_name = "Board 1"
    elif "_DUT2" in file_upper:
        board_name = "Board 2"
    else:
        board_name = "Unknown Board"

    # Remove extension and DUT identifier
    base_name = os.path.splitext(file_name)[0]

    run_name = base_name.replace("_DUT1", "")
    run_name = run_name.replace("_DUT2", "")
    run_name = run_name.replace("_dut1", "")
    run_name = run_name.replace("_dut2", "")

    # Create plot
    plt.figure(figsize=(10, 6))

    # Channel 1 is always plotted
    plt.plot(time_sec, df[I1_col], label="Channel 1")

    # Channel 2 exists only on Board 2
    if board_name == "Board 2":
        plt.plot(time_sec, df[I2_col], label="Channel 2")

    # Channel 3 is always plotted
    plt.plot(time_sec, df[I3_col], label="Channel 3")

    plt.xlabel("Time (seconds)")
    plt.ylabel(current_units)
    plt.title(f"{run_name} - {board_name} Current vs Time")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    output_file = os.path.join(
        DATA_DIR,
        f"{run_name}_{board_name}_currents.png"
    )

    plt.savefig(output_file, dpi=300)
    plt.close()

    print(f"Saved: {output_file}")

print("Done.")