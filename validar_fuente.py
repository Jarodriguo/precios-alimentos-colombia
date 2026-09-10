#!/usr/bin/env python3
"""
ETAPA 1 — Validación de la fuente SIPSA (DANE).

Antes de escribir un pipeline hay que responder cuatro preguntas:
  1. ¿La URL es realmente predecible a partir de la fecha?
  2. ¿Con qué frecuencia publican y qué días faltan?
  3. ¿Qué estructura tiene el Excel por dentro?
  4. ¿Los datos cambian de un día a otro, o se repiten?

Este script no construye nada. Solo diagnostica. Si algo de esto falla,
cambiamos de fuente antes de haber invertido tiempo.

Requisitos:
    pip install requests pandas openpyxl

Uso:
    python validar_fuente.py
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

BASE = "https://www.dane.gov.co/files/operaciones/SIPSA"

# El DANE abrevia los meses en español, en minúscula y a tres letras.
MESES = {
    1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic",
}

CRUDO = Path("data/raw")
DIAS_A_REVISAR = 14


def url_anexo(f: date) -> str:
    """Construye la URL del anexo diario a partir de una fecha.

    Patrón observado: anex-SIPSADiario-08sep2026.xlsx
    El día va con cero a la izquierda.
    """
    return f"{BASE}/anex-SIPSADiario-{f.day:02d}{MESES[f.month]}{f.year}.xlsx"


def existe(url: str) -> tuple[bool, int, str]:
    """Consulta si el archivo existe sin descargarlo entero.

    HEAD pide solo las cabeceras. Si el servidor no lo soporta, caemos a un
    GET con streaming y cortamos apenas llega la respuesta.
    """
    try:
        r = requests.head(url, timeout=30, allow_redirects=True)
        if r.status_code == 405:  # método no permitido
            r = requests.get(url, timeout=30, stream=True)
            r.close()
        tam = int(r.headers.get("Content-Length", 0))
        tipo = r.headers.get("Content-Type", "")
        return r.status_code == 200, tam, tipo
    except requests.RequestException as e:
        return False, 0, str(e)[:60]


def descargar(url: str, destino: Path) -> Path | None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        destino.write_bytes(r.content)
        return destino
    except requests.RequestException as e:
        print(f"    fallo la descarga: {e}")
        return None


# ---------------------------------------------------------------------------
# 1. CALENDARIO DE PUBLICACIÓN
# ---------------------------------------------------------------------------

def revisar_calendario() -> list[date]:
    """Recorre los últimos N días y reporta cuáles tienen anexo publicado."""
    print("=" * 72)
    print("1. CALENDARIO DE PUBLICACIÓN")
    print("=" * 72)
    print(f"{'Fecha':<14}{'Día':<12}{'Existe':<9}{'Tamaño':>12}")
    print("-" * 72)

    disponibles: list[date] = []
    hoy = date.today()
    dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

    for i in range(1, DIAS_A_REVISAR + 1):
        f = hoy - timedelta(days=i)
        hay, tam, _ = existe(url_anexo(f))
        marca = "sí" if hay else "no"
        tamano = f"{tam / 1024:,.0f} KB" if tam else "—"
        print(f"{f.isoformat():<14}{dias_es[f.weekday()]:<12}{marca:<9}{tamano:>12}")
        if hay:
            disponibles.append(f)

    print(f"\nDisponibles: {len(disponibles)} de {DIAS_A_REVISAR} días revisados.")
    print("Si los que faltan son sábados, domingos y festivos, el patrón es")
    print("el esperado y el pipeline debe tolerarlo sin fallar.\n")
    return disponibles


# ---------------------------------------------------------------------------
# 2. ESTRUCTURA INTERNA DEL EXCEL
# ---------------------------------------------------------------------------

def inspeccionar_excel(ruta: Path) -> None:
    """Revela cómo está armado el archivo por dentro.

    Se lee con header=None a propósito: queremos ver las filas tal cual, sin
    que pandas adivine dónde está el encabezado. En archivos oficiales el
    encabezado casi nunca está en la primera fila.
    """
    print("=" * 72)
    print(f"2. ESTRUCTURA DE {ruta.name}")
    print("=" * 72)

    xl = pd.ExcelFile(ruta, engine="openpyxl")
    print(f"Hojas ({len(xl.sheet_names)}): {xl.sheet_names}\n")

    for hoja in xl.sheet_names:
        crudo = pd.read_excel(ruta, sheet_name=hoja, header=None, engine="openpyxl")
        print("-" * 72)
        print(f"Hoja '{hoja}': {crudo.shape[0]} filas × {crudo.shape[1]} columnas")
        print("-" * 72)

        print("Primeras 12 filas (sin interpretar encabezado):")
        with pd.option_context("display.max_columns", 12, "display.width", 200,
                               "display.max_colwidth", 28):
            print(crudo.head(12).to_string())

        # Heurística: la fila de encabezado suele ser la primera con muchas
        # celdas llenas de texto después de un bloque de títulos.
        llenas = crudo.notna().sum(axis=1)
        candidata = llenas.idxmax()
        print(f"\nFila con más celdas llenas: índice {candidata} "
              f"({llenas.max()} de {crudo.shape[1]}). "
              f"Probable encabezado.")
        print(f"Contenido: {crudo.iloc[candidata].dropna().tolist()[:12]}")

        print("\nÚltimas 5 filas (ojo con notas al pie mezcladas con datos):")
        with pd.option_context("display.max_columns", 8, "display.width", 200,
                               "display.max_colwidth", 40):
            print(crudo.tail(5).to_string())
        print()


# ---------------------------------------------------------------------------
# 3. ¿LOS DATOS CAMBIAN?
# ---------------------------------------------------------------------------

def comparar(a: Path, b: Path) -> None:
    """Verifica que dos días distintos traigan datos distintos.

    Si los archivos fueran idénticos, no habría nada que acumular y el
    proyecto no tendría sentido. Es la prueba que justifica la automatización.
    """
    print("=" * 72)
    print("3. ¿CAMBIAN LOS DATOS ENTRE DÍAS?")
    print("=" * 72)

    ha = hashlib.sha256(a.read_bytes()).hexdigest()[:16]
    hb = hashlib.sha256(b.read_bytes()).hexdigest()[:16]
    print(f"{a.name}: hash {ha}, {a.stat().st_size / 1024:,.0f} KB")
    print(f"{b.name}: hash {hb}, {b.stat().st_size / 1024:,.0f} KB")

    if ha == hb:
        print("\nARCHIVOS IDÉNTICOS. Bandera roja: revisar antes de seguir.")
        return

    print("\nArchivos distintos. La fuente sí cambia día a día.")

    da = pd.read_excel(a, header=None, engine="openpyxl")
    db = pd.read_excel(b, header=None, engine="openpyxl")
    print(f"\nDimensiones: {da.shape} vs {db.shape}")

    if da.shape[1] != db.shape[1]:
        print("ATENCIÓN: distinto número de columnas entre días.")
        print("El pipeline necesitará detección de cambios de esquema.")
    else:
        print("Mismo número de columnas. El esquema parece estable.")

    if da.shape[0] != db.shape[0]:
        print(f"Distinto número de filas ({abs(da.shape[0] - db.shape[0])} de "
              f"diferencia): productos o mercados que entran y salen.")


def main() -> None:
    disponibles = revisar_calendario()

    if len(disponibles) < 2:
        print("Menos de dos días disponibles. No se puede validar el cambio.")
        print("Revisa tu conexión o si el patrón de URL cambió.")
        return

    print("Descargando dos días para inspeccionar...\n")
    rutas: list[Path] = []
    for f in disponibles[:2]:
        destino = CRUDO / f"anexo_{f.isoformat()}.xlsx"
        print(f"  {f.isoformat()} -> {destino}")
        r = descargar(url_anexo(f), destino)
        if r:
            rutas.append(r)
    print()

    if not rutas:
        print("No se pudo descargar ningún archivo.")
        return

    inspeccionar_excel(rutas[0])

    if len(rutas) == 2:
        comparar(rutas[0], rutas[1])

    print("\n" + "=" * 72)
    print("VALIDACIÓN TERMINADA")
    print("=" * 72)
    print("Si el calendario tiene sentido, el Excel es legible y los días")
    print("difieren, la fuente sirve y pasamos a la Etapa 2.")


if __name__ == "__main__":
    main()