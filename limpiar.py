#!/usr/bin/env python3
"""
ETAPA 4 — Limpieza.

Cada regla de este módulo salió de un hallazgo medido en el EDA. Ninguna se
aplicó "por si acaso".

Principio de diseño: **marcar, no borrar.**

La tentación es filtrar las filas problemáticas y quedarse con datos bonitos.
El problema es que quien use la tabla después no sabe qué se fue ni por qué,
y no puede revisar tu criterio. En vez de eso, cada problema agrega una
columna booleana. El analista decide si filtra o no, y el dashboard puede
mostrar cuánto pesa cada problema.

Las únicas transformaciones destructivas son las que corrigen errores
inequívocos de la fuente: dos nombres para una misma plaza, y siete etiquetas
para tres grupos.

Uso:
    python limpiar.py
    python limpiar.py --reporte reports/limpieza.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ENTRADA = Path("data/processed/precios_sipsa.parquet")
SALIDA = Path("data/processed/precios_limpio.parquet")


# ---------------------------------------------------------------------------
# REGLAS DERIVADAS DEL EDA
# ---------------------------------------------------------------------------

# R1. Plazas con dos nombres.
# Evidencia (EDA parte 1 y 2): patrones de aparición perfectamente
# complementarios, catálogo de productos idéntico y niveles de precio
# equivalentes. Tres pruebas independientes.
PLAZAS_CANONICAS = {
    ("Ibagué", "Plaza La 21"): ("Ibagué", "La 21"),
    ("Pereira", "La 41"): ("Pereira", "La 41-Impala"),
}

# R2. Grupos de alimento: 7 etiquetas para 3 categorías reales.
# Evidencia: los 36 productos aparecen en 2 o 3 grupos distintos. El DANE
# cambió la redacción durante el periodo.
GRUPOS_CANONICOS = {
    "verduras y hortalizas": "Verduras y hortalizas",
    "hortalizas y verduras": "Verduras y hortalizas",
    "frutas frescas": "Frutas frescas",
    "frutas": "Frutas frescas",
    "tubérculos, raíces y plátanos": "Tubérculos, raíces y plátanos",
    "tubérculos y plátanos": "Tubérculos, raíces y plátanos",
    "tubérculos, plátanos": "Tubérculos, raíces y plátanos",
}

# R3. Rango físicamente plausible para precio mayorista de alimentos frescos.
# Evidencia: el EDA observó [500, 14.000] sin ningún valor absurdo. Los
# límites se ponen holgados a propósito: el objetivo es atrapar fallos
# futuros de la fuente, no recortar los datos actuales.
PRECIO_MIN, PRECIO_MAX = 100.0, 100_000.0

# R4. Umbral de racha para considerar un precio "arrastrado".
# Evidencia: el EDA encontró rachas de valores idénticos. Tres o más días
# consecutivos con el mismo precio exacto en un producto fresco es
# sospechoso de que el encuestador repitió la cotización anterior.
RACHA_SOSPECHOSA = 3

# R5. Umbral de atípico. z robusto (MAD) calculado dentro de cada serie
# plaza-producto, no sobre la columna global.
Z_ATIPICO = 5.0


# ---------------------------------------------------------------------------
# REGISTRO DE IMPACTO
# ---------------------------------------------------------------------------

class Registro:
    """Anota cuántas filas toca cada regla.

    Sin esto, la limpieza es una caja negra. Con esto, el README y el
    dashboard pueden decir exactamente qué se corrigió y cuánto pesaba.
    """

    def __init__(self, total: int) -> None:
        self.total = total
        self.entradas: list[dict] = []

    def anotar(self, regla: str, descripcion: str, filas: int,
               accion: str) -> None:
        self.entradas.append({
            "regla": regla,
            "descripcion": descripcion,
            "filas": filas,
            "pct": round(filas / self.total * 100, 3),
            "accion": accion,
        })

    def tabla(self) -> pd.DataFrame:
        return pd.DataFrame(self.entradas)

    def markdown(self) -> str:
        t = self.tabla()
        lineas = [
            "# Reglas de limpieza aplicadas\n",
            f"Filas de entrada: **{self.total:,}**\n",
            "| Regla | Qué corrige | Filas | % | Acción |",
            "|---|---|---:|---:|---|",
        ]
        for _, f in t.iterrows():
            lineas.append(
                f"| {f['regla']} | {f['descripcion']} | {f['filas']:,} | "
                f"{f['pct']}% | {f['accion']} |"
            )
        lineas.append(
            "\n> Las reglas marcadas como *marca* no eliminan filas: agregan "
            "una columna booleana para que el análisis decida."
        )
        return "\n".join(lineas)


# ---------------------------------------------------------------------------
# REGLAS
# ---------------------------------------------------------------------------

def r1_unificar_plazas(df: pd.DataFrame, reg: Registro) -> pd.DataFrame:
    """Corrige los casos de una plaza con dos nombres."""
    afectadas = 0
    for (ciudad, viejo), (_, nuevo) in PLAZAS_CANONICAS.items():
        mask = (df["ciudad"] == ciudad) & (df["mercado"] == viejo)
        afectadas += int(mask.sum())
        df.loc[mask, "mercado"] = nuevo

    reg.anotar("R1", "Plazas con dos nombres (Ibagué La 21, Pereira La 41)",
               afectadas, "corrige")
    return df


def r2_unificar_grupos(df: pd.DataFrame, reg: Registro) -> pd.DataFrame:
    """Normaliza las 7 etiquetas de grupo a las 3 categorías reales."""
    original = df["grupo_alimento"].copy()
    df["grupo_alimento"] = (
        df["grupo_alimento"].str.strip().str.lower().map(GRUPOS_CANONICOS)
        .fillna(df["grupo_alimento"])
    )
    cambiadas = int((original != df["grupo_alimento"]).sum())

    sin_mapear = set(
        original[df["grupo_alimento"] == original].str.strip().str.lower()
    ) - set(GRUPOS_CANONICOS)
    if sin_mapear:
        print(f"  AVISO R2: etiquetas de grupo no previstas: {sin_mapear}")

    reg.anotar("R2", "Etiquetas de grupo inconsistentes (7 -> 3)",
               cambiadas, "corrige")
    return df


def r3_marcar_fuera_de_rango(df: pd.DataFrame, reg: Registro) -> pd.DataFrame:
    """Marca precios físicamente implausibles.

    No borra: si algún día el DANE publica un precio absurdo, queremos verlo
    en el reporte de calidad, no que desaparezca en silencio.
    """
    df["fuera_de_rango"] = (
        (df["precio_kg"] < PRECIO_MIN) | (df["precio_kg"] > PRECIO_MAX)
    )
    reg.anotar("R3", f"Precio fuera de [{PRECIO_MIN:,.0f}, {PRECIO_MAX:,.0f}]",
               int(df["fuera_de_rango"].sum()), "marca")
    return df


def r4_marcar_arrastrados(df: pd.DataFrame, reg: Registro) -> pd.DataFrame:
    """Marca precios repetidos exactos en rachas largas.

    Un precio idéntico dos días seguidos es normal. Tres o más en un producto
    fresco sugiere que el encuestador repitió la cotización anterior en vez
    de tomarla. El dato se ve válido y no lo es.
    """
    df = df.sort_values(["ciudad", "mercado", "producto_clave", "fecha"])
    llave = ["ciudad", "mercado", "producto_clave"]

    # Identificador de bloque: aumenta cada vez que el precio cambia
    bloque = df.groupby(llave, dropna=False)["precio_kg"].transform(
        lambda x: (x != x.shift()).cumsum()
    )
    largo = df.groupby(llave + [bloque.rename("b")], dropna=False)[
        "precio_kg"
    ].transform("size")

    df["racha_precio"] = largo.astype(int)
    # Solo las repeticiones son sospechosas, no la medición original
    posicion = df.groupby(llave + [bloque.rename("b")], dropna=False).cumcount()
    df["precio_arrastrado"] = (df["racha_precio"] >= RACHA_SOSPECHOSA) & (posicion > 0)

    reg.anotar("R4", f"Precio idéntico {RACHA_SOSPECHOSA}+ días seguidos",
               int(df["precio_arrastrado"].sum()), "marca")
    return df


def r5_marcar_atipicos(df: pd.DataFrame, reg: Registro) -> pd.DataFrame:
    """Marca atípicos dentro de cada serie plaza-producto.

    Se usa MAD y no desviación estándar: la desviación estándar se infla con
    el mismo valor extremo que se quiere detectar.
    """
    def z_robusto(x: pd.Series) -> pd.Series:
        mediana = x.median()
        mad = (x - mediana).abs().median()
        if mad == 0 or np.isnan(mad):
            return pd.Series(0.0, index=x.index)
        return 0.6745 * (x - mediana) / mad

    df["z_robusto"] = df.groupby(
        ["ciudad", "mercado", "producto_clave"], dropna=False
    )["precio_kg"].transform(z_robusto)
    df["atipico"] = df["z_robusto"].abs() > Z_ATIPICO

    reg.anotar("R5", f"Atípico dentro de su serie (|z MAD| > {Z_ATIPICO})",
               int(df["atipico"].sum()), "marca")
    return df


def r6_derivar_calendario(df: pd.DataFrame, reg: Registro) -> pd.DataFrame:
    """Agrega columnas de calendario y marca los días posteriores a un puente.

    El EDA mostró que 8 de las 12 ausencias fueron lunes festivos, así que
    muchos martes son 'martes después de puente largo'. Marcarlo permite
    controlar ese efecto al analizar el ciclo semanal.
    """
    dias = ["lunes", "martes", "miércoles", "jueves", "viernes",
            "sábado", "domingo"]
    df["dia_semana"] = df["fecha"].dt.weekday
    df["nombre_dia"] = df["dia_semana"].map(lambda i: dias[i])
    df["semana_iso"] = df["fecha"].dt.isocalendar().week.astype(int)
    df["mes"] = df["fecha"].dt.to_period("M").astype(str)

    fechas = pd.Index(sorted(df["fecha"].unique()))
    anterior = pd.Series(fechas, index=fechas).shift(1)
    brecha = (pd.Series(fechas, index=fechas) - anterior).dt.days
    df["dias_desde_publicacion_previa"] = df["fecha"].map(brecha)
    df["post_puente"] = df["dias_desde_publicacion_previa"] > 3

    reg.anotar("R6", "Día posterior a un puente (>3 días sin publicación)",
               int(df["post_puente"].sum()), "marca")
    return df


def r7_marcar_panel(df: pd.DataFrame, reg: Registro,
                    umbral: float = 0.95) -> pd.DataFrame:
    """Marca las series que forman el panel fijo de referencia.

    Precalcularlo aquí evita que cada análisis lo redefina a su manera y
    obtenga números distintos.
    """
    dias_totales = df["fecha"].nunique()
    cobertura = (
        df.groupby(["ciudad", "mercado", "producto_clave"], dropna=False)["fecha"]
        .transform("nunique") / dias_totales
    )
    df["cobertura_serie"] = cobertura.round(4)
    df["en_panel"] = cobertura >= umbral

    reg.anotar("R7", f"Serie con cobertura >= {umbral:.0%} (panel fijo)",
               int(df["en_panel"].sum()), "marca")
    return df


# ---------------------------------------------------------------------------
# ORQUESTACIÓN
# ---------------------------------------------------------------------------

def limpiar(df: pd.DataFrame) -> tuple[pd.DataFrame, Registro]:
    reg = Registro(len(df))
    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])

    for regla in (r1_unificar_plazas, r2_unificar_grupos,
                  r3_marcar_fuera_de_rango, r4_marcar_arrastrados,
                  r5_marcar_atipicos, r6_derivar_calendario, r7_marcar_panel):
        df = regla(df, reg)

    # Etiqueta agregada: fila apta para análisis sin reservas.
    df["confiable"] = ~(df["fuera_de_rango"] | df["atipico"] |
                        df["precio_arrastrado"])

    df["plaza"] = df["ciudad"] + " / " + df["mercado"].fillna("—")
    return df.sort_values(["fecha", "ciudad", "producto"]).reset_index(drop=True), reg


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--entrada", type=Path, default=ENTRADA)
    p.add_argument("--salida", type=Path, default=SALIDA)
    p.add_argument("--reporte", type=Path, default=Path("reports/limpieza.md"))
    a = p.parse_args()

    df = pd.read_parquet(a.entrada)
    print(f"Entrada: {len(df):,} filas\n")

    limpio, reg = limpiar(df)

    print(reg.tabla().to_string(index=False))

    print(f"\nSalida: {len(limpio):,} filas (no se eliminó ninguna)")
    print(f"Plazas: {limpio['plaza'].nunique()} "
          f"(antes {(df['ciudad'] + ' / ' + df['mercado'].fillna('—')).nunique()})")
    print(f"Grupos: {limpio['grupo_alimento'].nunique()} "
          f"(antes {df['grupo_alimento'].nunique()})")
    print(f"Filas confiables: {limpio['confiable'].sum():,} "
          f"({limpio['confiable'].mean():.1%})")

    a.salida.parent.mkdir(parents=True, exist_ok=True)
    limpio.to_parquet(a.salida, index=False)
    print(f"\nGuardado en {a.salida}")

    a.reporte.parent.mkdir(parents=True, exist_ok=True)
    a.reporte.write_text(reg.markdown(), encoding="utf-8")
    print(f"Reporte en {a.reporte}")


if __name__ == "__main__":
    main()