"""
Guarda y carga el Cross Reference (mapeo Material Number -> Forma/Línea).

Por defecto se guarda en data/cross_reference.csv dentro del propio
contenedor de la app. Esto funciona bien mientras la app esté corriendo,
pero en Streamlit Community Cloud el contenedor se puede reiniciar
(por inactividad o al redesplegar), y en ese caso se perdería lo que no
esté también en el repositorio de GitHub.

Para que los materiales nuevos aprobados persistan de verdad semana a
semana, configura un token de GitHub en los "Secrets" de la app
(Settings -> Secrets) así:

    GITHUB_TOKEN = "ghp_xxxxxxxxxxxx"
    GITHUB_REPO  = "tu-usuario/facturacion-app"

Con eso, cada vez que apruebes materiales nuevos, la app hace un commit
directo al archivo data/cross_reference.csv en GitHub, y así queda
guardado para siempre (y visible/editable ahí si algún día quieres
corregir algo a mano).

Si no configuras el token, la app sigue funcionando normal, solo que
usa el archivo local del contenedor (y conviene bajar y subir a mano el
CSV actualizado al repo de vez en cuando, con el botón de descarga que
se puede agregar si se necesita).
"""

import base64
import json
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    import requests
except ImportError:  # requests viene con streamlit, pero por si acaso
    requests = None

LOCAL_PATH = Path(__file__).parent / "data" / "cross_reference.csv"
COLUMNS = ["material_number", "descripcion", "forma", "linea", "fuente", "fecha_agregado"]


def _github_configured() -> bool:
    return "GITHUB_TOKEN" in st.secrets and "GITHUB_REPO" in st.secrets


def load_cross_reference() -> pd.DataFrame:
    if LOCAL_PATH.exists():
        df = pd.read_csv(LOCAL_PATH, dtype={"material_number": str})
    else:
        df = pd.DataFrame(columns=COLUMNS)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[COLUMNS]


def save_cross_reference(df: pd.DataFrame) -> None:
    df = df[COLUMNS].drop_duplicates(subset="material_number", keep="last")
    LOCAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(LOCAL_PATH, index=False)

    if _github_configured() and requests is not None:
        _commit_to_github(df)


def _commit_to_github(df: pd.DataFrame) -> None:
    token = st.secrets["GITHUB_TOKEN"]
    repo = st.secrets["GITHUB_REPO"]
    path = "data/cross_reference.csv"
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    # Necesitamos el sha del archivo actual para poder actualizarlo
    resp = requests.get(url, headers=headers)
    sha = resp.json().get("sha") if resp.status_code == 200 else None

    content = df.to_csv(index=False)
    payload = {
        "message": "Actualiza cross_reference.csv con materiales nuevos aprobados",
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
    }
    if sha:
        payload["sha"] = sha

    put_resp = requests.put(url, headers=headers, data=json.dumps(payload))
    if put_resp.status_code not in (200, 201):
        st.warning(
            "No se pudo guardar el Cross Reference en GitHub "
            f"(status {put_resp.status_code}). Se guardó solo localmente "
            "por ahora; revisa el token/permmisos en Secrets."
        )
