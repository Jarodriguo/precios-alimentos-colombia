#!/usr/bin/env python3
"""
ETAPA 2 — Extracción del anexo diario SIPSA.

Convierte el Excel ancho del DANE (un bloque de columnas por mercado) a
formato largo: una fila por (fecha, ciudad, mercado, producto).

Por qué formato largo: el número de mercados encuestados cambia según el día
(11 un martes, 14 un lunes). En formato ancho eso significa columnas que
aparecen y desaparecen, y un esquema que se rompe. En formato largo, un día con
menos mercados simplemente aporta menos filas.

Uso:
    # Un día concreto
    python extraer.py --fecha 2026-09-08

    # Los últimos N días hábiles
    python extraer.py --ultimos 10

    # Un rango
    python extraer.py --desde 2026-08-01 --hasta 2026-09-08

Requisitos:
    pip install requests pandas openpyxl pyarrow
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

BASE = "https://www.dane.gov.co/files/operaciones/SIPSA"
MESES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
         7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}
MES_NUM = {v: k for k, v in MESES.items()}

DIR_CRUDO = Path("data/raw")
DIR_PROCESADO = Path("data/processed")
TABLA = DIR_PROCESADO / "precios_sipsa.parquet"

# Texto que delata una nota al pie y no un rótulo de grupo de alimentos.
MARCAS_NOTA = ("*variedad", "var%:", "var %:", "n.d.", "fuente:", "nota")

# Marcador de dato ausente que usa el DANE.
NULOS = {"n.d.", "nd", "n.d", "-", "", "s.d."}


# ---------------------------------------------------------------------------
# DESCARGA
# ---------------------------------------------------------------------------

def url_anexo(f: date) -> str:
    return f"{BASE}/anex-SIPSADiario-{f.day:02d}{MESES[f.month]}{f.year}.xlsx"


def descargar(f: date, forzar: bool = False) -> Path | None:
    """Descarga el anexo de un día. Lo crudo nunca se sobrescribe.

    Si el archivo ya está en disco, no se vuelve a pedir. Esto hace la
    extracción barata de reintentar y evita golpear el servidor del DANE
    innecesariamente.
    """
    destino = DIR_CRUDO / f"anexo_{f.isoformat()}.xlsx"
    if destino.exists() and not forzar:
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url_anexo(f), timeout=120)
    except requests.RequestException as e:
        print(f"  {f}: error de red ({e})")
        return None

    if r.status_code == 404:
        print(f"  {f}: sin publicación ({['lun','mar','mié','jue','vie','sáb','dom'][f.weekday()]})")
        return None
    if r.status_code != 200:
        print(f"  {f}: HTTP {r.status_code}")
        return None

    destino.write_bytes(r.content)
    print(f"  {f}: descargado ({len(r.content) / 1024:.0f} KB)")
    return destino


# ---------------------------------------------------------------------------
# NORMALIZACIÓN
# ---------------------------------------------------------------------------

def limpiar_texto(v) -> str:
    """Colapsa saltos de línea y espacios múltiples.

    Los encabezados traen saltos internos ('Medellín,\\nCMA') que romperían
    cualquier agrupación posterior si no se normalizan.
    """
    if pd.isna(v):
        return ""
    return re.sub(r"\s+", " ", str(v).replace("\n", " ")).strip()


def clave(texto: str) -> str:
    """Versión canónica de un texto: sin tildes, minúscula, sin espacios extra.

    Se usa para agrupar. El texto original se conserva para mostrar; esta
    versión es la que garantiza que 'Fríjol verde' y 'FRIJOL VERDE' sean
    el mismo producto.
    """
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def a_numero(v) -> float | None:
    """Convierte a float tolerando los marcadores de ausencia del DANE."""
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().lower().replace("$", "").replace(" ", "")
    if t in NULOS:
        return None
    t = t.replace(".", "").replace(",", ".") if t.count(",") == 1 and t.count(".") > 1 else t
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def partir_mercado(texto: str) -> tuple[str, str | None]:
    """Separa 'Bogotá, Corabastos' en ciudad y mercado.

    Algunas entradas no traen mercado ('Santa Marta', 'Tunja'). En ese caso
    devolvemos None en lugar de inventar un valor.
    """
    t = limpiar_texto(texto)
    if "," in t:
        ciudad, mercado = t.split(",", 1)
        return ciudad.strip(), mercado.strip() or None
    return t, None


def fecha_desde_titulo(texto: str) -> date | None:
    """Extrae la fecha de 'Martes 8 de septiembre de 2026'.

    Sirve como control de calidad: se compara contra la fecha del nombre del
    archivo. Si no coinciden, el DANE publicó el archivo equivocado.
    """
    nombres = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
               "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
               "octubre": 10, "noviembre": 11, "diciembre": 12}
    t = clave(limpiar_texto(texto))
    m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", t)
    if not m:
        return None
    dia, mes_txt, anio = m.groups()
    if mes_txt not in nombres:
        return None
    return date(int(anio), nombres[mes_txt], int(dia))


# ---------------------------------------------------------------------------
# PARSEO
# ---------------------------------------------------------------------------

def parsear(ruta: Path, fecha_archivo: date) -> pd.DataFrame:
    """Convierte un anexo diario a formato largo.

    Estructura observada del archivo:
        fila 0        vacía
        fila 1        fecha en texto
        fila 2        ciudad + mercado, solo en columnas impares (celdas combinadas)
        fila 3        subencabezado: 'Precio' / 'Var %'
        fila 4+       alterna rótulos de grupo y filas de producto
        últimas filas notas al pie
    """
    crudo = pd.read_excel(ruta, sheet_name=0, header=None, engine="openpyxl")

    # --- Control de calidad: la fecha del archivo contra la fecha interna ---
    fecha_interna = None
    for i in range(min(4, len(crudo))):
        fecha_interna = fecha_desde_titulo(crudo.iloc[i, 0])
        if fecha_interna:
            break
    if fecha_interna and fecha_interna != fecha_archivo:
        print(f"  AVISO {fecha_archivo}: el archivo dice ser del {fecha_interna}")

    # --- Localizar la fila de mercados y la de subencabezados ---
    fila_mercados = None
    for i in range(min(8, len(crudo))):
        celdas = [limpiar_texto(v) for v in crudo.iloc[i]]
        if sum(1 for c in celdas if "," in c or c in ("Santa Marta", "Tunja")) >= 3:
            fila_mercados = i
            break
    if fila_mercados is None:
        raise ValueError(f"{ruta.name}: no se encontró la fila de mercados")

    fila_sub = fila_mercados + 1

    # --- Mapear cada columna a su mercado ---
    # Las celdas combinadas dejan el nombre solo en la primera columna del par,
    # así que arrastramos el último valor visto hacia la derecha.
    columnas: dict[int, tuple[str, str | None, str]] = {}
    actual: tuple[str, str | None] | None = None
    for col in range(1, crudo.shape[1]):
        etiqueta = limpiar_texto(crudo.iloc[fila_mercados, col])
        if etiqueta:
            actual = partir_mercado(etiqueta)
        sub = clave(limpiar_texto(crudo.iloc[fila_sub, col]))
        if actual and sub:
            tipo = "precio" if "precio" in sub else "variacion" if "var" in sub else None
            if tipo:
                columnas[col] = (actual[0], actual[1], tipo)

    if not columnas:
        raise ValueError(f"{ruta.name}: no se mapeó ninguna columna de mercado")

    # --- Separar filas de datos, rótulos de grupo y notas al pie ---
    cols_datos = list(columnas)
    primera = fila_sub + 1

    tiene_datos = crudo.iloc[primera:, cols_datos].notna().any(axis=1)
    if not tiene_datos.any():
        raise ValueError(f"{ruta.name}: no hay filas con datos")
    ultima_con_datos = tiene_datos[tiene_datos].index[-1]

    registros: list[dict] = []
    grupo_actual: str | None = None

    for i in range(primera, ultima_con_datos + 1):
        etiqueta = limpiar_texto(crudo.iloc[i, 0])
        if not etiqueta:
            continue

        hay_valores = crudo.iloc[i, cols_datos].notna().any()

        # Fila con texto y sin valores = rótulo de grupo (o nota, si ya
        # pasamos la última fila con datos, cosa que este bucle evita).
        if not hay_valores:
            if not clave(etiqueta).startswith(MARCAS_NOTA):
                grupo_actual = etiqueta
            continue

        # El asterisco significa 'variedad predominante en el mercado'.
        predominante = etiqueta.endswith("*")
        producto = etiqueta.rstrip("*").strip()

        # Agrupamos las columnas del mismo mercado para armar una sola fila.
        por_mercado: dict[tuple[str, str | None], dict] = {}
        for col, (ciudad, mercado, tipo) in columnas.items():
            por_mercado.setdefault((ciudad, mercado), {})[tipo] = crudo.iloc[i, col]

        for (ciudad, mercado), valores in por_mercado.items():
            precio = a_numero(valores.get("precio"))
            variacion = a_numero(valores.get("variacion"))

            # Si no hay ni precio ni variación, esa plaza no reportó ese
            # producto. No se guarda una fila vacía.
            if precio is None and variacion is None:
                continue

            registros.append({
                "fecha": fecha_archivo,
                "ciudad": ciudad,
                "mercado": mercado,
                "grupo_alimento": grupo_actual,
                "producto": producto,
                "producto_clave": clave(producto),
                "variedad_predominante": predominante,
                "precio_kg": precio,
                "variacion": variacion,
                "archivo_origen": ruta.name,
                "extraido_en": datetime.now().isoformat(timespec="seconds"),
            })

    df = pd.DataFrame(registros)
    print(f"  {fecha_archivo}: {len(df):,} filas, "
          f"{df['producto'].nunique()} productos, "
          f"{len(por_mercado)} mercados")
    return df


# ---------------------------------------------------------------------------
# CARGA IDEMPOTENTE
# ---------------------------------------------------------------------------

LLAVE = ["fecha", "ciudad", "mercado", "producto_clave"]


def guardar(nuevo: pd.DataFrame) -> None:
    """Inserta o reemplaza por llave natural.

    Esta es la propiedad que define el pipeline: reprocesar un día ya cargado
    no duplica nada. Se borran sus filas y se vuelven a insertar. Correr el
    proceso una vez o cien veces produce el mismo resultado.
    """
    if nuevo.empty:
        print("Nada que guardar.")
        return

    DIR_PROCESADO.mkdir(parents=True, exist_ok=True)

    if TABLA.exists():
        viejo = pd.read_parquet(TABLA)
        fechas_nuevas = set(nuevo["fecha"])
        antes = len(viejo)
        viejo = viejo[~viejo["fecha"].isin(fechas_nuevas)]
        reemplazadas = antes - len(viejo)
        if reemplazadas:
            print(f"Reemplazando {reemplazadas:,} filas de fechas ya cargadas.")
        combinado = pd.concat([viejo, nuevo], ignore_index=True)
    else:
        combinado = nuevo

    # Red de seguridad por si la llave se colara duplicada dentro de un mismo día.
    dups = combinado.duplicated(subset=LLAVE).sum()
    if dups:
        print(f"AVISO: {dups} duplicados por llave natural; se conserva el último.")
        combinado = combinado.drop_duplicates(subset=LLAVE, keep="last")

    combinado = combinado.sort_values(["fecha", "ciudad", "producto"]).reset_index(drop=True)
    combinado.to_parquet(TABLA, index=False)

    print(f"\nTabla: {len(combinado):,} filas totales")
    print(f"Rango: {combinado['fecha'].min()} → {combinado['fecha'].max()}")
    print(f"Guardada en {TABLA}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def dias_habiles(n: int) -> list[date]:
    """Últimos n días de lunes a viernes, sin contar hoy."""
    salida, f = [], date.today() - timedelta(days=1)
    while len(salida) < n:
        if f.weekday() < 5:
            salida.append(f)
        f -= timedelta(days=1)
    return sorted(salida)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fecha", help="Un día concreto (YYYY-MM-DD)")
    p.add_argument("--ultimos", type=int, help="Últimos N días hábiles")
    p.add_argument("--desde")
    p.add_argument("--hasta")
    a = p.parse_args()

    if a.fecha:
        fechas = [date.fromisoformat(a.fecha)]
    elif a.ultimos:
        fechas = dias_habiles(a.ultimos)
    elif a.desde and a.hasta:
        ini, fin = date.fromisoformat(a.desde), date.fromisoformat(a.hasta)
        fechas = [ini + timedelta(days=i) for i in range((fin - ini).days + 1)]
        fechas = [f for f in fechas if f.weekday() < 5]
    else:
        fechas = dias_habiles(5)

    print(f"Procesando {len(fechas)} fecha(s)\n")

    trozos, fallos = [], []
    for f in fechas:
        ruta = descargar(f)
        if not ruta:
            continue
        try:
            trozos.append(parsear(ruta, f))
        except Exception as e:
            print(f"  {f}: ERROR al parsear -> {e}")
            fallos.append((f, str(e)))

    if fallos:
        print(f"\n{len(fallos)} archivo(s) fallaron:")
        for f, e in fallos:
            print(f"  {f}: {e}")

    if trozos:
        guardar(pd.concat(trozos, ignore_index=True))
    else:
        print("\nNo se extrajo ninguna fila.")


if __name__ == "__main__":
    main()