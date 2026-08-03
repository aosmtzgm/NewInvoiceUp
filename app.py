"""
Facturación Semanal YETI — App de automatización
--------------------------------------------------
Reemplaza el proceso manual de:
  1.Data SAP -> 2.PivotTable -> 3.PT-Creation -> 4.MasterTable -> 5.Invoice
  -> Container/PO Line/Release Upload Templates

Flujo:
  1. Subes el reporte semanal de SAP.
  2. La app agrupa por Material Number, clasifica cada material
     (usando el Cross Reference guardado, o la regla automática si es nuevo).
  3. Revisas/apruebas los materiales nuevos.
  4. La app genera el resumen de las 10 categorías de PT + los 3 CSV
     listos para subir a PLEX SSE.
"""

import io
import re
from datetime import date, datetime

import pandas as pd
import streamlit as st

from clasificador import clasificar_forma_linea, pt_final
from cross_reference_store import load_cross_reference, save_cross_reference
from plex_templates import build_container_csv, build_po_line_csv, build_release_csv
from precios import load_precios

st.set_page_config(page_title="Facturación Semanal YETI", layout="wide")

# ---------------------------------------------------------------------------
# Constantes fijas (confirmadas: nunca cambian)
# ---------------------------------------------------------------------------
CUSTOMER_CODE = "YETI"
APPROVED_SHIP_TO = "YETI YC2 1310 1104480"
LOCATION = "Facturacion YCDos"
TERMS = "Net 45"
MASTER_UNIT_NO = "000012"
OPERATION = "Otros Servicios - Pza (Pcs)"

PT_CATEGORIES = [
    "PT-1LOGO-DC", "PT-2LOGOS-DC", "PT-BUCKET-DC",
    "PT-1LOGOSHAKER-DC", "PT-2LOGOSHAKER-DC",
    "PT-1LOGO-SS", "PT-2LOGOS-SS", "PT-BUCKET-SS",
    "PT-1LOGOSHAKER-SS", "PT-2LOGOSHAKER-SS",
]

REQUIRED_SAP_COLUMNS = [
    "Ship Date", "Sales Order/STO", "Material Number",
    "Material Description", "Quantity", "Single Side", "Double Side",
]

st.title("📦 Facturación Semanal YETI")
st.caption(
    "Sube el reporte de SAP y la app hace el resto: agrupar, clasificar, "
    "consolidar en las 10 categorías y generar los 3 archivos para PLEX SSE."
)

# ---------------------------------------------------------------------------
# Estado inicial
# ---------------------------------------------------------------------------
if "cross_ref" not in st.session_state:
    st.session_state.cross_ref = load_cross_reference()

if "processed" not in st.session_state:
    st.session_state.processed = False

precios = load_precios()

# ---------------------------------------------------------------------------
# Paso 1 — Datos de entrada
# ---------------------------------------------------------------------------
st.header("1. Datos de la semana")

col1, col2 = st.columns(2)
with col1:
    sap_file = st.file_uploader(
        "Reporte de SAP (Excel o CSV)", type=["xlsx", "xls", "csv"]
    )
with col2:
    po_no = st.text_input(
        "PO No (ej. Week30_2026_SSE)", placeholder="Week30_2026_SSE"
    )

due_date = date.today().strftime("%d/%m/%Y")
st.info(f"Due Date se genera automático con la fecha de hoy: **{due_date}**")

if st.button("Procesar semana", type="primary", disabled=sap_file is None):
    st.session_state.processed = True

if not st.session_state.processed or sap_file is None:
    st.stop()

# ---------------------------------------------------------------------------
# Paso 2 — Leer y agrupar el reporte de SAP
# ---------------------------------------------------------------------------
try:
    if sap_file.name.lower().endswith(".csv"):
        sap_df = pd.read_csv(sap_file)
    else:
        sap_df = pd.read_excel(sap_file)
except Exception as e:
    st.error(f"No pude leer el archivo: {e}")
    st.stop()

missing_cols = [c for c in REQUIRED_SAP_COLUMNS if c not in sap_df.columns]
if missing_cols:
    st.error(
        "Al archivo le faltan estas columnas requeridas: "
        + ", ".join(missing_cols)
    )
    st.stop()

def _clean_material_number(x) -> str:
    """SAP a veces exporta Material Number como número (float), lo que deja
    un '.0' pegado al convertir a texto (21071507690.0). Lo limpiamos para
    que siempre coincida con lo guardado en el Cross Reference."""
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


# Algunos exports de SAP/Excel arrastran una fila extra de "Gran Total" al
# final (residuo de una pivot table), con Material Number vacío pero
# cantidades reales. Si no se filtra ANTES de convertir a texto, ese vacío
# se vuelve el texto "nan" y se cuenta como si fuera un material más,
# duplicando el total. Se elimina aquí, antes de cualquier otra cosa.
filas_sin_material = sap_df["Material Number"].isna().sum()
if filas_sin_material:
    st.warning(
        f"Se ignoraron {filas_sin_material} fila(s) sin Material Number "
        "(probablemente una fila de 'Gran Total' que quedó pegada al "
        "exportar el archivo). Verifica que no debieran tener datos válidos."
    )
    sap_df = sap_df[sap_df["Material Number"].notna()].copy()

sap_df["Material Number"] = sap_df["Material Number"].apply(_clean_material_number)

# Se agrupa SOLO por Material Number (igual que la pivot table original de
# SAP) — nunca por Material Number + Descripción. Si el mismo Material
# Number aparece con más de una descripción (pasa con algunos materiales
# reales), las cantidades se SUMAN todas; solo se usa la primera
# descripción encontrada como referencia visual, nunca se descarta cantidad.
grouped = (
    sap_df.groupby("Material Number", as_index=False)
    .agg(
        **{"Material Description": ("Material Description", "first")},
        Quantity=("Quantity", "sum"),
        Single_Side=("Single Side", "sum"),
        Double_Side=("Double Side", "sum"),
    )
)

dup_check = (
    sap_df.groupby("Material Number")["Material Description"].nunique()
)
materiales_con_varias_desc = dup_check[dup_check > 1]
if not materiales_con_varias_desc.empty:
    st.warning(
        f"{len(materiales_con_varias_desc)} Material Number aparecen con más "
        "de una descripción en el reporte. Se sumaron todas sus cantidades "
        "igual; se usó la primera descripción encontrada solo para "
        "clasificar (revisa el detalle por SKU si quieres confirmar que la "
        "forma/línea sea la correcta para todos los casos)."
    )

# ---------------------------------------------------------------------------
# Paso 3 — Clasificar contra el Cross Reference (o regla automática)
# ---------------------------------------------------------------------------
cross_ref = st.session_state.cross_ref  # DataFrame: material_number, descripcion, forma, linea, fuente, fecha_agregado
cross_ref_map = cross_ref.set_index("material_number")[["forma", "linea"]].to_dict("index")

rows = []
nuevos = []
for _, r in grouped.iterrows():
    mat = r["Material Number"]
    desc = r["Material Description"]
    if mat in cross_ref_map:
        forma = cross_ref_map[mat]["forma"]
        linea = cross_ref_map[mat]["linea"]
        origen = "conocido"
    else:
        forma, linea = clasificar_forma_linea(desc)
        origen = "nuevo"
        nuevos.append(
            {
                "material_number": mat,
                "descripcion": desc,
                "forma": forma,
                "linea": linea,
            }
        )
    rows.append(
        {
            "Material Number": mat,
            "Descripción": desc,
            "Qty Single Side": r["Single_Side"],
            "Qty Double Side": r["Double_Side"],
            "Forma": forma,
            "Línea": linea,
            "Origen": origen,
        }
    )

detalle_df = pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# Paso 4 — Revisar materiales nuevos antes de consolidar
# ---------------------------------------------------------------------------
if nuevos:
    st.header("2. Revisa los materiales nuevos detectados")
    st.write(
        f"Se detectaron **{len(nuevos)}** materiales que no estaban en el "
        "Cross Reference. La app les asignó una clasificación automática "
        "según la regla (Bucket/Shaker/Regular + SS/DC). Corrige lo que "
        "no aplique antes de continuar."
    )

    edited_nuevos = st.data_editor(
        pd.DataFrame(nuevos),
        column_config={
            "material_number": st.column_config.TextColumn("Material Number", disabled=True),
            "descripcion": st.column_config.TextColumn("Descripción", disabled=True),
            "forma": st.column_config.SelectboxColumn(
                "Forma", options=["REGULAR", "SHAKER", "BUCKET"]
            ),
            "linea": st.column_config.SelectboxColumn("Línea", options=["DC", "SS"]),
        },
        hide_index=True,
        use_container_width=True,
        key="editor_nuevos",
    )

    if st.button("✅ Aprobar y guardar estos materiales en el Cross Reference"):
        new_entries = edited_nuevos.copy()
        new_entries["fuente"] = "auto_aprobado"
        new_entries["fecha_agregado"] = date.today().isoformat()
        updated_cross_ref = pd.concat(
            [cross_ref, new_entries[cross_ref.columns]], ignore_index=True
        )
        save_cross_reference(updated_cross_ref)
        st.session_state.cross_ref = updated_cross_ref

        # Re-aplicar la clasificación aprobada al detalle
        approved_map = edited_nuevos.set_index("material_number")[["forma", "linea"]].to_dict("index")
        for i, row in detalle_df.iterrows():
            mat = row["Material Number"]
            if mat in approved_map:
                detalle_df.at[i, "Forma"] = approved_map[mat]["forma"]
                detalle_df.at[i, "Línea"] = approved_map[mat]["linea"]
                detalle_df.at[i, "Origen"] = "nuevo (aprobado)"

        st.success("Materiales guardados. Ya quedan disponibles para la próxima semana.")
else:
    st.success("Todos los materiales de esta semana ya estaban en el Cross Reference. ✅")

# ---------------------------------------------------------------------------
# Paso 5 — Calcular PT final por fila y consolidar en las 10 categorías
# ---------------------------------------------------------------------------
detalle_df["PT Single (-1)"] = detalle_df.apply(
    lambda r: pt_final(r["Forma"], r["Línea"], es_doble=False), axis=1
)
detalle_df["PT Double (-2)"] = detalle_df.apply(
    lambda r: pt_final(r["Forma"], r["Línea"], es_doble=True), axis=1
)

# Cada material aporta a dos categorías (single/double), salvo Bucket que
# solo aporta a una (single). Armamos una tabla larga para sumar fácil.
aportes = []
anomalias_bucket = []
for _, r in detalle_df.iterrows():
    if r["Qty Single Side"]:
        aportes.append({"PT": r["PT Single (-1)"], "Qty": r["Qty Single Side"]})
    if r["Forma"] != "BUCKET" and r["Qty Double Side"]:
        aportes.append({"PT": r["PT Double (-2)"], "Qty": r["Qty Double Side"]})
    elif r["Forma"] == "BUCKET" and r["Qty Double Side"]:
        # Bucket no tiene versión de doble logo: esta cantidad no entra a
        # ninguna de las 10 categorías. Se avisa en vez de perderla en
        # silencio (igual habría pasado con el VLOOKUP del proceso manual).
        anomalias_bucket.append((r["Material Number"], r["Descripción"], r["Qty Double Side"]))

if anomalias_bucket:
    detalle_anom = "; ".join(
        f"{mat} ({desc}): {qty} en Double Side" for mat, desc, qty in anomalias_bucket
    )
    st.warning(
        "⚠️ Algunos materiales clasificados como BUCKET tienen cantidad en "
        "'Double Side', pero Bucket no tiene versión de doble logo — esa "
        f"cantidad NO se incluyó en ninguna categoría: {detalle_anom}. "
        "Revisa si es un error de captura en SAP."
    )

aportes_df = pd.DataFrame(aportes, columns=["PT", "Qty"])
resumen = (
    aportes_df.groupby("PT", as_index=False)["Qty"].sum()
    if not aportes_df.empty
    else pd.DataFrame(columns=["PT", "Qty"])
)

# Asegurar que las 10 categorías siempre aparezcan (con 0 si no hubo)
resumen = (
    pd.DataFrame({"PT": PT_CATEGORIES})
    .merge(resumen, on="PT", how="left")
    .fillna({"Qty": 0})
)
resumen["Qty"] = resumen["Qty"].astype(int)
resumen = resumen.merge(precios, left_on="PT", right_on="pt_final", how="left")
resumen["Total $"] = (resumen["Qty"] * resumen["precio_unitario"]).round(2)
resumen = resumen.rename(columns={"precio_unitario": "Precio Unitario"})[
    ["PT", "Qty", "Precio Unitario", "Total $"]
]

# ---------------------------------------------------------------------------
# Paso 6 — Mostrar resultados
# ---------------------------------------------------------------------------
st.header("3. Resumen final (equivalente a '5.Invoice')")
st.dataframe(resumen, use_container_width=True, hide_index=True)
st.metric("Total a facturar esta semana", f"${resumen['Total $'].sum():,.2f}")

with st.expander("Ver detalle por SKU / material individual"):
    st.dataframe(
        detalle_df[
            [
                "Material Number", "Descripción", "Qty Single Side",
                "Qty Double Side", "Forma", "Línea", "Origen",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

# ---------------------------------------------------------------------------
# Paso 7 — Generar los 3 archivos para PLEX SSE
# ---------------------------------------------------------------------------
st.header("4. Archivos para subir a PLEX SSE")

if not po_no:
    st.warning("Escribe el 'PO No' arriba para poder generar los archivos.")
else:
    resumen_export = resumen[resumen["Qty"] > 0].copy()

    container_csv = build_container_csv(
        resumen_export, operation=OPERATION, location=LOCATION,
        master_unit_no=MASTER_UNIT_NO,
    )
    po_line_csv = build_po_line_csv(
        resumen_export, customer_code=CUSTOMER_CODE, po_no=po_no,
        approved_ship_to=APPROVED_SHIP_TO, terms=TERMS,
    )
    release_csv = build_release_csv(
        resumen_export, customer_code=CUSTOMER_CODE, approved_ship_to=APPROVED_SHIP_TO,
        po_no=po_no, due_date=due_date, ship_from=LOCATION,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "⬇️ Container Data Upload.csv", container_csv,
            file_name="Container_Data_Upload.csv", mime="text/csv",
        )
    with c2:
        st.download_button(
            "⬇️ PO Line Upload.csv", po_line_csv,
            file_name="PO_Line_Upload.csv", mime="text/csv",
        )
    with c3:
        st.download_button(
            "⬇️ Release Upload.csv", release_csv,
            file_name="Release_Upload.csv", mime="text/csv",
        )
