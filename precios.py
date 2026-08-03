from pathlib import Path

import pandas as pd

LOCAL_PATH = Path(__file__).parent / "data" / "precios.csv"


def load_precios() -> pd.DataFrame:
    """pt_final, precio_unitario"""
    return pd.read_csv(LOCAL_PATH)
