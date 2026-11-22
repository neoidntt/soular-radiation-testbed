from __future__ import annotations

import argparse
import base64
import io
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit


def weibull(let: np.ndarray, let_th: float, sigma_sat: float, s: float, w: float) -> np.ndarray:
    let = np.asarray(let, dtype=float)
    sigma = np.zeros_like(let)
    mask = let >= let_th
    sigma[mask] = sigma_sat * (1.0 - np.exp(-((let[mask] - let_th) / w) ** s))
    return sigma


def log_weibull(let: np.ndarray, let_th: float, sigma_sat: float, s: float, w: float) -> np.ndarray:
    eps = 1e-30
    return np.log10(weibull(let, let_th, sigma_sat, s, w) + eps)


def load_data_from_file(file_path: str | os.PathLike) -> pd.DataFrame:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(path)
    elif suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path)
    else:
        raise ValueError("Only .csv, .xlsx, and .xls files are supported")

    if frame.empty:
        raise ValueError("The selected file does not contain any rows")

    frame = frame.copy()
    frame.columns = [str(col) for col in frame.columns]

    def find_numeric_column(patterns: Tuple[str, ...]) -> Optional[str]:
        for column in frame.columns:
            lowered = column.lower()
            if any(pattern in lowered for pattern in patterns):
                return column
        return None

    x_column = find_numeric_column(("let", "x", "dose", "energy"))
    y_column = find_numeric_column(("sigma", "cross", "yield", "response", "y", "value"))

    if x_column is None or y_column is None:
        numeric_columns = [col for col in frame.columns if pd.api.types.is_numeric_dtype(frame[col])]
        if len(numeric_columns) < 2:
            raise ValueError("Could not find two numeric columns for fitting")
        x_column, y_column = numeric_columns[0], numeric_columns[1]

    let = pd.to_numeric(frame[x_column], errors="coerce")
    sigma = pd.to_numeric(frame[y_column], errors="coerce")
    cleaned = pd.DataFrame({"LET": let, "sigma": sigma}).dropna()
    cleaned = cleaned[(cleaned["LET"] > 0) & (cleaned["sigma"] > 0)]

    if len(cleaned) < 4:
        raise ValueError("At least four positive data points are required for a reliable fit")

    cleaned = cleaned.sort_values("LET").reset_index(drop=True)
    return cleaned


def fit_weibull_model(let: np.ndarray, sigma: np.ndarray) -> Dict[str, float]:
    let = np.asarray(let, dtype=float)
    sigma = np.asarray(sigma, dtype=float)

    mask = np.isfinite(let) & np.isfinite(sigma) & (let > 0) & (sigma > 0)
    let = let[mask]
    sigma = sigma[mask]
    order = np.argsort(let)
    let = let[order]
    sigma = sigma[order]

    if len(let) < 4:
        raise ValueError("At least four positive data points are required for a reliable fit")

    log_sigma = np.log10(np.clip(sigma, np.finfo(float).tiny, None))

    let_th_guess = max(float(np.min(let)) * 0.6, float(np.percentile(let, 25)))
    sigma_sat_guess = max(float(np.max(sigma)) * 1.1, 1e-12)
    s_guess = 2.0
    w_guess = max(float(np.max(let) - np.min(let)) * 0.35, 1.0)

    p0 = [let_th_guess, sigma_sat_guess, s_guess, w_guess]
    bounds = (
        [0.0, 0.0, 0.1, 1e-6],
        [max(float(np.max(let)) * 2.0, 100.0), max(float(np.max(sigma)) * 1000.0, 1.0), 20.0, max(float(np.max(let)) * 10.0, 100.0)],
    )

    popt, _ = curve_fit(
        log_weibull,
        let,
        log_sigma,
        p0=p0,
        bounds=bounds,
        maxfev=200000,
        method="trf",
    )

    let_th, sigma_sat, s, w = popt
    sigma_fit = weibull(let, let_th, sigma_sat, s, w)
    residuals = sigma - sigma_fit
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((sigma - np.mean(sigma)) ** 2)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0

    return {
        "let_th": float(let_th),
        "sigma_sat": float(sigma_sat),
        "s": float(s),
        "w": float(w),
        "r_squared": float(r_squared),
    }


def build_plot(let: np.ndarray, sigma: np.ndarray, result: Dict[str, float]) -> Tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(7, 5))
    let_fit = np.linspace(float(np.min(let)) * 0.9, float(np.max(let)) * 1.1, 400)
    sigma_fit = weibull(let_fit, result["let_th"], result["sigma_sat"], result["s"], result["w"])

    ax.semilogy(let, sigma, "o", label="Data")
    ax.semilogy(let_fit, sigma_fit, "-", label="Weibull fit")
    ax.set_xlabel("LET (MeV·cm²/mg)")
    ax.set_ylabel("Cross section (cm²/device)")
    ax.set_title("Curve fit")
    ax.grid(True, which="both")
    ax.legend()
    fig.tight_layout()
    return fig, ax


def plot_to_base64(let: np.ndarray, sigma: np.ndarray, result: Dict[str, float]) -> str:
    fig, _ = build_plot(let, sigma, result)
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def run_fit(file_path: str | os.PathLike) -> Tuple[pd.DataFrame, Dict[str, float]]:
    data = load_data_from_file(file_path)
    result = fit_weibull_model(data["LET"].to_numpy(), data["sigma"].to_numpy())
    return data, result


def print_summary(data: pd.DataFrame, result: Dict[str, float]) -> None:
    print("\nFit summary")
    print("-" * 40)
    print(f"Points used: {len(data)}")
    print(f"LET_th     = {result['let_th']:.4f} MeV·cm²/mg")
    print(f"sigma_sat  = {result['sigma_sat']:.4e} cm²/device")
    print(f"s          = {result['s']:.4f}")
    print(f"w          = {result['w']:.4f} MeV·cm²/mg")
    print(f"R²         = {result['r_squared']:.4f}")


def build_gui() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    plt.switch_backend("TkAgg")

    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
    except ModuleNotFoundError:
        DND_FILES = None
        TkinterDnD = None

    if TkinterDnD is not None:
        class App(TkinterDnD.Tk):
            def __init__(self) -> None:
                super().__init__()
                self.title("Curvefit Explorer")
                self.geometry("900x650")
                self._build_ui()

            def _build_ui(self) -> None:
                self.columnconfigure(0, weight=1)
                self.rowconfigure(1, weight=1)

                header = ttk.Label(self, text="Drop an Excel/CSV file here or choose one below", font=("Segoe UI", 12))
                header.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="w")

                controls = ttk.Frame(self)
                controls.grid(row=1, column=0, padx=12, pady=8, sticky="ew")
                controls.columnconfigure(1, weight=1)

                ttk.Button(controls, text="Choose file", command=self.select_file).grid(row=0, column=0, padx=(0, 8), pady=4)
                self.path_var = tk.StringVar(value="No file selected")
                ttk.Entry(controls, textvariable=self.path_var, state="readonly").grid(row=0, column=1, sticky="ew")

                self.result_text = tk.Text(self, height=10, wrap="word", padx=8, pady=8)
                self.result_text.grid(row=2, column=0, padx=12, pady=(0, 8), sticky="nsew")

                self.plot_frame = ttk.Frame(self)
                self.plot_frame.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="nsew")
                self.plot_frame.columnconfigure(0, weight=1)
                self.plot_frame.rowconfigure(0, weight=1)

                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<Drop>>", self._handle_drop)

            def select_file(self) -> None:
                file_path = filedialog.askopenfilename(filetypes=[("Data files", "*.csv *.xlsx *.xls"), ("All files", "*.*")])
                if file_path:
                    self._process_file(file_path)

            def _handle_drop(self, event) -> None:
                dropped = event.data
                if dropped.startswith("{") and dropped.endswith("}"):
                    dropped = dropped[1:-1]
                paths = [p for p in dropped.split() if p]
                if paths:
                    self._process_file(paths[0])

            def _process_file(self, file_path: str) -> None:
                self.path_var.set(file_path)
                try:
                    data, result = run_fit(file_path)
                    self.result_text.delete("1.0", tk.END)
                    self.result_text.insert(tk.END, f"Loaded {Path(file_path).name}\n")
                    self.result_text.insert(tk.END, f"Points: {len(data)}\n")
                    self.result_text.insert(tk.END, f"LET_th: {result['let_th']:.4f}\n")
                    self.result_text.insert(tk.END, f"sigma_sat: {result['sigma_sat']:.4e}\n")
                    self.result_text.insert(tk.END, f"s: {result['s']:.4f}\n")
                    self.result_text.insert(tk.END, f"w: {result['w']:.4f}\n")
                    self.result_text.insert(tk.END, f"R²: {result['r_squared']:.4f}\n")
                    self._update_plot(data["LET"].to_numpy(), data["sigma"].to_numpy(), result)
                except Exception as exc:  # pragma: no cover - UI error handling
                    messagebox.showerror("Fit failed", str(exc))

            def _update_plot(self, let: np.ndarray, sigma: np.ndarray, result: Dict[str, float]) -> None:
                for child in self.plot_frame.winfo_children():
                    child.destroy()
                fig, _ = build_plot(let, sigma, result)
                canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
                canvas.draw()
                canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    else:
        class App(tk.Tk):
            def __init__(self) -> None:
                super().__init__()
                self.title("Curvefit Explorer")
                self.geometry("780x520")
                self._build_ui()

            def _build_ui(self) -> None:
                ttk.Label(self, text="Select an Excel/CSV file to fit", font=("Segoe UI", 12)).pack(anchor="w", padx=12, pady=(12, 8))
                ttk.Button(self, text="Choose file", command=self.select_file).pack(anchor="w", padx=12, pady=8)
                self.result_text = tk.Text(self, height=14, wrap="word")
                self.result_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

            def select_file(self) -> None:
                file_path = filedialog.askopenfilename(filetypes=[("Data files", "*.csv *.xlsx *.xls"), ("All files", "*.*")])
                if file_path:
                    self._process_file(file_path)

            def _process_file(self, file_path: str) -> None:
                try:
                    data, result = run_fit(file_path)
                    self.result_text.delete("1.0", tk.END)
                    self.result_text.insert(tk.END, f"Loaded {Path(file_path).name}\n")
                    self.result_text.insert(tk.END, f"Points: {len(data)}\n")
                    self.result_text.insert(tk.END, f"LET_th: {result['let_th']:.4f}\n")
                    self.result_text.insert(tk.END, f"sigma_sat: {result['sigma_sat']:.4e}\n")
                    self.result_text.insert(tk.END, f"s: {result['s']:.4f}\n")
                    self.result_text.insert(tk.END, f"w: {result['w']:.4f}\n")
                    self.result_text.insert(tk.END, f"R²: {result['r_squared']:.4f}\n")
                    build_plot(data["LET"].to_numpy(), data["sigma"].to_numpy(), result)
                    plt.show()
                except Exception as exc:  # pragma: no cover - UI error handling
                    messagebox.showerror("Fit failed", str(exc))

    app = App()
    app.mainloop()


def create_web_app() -> object:
    from flask import Flask, jsonify, render_template_string, request

    app = Flask(__name__)

    html = """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Curvefit Drop Zone</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 24px; background: #f5f7fb; color: #172033; }
        .card { background: white; padding: 24px; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.08); max-width: 800px; margin: auto; }
        .dropzone { border: 2px dashed #4c6ef5; border-radius: 12px; padding: 32px; text-align: center; background: #eef3ff; margin-bottom: 16px; }
        .dropzone.dragover { background: #dbeafe; }
        #result { white-space: pre-wrap; }
        img { max-width: 100%; border-radius: 8px; margin-top: 12px; }
      </style>
    </head>
    <body>
      <div class="card">
        <h2>Curvefit drag-and-drop</h2>
        <p>Drop an Excel or CSV file containing LET and cross-section data.</p>
        <form id="upload-form" enctype="multipart/form-data">
          <div id="dropzone" class="dropzone">Drop file here or click to choose</div>
          <input id="file-input" type="file" accept=".csv,.xlsx,.xls" hidden>
        </form>
        <div id="result">Waiting for a file…</div>
        <img id="plot" alt="fit plot" style="display:none;">
      </div>
      <script>
        const dropzone = document.getElementById('dropzone');
        const fileInput = document.getElementById('file-input');
        const result = document.getElementById('result');
        const plot = document.getElementById('plot');

        function handleFile(file) {
          if (!file) return;
          const formData = new FormData();
          formData.append('file', file);
          result.textContent = 'Fitting…';
          fetch('/fit', { method: 'POST', body: formData })
            .then(async (resp) => {
              const data = await resp.json();
              if (!resp.ok) throw new Error(data.error || 'Fit failed');
              result.textContent = JSON.stringify(data.summary, null, 2);
              plot.src = 'data:image/png;base64,' + data.plot;
              plot.style.display = 'block';
            })
            .catch((err) => {
              result.textContent = err.message;
            });
        }

        dropzone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (event) => handleFile(event.target.files[0]));
        ['dragenter', 'dragover'].forEach((type) => dropzone.addEventListener(type, (event) => {
          event.preventDefault();
          dropzone.classList.add('dragover');
        }));
        ['dragleave', 'drop'].forEach((type) => dropzone.addEventListener(type, (event) => {
          event.preventDefault();
          dropzone.classList.remove('dragover');
        }));
        dropzone.addEventListener('drop', (event) => handleFile(event.dataTransfer.files[0]));
      </script>
    </body>
    </html>
    """

    @app.route("/")
    def index() -> str:
        return render_template_string(html)

    @app.route("/fit", methods=["POST"])
    def fit_endpoint():
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        uploaded_file = request.files["file"]
        if uploaded_file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.filename).suffix) as temp_file:
            uploaded_file.save(temp_file.name)
            data, result = run_fit(temp_file.name)
            plot_data = plot_to_base64(data["LET"].to_numpy(), data["sigma"].to_numpy(), result)

        os.unlink(temp_file.name)
        return jsonify({
            "summary": {
                "points": len(data),
                "let_th": result["let_th"],
                "sigma_sat": result["sigma_sat"],
                "s": result["s"],
                "w": result["w"],
                "r_squared": result["r_squared"],
            },
            "plot": plot_data,
        })

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit a Weibull curve to LET/sigma data from Excel or CSV")
    parser.add_argument("input_file", nargs="?", help="Path to .csv/.xlsx/.xls data file")
    parser.add_argument("--plot", action="store_true", help="Show the fitted plot")
    parser.add_argument("--gui", action="store_true", help="Open the desktop GUI")
    parser.add_argument("--web", action="store_true", help="Start the drag-and-drop web app")
    parser.add_argument("--host", default="127.0.0.1", help="Host for the web app")
    parser.add_argument("--port", type=int, default=5000, help="Port for the web app")
    args = parser.parse_args()

    if args.web:
        app = create_web_app()
        app.run(debug=True, host=args.host, port=args.port)
        return

    if args.gui or not args.input_file:
        build_gui()
        return

    data, result = run_fit(args.input_file)
    print_summary(data, result)

    if args.plot:
        fig, _ = build_plot(data["LET"].to_numpy(), data["sigma"].to_numpy(), result)
        plt.show()


if __name__ == "__main__":
    main()
