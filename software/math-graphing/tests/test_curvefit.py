from pathlib import Path

import numpy as np

from curvefit.curvefit import fit_weibull_model, load_data_from_file


def test_fit_weibull_model_returns_positive_parameters():
    let = np.array([0.89, 1.64, 7.0, 16.0, 25.0], dtype=float)
    sigma = np.array([4.73e-08, 2.72e-6, 6.36e-5, 2.8e-4, 2.3e-4], dtype=float)

    result = fit_weibull_model(let, sigma)

    assert result["let_th"] > 0
    assert result["sigma_sat"] > 0
    assert result["s"] > 0
    assert result["w"] > 0
    assert np.isfinite(result["r_squared"])


def test_load_data_from_file_reads_csv(tmp_path: Path):
    data_path = tmp_path / "sample.csv"
    data_path.write_text("LET,sigma\n0.89,4.73e-8\n1.64,2.72e-6\n", encoding="utf-8")

    df = load_data_from_file(data_path)

    assert list(df.columns) == ["LET", "sigma"]
    assert len(df) == 2
