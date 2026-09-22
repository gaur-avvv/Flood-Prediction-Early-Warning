"""Unit tests for the T-32 calibration/metric helpers."""

import numpy as np

from models.flood_model import _calibration_table


def test_calibration_table_well_calibrated():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.05, 0.15, 0.90, 0.95])
    table, ece = _calibration_table(y, p, n_bins=2)
    assert len(table) == 2
    assert ece < 0.1
    assert table[0]["count"] == 2
    assert table[1]["fraction_positive"] == 1.0


def test_calibration_table_empty():
    table, ece = _calibration_table(np.array([]), np.array([]))
    assert table == []
    assert ece == 0.0
