"""
Genera los 3 CSV para subir a PLEX SSE, respetando EXACTAMENTE las columnas
de las plantillas originales (mismo orden, mismos nombres). Los campos que
no se usan se dejan vacíos, igual que en las plantillas.
"""

import pandas as pd

CONTAINER_COLUMNS = [
    "Supplier Serial Number", "Part", "Rev", "Operation", "Material", "Heat",
    "Location", "Status", "Defect Type", "Container Type", "Quantity",
    "Tare Weight", "Gross Weight", "Net Weight", "From Container", "Active",
    "Note", "Lot Number", "Master Unit No", "Special Instructions",
    "Containers", "Size", "Length", "Tracking No", "Job Operation",
    "Job Number", "Shelf Date", "Cost", "Customer Code",
    "Container Mill Status", "Class", "Mill Coil No", "OSPCoil No",
    "Mill Order No", "Mill Item No", "Theoretical Weight", "Mill Weight",
    "Heat Code", "Received Heat No", "Release Number", "Shipper Number",
    "SCACCode", "Thickness", "Width", "EDIKey", "Actual Quantity", "Job No",
    "Supplier No", "Rescale Flag", "Original Scale Weight", "Original Length",
    "Proof", "Proof Volume", "Manufacturer Part No",
    "Manufacturer Part Revision", "Accounting Job No",
]

PO_LINE_COLUMNS = [
    "Customer Code", "PO No", "PO Status", "PO Type", "PO Date", "Terms",
    "FOB", "Freight Terms", "Approved Ship To", "Approved Ship From",
    "Customer Part No", "Customer Part Revision", "New Shipper Per Schedule",
    "New Shipper Per Release No", "Container Type", "Master Unit Type",
    "Standard Pack Quantity", "Transportation Adjustment", "Part No",
    "Part Revision", "Note", "Master Price", "Default Carrier",
    "PO Category", "INCO Terms", "Assign All Ship Tos", "Named Place Type",
    "Named Place Address", "Negotiated Place",
]

RELEASE_COLUMNS = [
    "Customer Code", "Ship To", "PO No", "Customer Part No",
    "Customer Part Revision", "Part No", "Part Revision", "Release No",
    "Quantity", "Due Date", "Ship From", "EDI Kanban No", "EDI Dock Code",
    "EDI Line Code", "EDI Line 11", "EDI Line 12", "EDI Line 13",
    "EDI Line 14", "EDI Line 15", "EDI Line 16", "EDI Line 17",
    "EDI Material Handling Code", "EDI Reference No", "EDI Document",
    "EDI R Code", "EDI Intermediate Consignee", "EDI Load Sequence No",
    "EDI Lot No", "EDI Batch", "EDI Order No", "EDI Dealer No",
    "Release Type", "Vehicle ID", "Rotation", "Usepoint", "Auto Create PO",
    "Supplier Code", "Drop Ship PO No", "Production Start Date",
    "Schedule Type",
]


def _customer_part_no(pt: str) -> str:
    """PT-1LOGO-SS -> 1LOGO-SS"""
    return pt[3:] if pt.startswith("PT-") else pt


def build_container_csv(resumen: pd.DataFrame, *, operation: str, location: str,
                         master_unit_no: str) -> str:
    rows = []
    for _, r in resumen.iterrows():
        row = {c: "" for c in CONTAINER_COLUMNS}
        row["Part"] = r["PT"]
        row["Operation"] = operation
        row["Location"] = location
        row["Status"] = "Ok"
        row["Quantity"] = int(r["Qty"])
        row["Active"] = 1
        row["Master Unit No"] = master_unit_no
        rows.append(row)
    return pd.DataFrame(rows, columns=CONTAINER_COLUMNS).to_csv(index=False)


def build_po_line_csv(resumen: pd.DataFrame, *, customer_code: str, po_no: str,
                       approved_ship_to: str, terms: str) -> str:
    rows = []
    for _, r in resumen.iterrows():
        row = {c: "" for c in PO_LINE_COLUMNS}
        row["Customer Code"] = customer_code
        row["PO No"] = po_no
        row["PO Status"] = "Abierta"
        row["PO Type"] = "Cantidad Cerrada"
        row["Terms"] = terms
        row["Freight Terms"] = "Default"
        row["Approved Ship To"] = approved_ship_to
        row["Customer Part No"] = _customer_part_no(r["PT"])
        row["Part No"] = r["PT"]
        rows.append(row)
    return pd.DataFrame(rows, columns=PO_LINE_COLUMNS).to_csv(index=False)


def build_release_csv(resumen: pd.DataFrame, *, customer_code: str,
                       approved_ship_to: str, po_no: str, due_date: str,
                       ship_from: str) -> str:
    rows = []
    for _, r in resumen.iterrows():
        row = {c: "" for c in RELEASE_COLUMNS}
        row["Customer Code"] = customer_code
        row["Ship To"] = approved_ship_to
        row["PO No"] = po_no
        row["Customer Part No"] = _customer_part_no(r["PT"])
        row["Part No"] = r["PT"]
        row["Quantity"] = int(r["Qty"])
        row["Due Date"] = due_date
        row["Ship From"] = ship_from
        rows.append(row)
    return pd.DataFrame(rows, columns=RELEASE_COLUMNS).to_csv(index=False)
