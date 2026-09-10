#!/usr/bin/env python3
"""
ETAPA 5 — Orquestador del pipeline.

Ejecuta la cadena completa: descarga -> parseo -> carga -> limpieza ->
controles de calidad. Pensado para correr sin supervisión humana.

Tres diferencias con ejecutar los scripts a mano:

1. **Logging en vez de print.** Con marca de tiempo y nivel de severidad, para
   poder reconstruir qué pasó semanas después.

2. **Falla en voz alta.** Si algo no cuadra, termina con código de salida
   distinto de cero y GitHub Actions marca la ejecución en rojo. Un pipeline
   que produce datos malos en silencio es peor que uno que no corre.

3. **Distingue ausencia legítima de fallo.** Un sábado sin publicación es
   normal y termina bien. Un martes sin publicación es una anomalía.

Códigos de salida:
    0  todo bien (incluye "no había publicación hoy, es normal")
    1  fallo: algo se rompió y hay que mirarlo
    2  advertencia: corrió pero un control de calidad no pasó

Uso:
    python pipeline.py                 # últimos 5 días hábiles (se pone al día)
    python pipeline.py --dias 15
    python pipeline.py --fecha 2026-09-08
    python pipeline.py --solo-validar
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from extraer import TABLA, descargar, guardar, parsear
from limpiar import limpiar

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

# reconfigure evita el UnicodeEncodeError en Windows cuando la salida va a un
# archivo o a un log. No depende de variables de entorno de la máquina.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("reports/pipeline.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("sipsa")

LIMPIO = Path("data/processed/precios_limpio.parquet")
METRICAS = Path("reports/metricas.json")

# Festivos colombianos observados en los datos. Se amplía cada año.
# Sirve para no alarmarse por ausencias legítimas.
FESTIVOS = {
    "2026-01-01", "2026-01-12", "2026-03-23", "2026-04-02", "2026-04-03",
    "2026-05-01", "2026-05-18", "2026-06-08", "2026-06-15", "2026-06-29",
    "2026-07-13", "2026-07-20", "2026-08-07", "2026-08-17", "2026-10-12",
    "2026-11-02", "2026-11-16", "2026-12-08", "2026-12-25",
}


class ControlFallido(Exception):
    """Un control de calidad no pasó. Detiene el pipeline a propósito."""


# ---------------------------------------------------------------------------
# CONTROLES DE CALIDAD
# ---------------------------------------------------------------------------
#
# Cada control salió de un hallazgo del EDA. Las expectativas no están
# escritas a mano: se derivan del histórico ya cargado. Así el pipeline se
# recalibra solo a medida que acumula datos, en vez de quedar amarrado a
# números que envejecen.

COLUMNAS_ESPERADAS = {
    "fecha", "ciudad", "mercado", "grupo_alimento", "producto",
    "producto_clave", "variedad_predominante", "precio_kg", "variacion",
    "archivo_origen", "extraido_en",
}

TOLERANCIA = 0.25  # cuánto puede desviarse del histórico antes de alertar


def control_esquema(nuevo: pd.DataFrame) -> list[str]:
    """El esquema no puede cambiar sin que nos enteremos."""
    faltan = COLUMNAS_ESPERADAS - set(nuevo.columns)
    sobran = set(nuevo.columns) - COLUMNAS_ESPERADAS
    problemas = []
    if faltan:
        problemas.append(f"faltan columnas: {sorted(faltan)}")
    if sobran:
        problemas.append(f"columnas nuevas: {sorted(sobran)}")
    return problemas


def control_volumen(nuevo: pd.DataFrame, historico: pd.DataFrame) -> list[str]:
    """El volumen del día debe parecerse al de otros días de la misma semana.

    Comparar contra el mismo día de la semana, y no contra el promedio
    general, es lo que hace útil este control: el EDA mostró que el viernes
    trae 16 plazas y el martes 11.
    """
    problemas = []
    if historico.empty:
        return problemas

    hist = historico.copy()
    hist["dow"] = pd.to_datetime(hist["fecha"]).dt.weekday

    for fecha, grupo in nuevo.groupby("fecha"):
        dow = pd.Timestamp(fecha).weekday()
        ref = hist[hist["dow"] == dow]
        if ref.empty:
            continue

        esperado = ref.groupby("fecha").size().median()
        obtenido = len(grupo)
        desvio = abs(obtenido - esperado) / esperado

        if desvio > TOLERANCIA:
            problemas.append(
                f"{pd.Timestamp(fecha).date()}: {obtenido} filas, "
                f"se esperaban ~{esperado:.0f} para ese día de la semana "
                f"({desvio:.0%} de desvío)"
            )
    return problemas


def control_vocabulario(nuevo: pd.DataFrame, historico: pd.DataFrame) -> list[str]:
    """Detecta plazas, productos o grupos que nunca habíamos visto.

    Un nombre nuevo no es necesariamente un error, pero sí algo que un humano
    debe revisar antes de que contamine las series.
    """
    problemas = []
    if historico.empty:
        return problemas

    for columna in ("ciudad", "mercado", "producto_clave", "grupo_alimento"):
        conocidos = set(historico[columna].dropna())
        nuevos = set(nuevo[columna].dropna()) - conocidos
        if nuevos:
            problemas.append(f"{columna}: valores nuevos {sorted(nuevos)[:6]}")
    return problemas


def control_rango(nuevo: pd.DataFrame) -> list[str]:
    """Precios físicamente imposibles."""
    problemas = []
    malos = nuevo[(nuevo["precio_kg"] < 100) | (nuevo["precio_kg"] > 100_000)]
    if len(malos):
        problemas.append(
            f"{len(malos)} precios fuera de rango "
            f"(min {malos['precio_kg'].min():.0f}, max {malos['precio_kg'].max():.0f})"
        )
    if nuevo["precio_kg"].isna().any():
        problemas.append(f"{nuevo['precio_kg'].isna().sum()} precios nulos")
    return problemas


def control_duplicados(nuevo: pd.DataFrame) -> list[str]:
    """La llave natural debe seguir siendo única."""
    llave = ["fecha", "ciudad", "mercado", "producto_clave"]
    dups = nuevo.duplicated(subset=llave).sum()
    return [f"{dups} filas violan la llave natural"] if dups else []


def validar(nuevo: pd.DataFrame, historico: pd.DataFrame) -> tuple[bool, list[str]]:
    """Corre todos los controles. Devuelve (todo_bien, lista_de_problemas)."""
    controles = [
        ("esquema", lambda: control_esquema(nuevo)),
        ("volumen", lambda: control_volumen(nuevo, historico)),
        ("vocabulario", lambda: control_vocabulario(nuevo, historico)),
        ("rango", lambda: control_rango(nuevo)),
        ("duplicados", lambda: control_duplicados(nuevo)),
    ]

    todos: list[str] = []
    for nombre, fn in controles:
        problemas = fn()
        if problemas:
            for p in problemas:
                log.warning("control '%s': %s", nombre, p)
            todos.extend(f"{nombre}: {p}" for p in problemas)
        else:
            log.info("control '%s': OK", nombre)

    return (not todos), todos


# ---------------------------------------------------------------------------
# EJECUCIÓN
# ---------------------------------------------------------------------------

def dias_habiles(n: int) -> list[date]:
    salida, f = [], date.today()
    while len(salida) < n:
        if f.weekday() < 5:
            salida.append(f)
        f -= timedelta(days=1)
    return sorted(salida)


def ausencia_esperada(f: date) -> bool:
    """¿Es normal que no haya publicación este día?"""
    return f.weekday() >= 5 or f.isoformat() in FESTIVOS


def ejecutar(fechas: list[date]) -> int:
    log.info("Pipeline SIPSA — procesando %d fecha(s)", len(fechas))

    historico = pd.read_parquet(TABLA) if TABLA.exists() else pd.DataFrame()
    if not historico.empty:
        log.info("Histórico: %s filas hasta %s",
                 f"{len(historico):,}", pd.to_datetime(historico['fecha']).max().date())

    trozos, sin_datos, fallos = [], [], []

    for f in fechas:
        ruta = descargar(f)
        if ruta is None:
            if ausencia_esperada(f):
                log.info("%s: sin publicación (esperado)", f)
            else:
                log.warning("%s: sin publicación en día hábil no festivo", f)
                sin_datos.append(f)
            continue
        try:
            trozos.append(parsear(ruta, f))
        except Exception as e:
            log.error("%s: fallo al parsear -> %s", f, e)
            fallos.append((f, str(e)))

    if fallos:
        log.error("%d archivo(s) no se pudieron parsear", len(fallos))
        return 1

    if not trozos:
        log.info("No había nada nuevo que procesar. Terminando sin cambios.")
        return 0

    nuevo = pd.concat(trozos, ignore_index=True)
    log.info("Extraídas %s filas de %d día(s)", f"{len(nuevo):,}", len(trozos))

    # --- Controles ANTES de guardar -------------------------------------
    ok, problemas = validar(nuevo, historico)

    guardar(nuevo)

    limpio, registro = limpiar(pd.read_parquet(TABLA))
    LIMPIO.parent.mkdir(parents=True, exist_ok=True)
    limpio.to_parquet(LIMPIO, index=False)
    log.info("Tabla limpia: %s filas, %d plazas, %.1f%% confiables",
             f"{len(limpio):,}", limpio["plaza"].nunique(),
             limpio["confiable"].mean() * 100)

    Path("reports").mkdir(exist_ok=True)
    Path("reports/limpieza.md").write_text(registro.markdown(), encoding="utf-8")

    metricas = {
        "ejecutado_en": datetime.now().isoformat(timespec="seconds"),
        "fechas_procesadas": [str(f) for f in fechas],
        "filas_nuevas": len(nuevo),
        "filas_totales": len(limpio),
        "plazas": int(limpio["plaza"].nunique()),
        "productos": int(limpio["producto_clave"].nunique()),
        "ultima_fecha": str(pd.to_datetime(limpio["fecha"]).max().date()),
        "pct_confiables": round(limpio["confiable"].mean() * 100, 2),
        "controles_ok": ok,
        "problemas": problemas,
        "dias_habiles_sin_datos": [str(f) for f in sin_datos],
    }
    METRICAS.write_text(json.dumps(metricas, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    log.info("Métricas en %s", METRICAS)

    if not ok:
        log.warning("Terminó con %d control(es) en alerta", len(problemas))
        return 2

    log.info("Pipeline completado sin novedades")
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dias", type=int, default=5,
                   help="Últimos N días hábiles (permite ponerse al día)")
    p.add_argument("--fecha", help="Una fecha concreta YYYY-MM-DD")
    p.add_argument("--solo-validar", action="store_true",
                   help="Revalida el histórico sin descargar nada")
    a = p.parse_args()

    Path("reports").mkdir(exist_ok=True)

    if a.solo_validar:
        df = pd.read_parquet(TABLA)
        ok, _ = validar(df, df)
        sys.exit(0 if ok else 2)

    fechas = [date.fromisoformat(a.fecha)] if a.fecha else dias_habiles(a.dias)
    sys.exit(ejecutar(fechas))


if __name__ == "__main__":
    main()