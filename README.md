# Facturación Semanal YETI

App que reemplaza el proceso manual de Excel (Data SAP → Pivot Table →
PT-Creation → MasterTable → Invoice → Container/PO Line/Release Upload).

## Qué hace

1. Subes el reporte semanal de SAP (Excel o CSV).
2. La app agrupa por Material Number y clasifica cada material contra el
   Cross Reference guardado (`data/cross_reference.csv`).
3. Si hay materiales nuevos, la app les asigna automáticamente una
   clasificación (Bucket / Shaker / Regular + SS / DC) según la
   descripción, y te deja revisarla/corregirla antes de aprobar.
4. Al aprobar, esos materiales se guardan en el Cross Reference para que
   la próxima semana ya los reconozca solo.
5. Consolida todo en las 10 categorías finales de PT (equivalente a
   "5.Invoice"), con cantidad y total en dólares.
6. Genera los 3 archivos listos para subir a PLEX SSE:
   - `Container_Data_Upload.csv`
   - `PO_Line_Upload.csv`
   - `Release_Upload.csv`

## Regla de clasificación automática (materiales nuevos)

- **Forma**: "BUCKET" en la descripción → Bucket · "COCKTAIL SHAKER" →
  Shaker · si no → Regular (1LOGO/2LOGOS)
- **Línea**: "SS" en la descripción (que no esté seguida de otra letra) →
  SS · si no → DC
- **Logo** (-1/-2): según si la cantidad viene en la columna *Single Side*
  o *Double Side* del reporte de SAP. Bucket no tiene esta distinción.

Este año no se usa YC4 — si el negocio lo retoma en el futuro, hay que
agregar esa rama a `clasificador.py`.

## Cómo desplegarla (una sola vez)

1. Crea un repositorio nuevo en GitHub (puede ser privado) y sube todo
   el contenido de esta carpeta.
2. Ve a [share.streamlit.io](https://share.streamlit.io), inicia sesión
   con tu cuenta de GitHub, y crea una nueva app apuntando a ese repo,
   con `app.py` como archivo principal.
3. (Opcional pero recomendado) Para que el Cross Reference se guarde
   *permanentemente* — no solo mientras la app esté corriendo — configura
   en **Settings → Secrets** de la app:

   ```
   GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxx"
   GITHUB_REPO  = "tu-usuario/nombre-del-repo"
   ```

   El token necesita permiso de escritura sobre el repo (scope `repo` si
   es un Personal Access Token clásico, o "Contents: Read and write" si
   es un token fine-grained). Con esto, cada vez que apruebes materiales
   nuevos, la app hace un commit directo al archivo
   `data/cross_reference.csv` en GitHub.

   Si no configuras esto, la app sigue funcionando normal durante la
   sesión, pero el contenedor se puede reiniciar y perder lo que no esté
   ya en GitHub — por eso se recomienda configurarlo desde el principio.

## Uso semanal

1. Abre la app (queda con una URL fija tipo
   `https://tu-app.streamlit.app`).
2. Sube el reporte de SAP de la semana.
3. Escribe el `PO No` de la semana (ej. `Week31_2026_SSE`).
4. Revisa y aprueba los materiales nuevos si aparecen.
5. Descarga los 3 archivos y súbelos a PLEX SSE.

## Estructura del proyecto

```
facturacion-app/
├── app.py                     → app principal (Streamlit)
├── clasificador.py            → regla de clasificación automática
├── cross_reference_store.py   → carga/guarda el Cross Reference (+ GitHub)
├── plex_templates.py          → genera los 3 CSV con columnas exactas
├── precios.py                 → carga la tabla de precios
├── data/
│   ├── cross_reference.csv    → mapeo material → forma/línea (histórico + nuevos)
│   └── precios.csv            → precio unitario por cada una de las 10 categorías
└── requirements.txt
```

## Mantenimiento

- Si cambia un precio: edita `data/precios.csv` (y súbelo a GitHub si
  quieres que quede permanente).
- Si te equivocaste al aprobar un material nuevo: edita directamente
  `data/cross_reference.csv` en GitHub (o pídeme que le agregue a la app
  una pantalla de edición del Cross Reference completo).
- Los valores fijos (Approved Ship To, Location, Terms, Master Unit No)
  están al inicio de `app.py` — cámbialos ahí si algún día cambian.
