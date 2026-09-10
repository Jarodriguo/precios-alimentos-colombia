#!/usr/bin/env python3
# %% [markdown]
# # EDA — Precios mayoristas SIPSA
# ## Parte 1: Integridad estructural y cobertura
#
# Este archivo usa celdas `# %%`. VS Code y Jupyter lo abren como notebook,
# pero se guarda como `.py`, así que git puede versionarlo y mostrar diferencias
# legibles. Un `.ipynb` guarda las salidas dentro del archivo y cada ejecución
# produce un diff ilegible.
#
# **Regla de esta etapa: no se arregla nada.** Se mide, se documenta, se decide
# después. Si limpias mientras exploras, pierdes el registro de qué había.

# %%
from pathlib import Path

import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)

TABLA = Path("data/processed/precios_sipsa.parquet")
df = pd.read_parquet(TABLA)
df["fecha"] = pd.to_datetime(df["fecha"])

print(f"Filas: {len(df):,}")
print(f"Rango: {df['fecha'].min().date()} → {df['fecha'].max().date()}")
print(f"Días con datos: {df['fecha'].nunique()}")
print(f"\nColumnas y tipos:\n{df.dtypes}")

# %% [markdown]
# ---
# # NIVEL 1 — INTEGRIDAD ESTRUCTURAL
#
# Antes de analizar nada, hay que verificar que la tabla es lo que creemos.

# %% [markdown]
# ## 1.1 ¿La llave natural es realmente única?
#
# Declaramos que `(fecha, ciudad, mercado, producto_clave)` identifica una
# fila. Si eso es falso, toda la idempotencia del pipeline es una ilusión y
# cualquier `groupby` posterior está mal.
#
# Esto se verifica, no se asume.

# %%
LLAVE = ["fecha", "ciudad", "mercado", "producto_clave"]

dups = df.duplicated(subset=LLAVE, keep=False)
print(f"Filas que violan la llave: {dups.sum():,}")

if dups.sum():
    print("\nEjemplos:")
    print(df[dups].sort_values(LLAVE).head(20)[LLAVE + ["precio_kg", "variacion"]])
    print("\nHay que decidir: ¿promediar, tomar el último, o descartar?")
else:
    print("Llave única confirmada. La idempotencia se sostiene.")

# %% [markdown]
# ## 1.2 Nulos: dónde están y qué significan
#
# Un nulo no es un error por defecto. Aquí hay al menos tres significados
# distintos y confundirlos lleva a conclusiones equivocadas:
#
# - `mercado` nulo → la plaza no tiene nombre propio (Santa Marta, Tunja).
#   Es información válida, no un dato faltante.
# - `variacion` nula con `precio_kg` presente → sí se cotizó, pero no había
#   día anterior con qué comparar.
# - `precio_kg` nulo → no debería existir; el extractor omite esas filas.

# %%
nulos = pd.DataFrame({
    "nulos": df.isna().sum(),
    "pct": (df.isna().mean() * 100).round(2),
})
print(nulos[nulos["nulos"] > 0])

print("\n--- Desglose del caso interesante ---")
sin_precio = df["precio_kg"].isna()
sin_var = df["variacion"].isna()
print(f"Con precio y sin variación : {(~sin_precio & sin_var).sum():,}")
print(f"Sin precio y con variación : {(sin_precio & ~sin_var).sum():,}")
print(f"Sin precio ni variación    : {(sin_precio & sin_var).sum():,}")
print("\nEl segundo caso sería raro: una variación sin precio base.")

# %% [markdown]
# ## 1.3 Rangos: ¿los valores son físicamente posibles?
#
# Un precio de 0 pesos por kilo o de 900.000 pesos no es un precio, es un
# error. Aquí no filtramos: solo medimos cuánto pesa el problema.

# %%
print("Precio por kilo (pesos):")
print(df["precio_kg"].describe(percentiles=[.01, .25, .5, .75, .99]).round(0))

print(f"\nPrecios <= 0     : {(df['precio_kg'] <= 0).sum():,}")
print(f"Precios < 200    : {(df['precio_kg'] < 200).sum():,}")
print(f"Precios > 50.000 : {(df['precio_kg'] > 50_000).sum():,}")

extremos = df.nlargest(10, "precio_kg")[["fecha", "ciudad", "producto", "precio_kg"]]
print(f"\nLos 10 precios más altos:\n{extremos.to_string(index=False)}")

extremos_bajos = df.nsmallest(10, "precio_kg")[["fecha", "ciudad", "producto", "precio_kg"]]
print(f"\nLos 10 más bajos:\n{extremos_bajos.to_string(index=False)}")

# %% [markdown]
# ## 1.4 ¿En qué escala está `variacion`?
#
# El Excel la rotula `Var %` y trae valores como `0.06` y `-0.12`. Ambigüedad
# real: ¿es 6% expresado como proporción, o 0.06%?
#
# La forma de resolverlo no es adivinar sino **reconstruir el cálculo**. La
# nota al pie dice que compara contra el promedio del día de mercado anterior
# **de la misma plaza**. Si nuestra reconstrucción coincide con la columna
# publicada, entendimos el campo. Si no, hay algo que no sabemos.

# %%
print(df["variacion"].describe(percentiles=[.01, .05, .95, .99]).round(4))
print(f"\n|variacion| > 1  : {(df['variacion'].abs() > 1).sum():,}")
print(f"|variacion| > 0.5: {(df['variacion'].abs() > 0.5).sum():,}")
print("\nSi casi todo cae entre -1 y 1, es proporción (0.06 = 6%).")
print("Si se concentra entre -100 y 100, ya viene en puntos porcentuales.")

# Reconstrucción: variación contra la observación anterior del mismo par
serie = df.dropna(subset=["precio_kg"]).sort_values("fecha").copy()
serie["precio_previo"] = serie.groupby(
    ["ciudad", "mercado", "producto_clave"], dropna=False
)["precio_kg"].shift(1)
serie["var_calculada"] = (
    serie["precio_kg"] / serie["precio_previo"] - 1
)

comparable = serie.dropna(subset=["variacion", "var_calculada"])
comparable = comparable[np.isfinite(comparable["var_calculada"])]
diferencia = (comparable["var_calculada"] - comparable["variacion"]).abs()

print(f"\nPares comparables: {len(comparable):,}")
print(f"Coinciden dentro de 0.005: {(diferencia < 0.005).mean() * 100:.1f}%")
print(f"Diferencia mediana       : {diferencia.median():.4f}")
print("\nSi la coincidencia es alta, entendimos el campo y la escala.")
print("Si es baja, el DANE promedia algo distinto a lo que asumimos.")

# %% [markdown]
# ## 1.5 Vocabularios: ¿los nombres son consistentes?
#
# Este es el punto donde más proyectos se caen sin que nadie lo note. Si
# "Medellín, CMA" aparece un día como "Medellín, C.M.A", pandas los trata como
# dos mercados distintos y tus series de tiempo se parten en dos sin avisar.

# %%
print("MERCADOS:")
mercados = (
    df.groupby(["ciudad", "mercado"], dropna=False)
      .agg(observaciones=("precio_kg", "size"),
           primer_dia=("fecha", "min"),
           ultimo_dia=("fecha", "max"),
           dias=("fecha", "nunique"))
      .sort_values("observaciones", ascending=False)
)
print(mercados.to_string())

print(f"\nCombinaciones ciudad-mercado distintas: {len(mercados)}")
print("\nCiudades con más de un mercado (¿son reales o variantes de escritura?):")
por_ciudad = df.groupby("ciudad")["mercado"].nunique().sort_values(ascending=False)
print(por_ciudad[por_ciudad > 1])

# %%
print("PRODUCTOS:")
productos = (
    df.groupby("producto_clave")
      .agg(nombre=("producto", "first"),
           variantes=("producto", "nunique"),
           observaciones=("precio_kg", "size"),
           grupos=("grupo_alimento", "nunique"))
      .sort_values("observaciones", ascending=False)
)
print(productos.to_string())

print("\nProductos cuyo nombre se escribe de más de una forma:")
print(productos[productos["variantes"] > 1])

print("\nProductos clasificados en más de un grupo de alimento:")
inconsistentes = productos[productos["grupos"] > 1]
if inconsistentes.empty:
    print("Ninguno. La clasificación es estable.")
else:
    print(inconsistentes)
    for pc in inconsistentes.index:
        print(f"\n  {pc}: {df[df['producto_clave'] == pc]['grupo_alimento'].unique()}")

# %% [markdown]
# ---
# # NIVEL 2 — COBERTURA
#
# Aquí vive el problema central de estos datos. No es que estén mal escritos,
# es que **no todos los mercados se encuestan todos los días**, y eso
# contamina cualquier agregado calculado ingenuamente.

# %% [markdown]
# ## 2.1 Calendario: qué días faltan y si son festivos

# %%
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

calendario = pd.date_range(df["fecha"].min(), df["fecha"].max(), freq="D")
habiles = [d for d in calendario if d.weekday() < 5]
con_datos = set(df["fecha"].unique())
faltantes = [d for d in habiles if d not in con_datos]

print(f"Días hábiles en el rango : {len(habiles)}")
print(f"Con datos                : {len(habiles) - len(faltantes)}")
print(f"Sin datos                : {len(faltantes)}\n")

for d in faltantes:
    print(f"  {d.date()}  {DIAS[d.weekday()]}")

print("\nContrasta esta lista con el calendario de festivos de Colombia.")
print("Cada fecha que NO sea festivo es un dato perdido, no una ausencia legítima.")

# %% [markdown]
# ## 2.2 La rotación de mercados por día de la semana
#
# Esta es la estructura oculta del dataset. Cuantificarla es el paso que
# habilita todo el análisis posterior.

# %%
por_dia = df.groupby("fecha").agg(
    mercados=("mercado", lambda s: len(s.index)),
)
plazas_por_fecha = (
    df.groupby("fecha")[["ciudad", "mercado"]]
      .apply(lambda g: g.drop_duplicates().shape[0])
      .rename("n_plazas")
      .reset_index()
)
plazas_por_fecha["dia_semana"] = plazas_por_fecha["fecha"].dt.weekday.map(
    lambda i: DIAS[i]
)

resumen = (
    plazas_por_fecha.groupby("dia_semana")["n_plazas"]
    .agg(["count", "min", "median", "max", "std"])
    .reindex(DIAS[:5])
)
print("Plazas encuestadas por día de la semana:")
print(resumen.round(2).to_string())

print("\nSi la desviación es baja, la rotación es determinista.")
print("Los días con desviación alta merecen investigación.")

# %%
# ¿Qué plaza aparece en qué días? Esta tabla es el corazón del hallazgo.
presencia = (
    df.assign(dia=df["fecha"].dt.weekday.map(lambda i: DIAS[i]),
              plaza=df["ciudad"] + " / " + df["mercado"].fillna("—"))
      .groupby(["plaza", "dia"])["fecha"]
      .nunique()
      .unstack(fill_value=0)
      .reindex(columns=DIAS[:5])
)
print("Días distintos en que cada plaza reportó, por día de la semana:")
print(presencia.to_string())

print("\nLas filas con ceros muestran plazas que solo se visitan ciertos días.")
print("Ese es el patrón que invalida el promedio nacional diario.")

# %% [markdown]
# ## 2.3 La matriz producto × plaza
#
# 36 productos × N plazas serían miles de combinaciones posibles, pero muchas
# no existen: no toda plaza vende todo producto. Hay que distinguir
# "no se vende aquí" de "no se midió ese día".

# %%
combos = df.groupby(["ciudad", "mercado", "producto_clave"], dropna=False).agg(
    obs=("precio_kg", "size"),
    dias=("fecha", "nunique"),
)
dias_totales = df["fecha"].nunique()
combos["cobertura_pct"] = (combos["dias"] / dias_totales * 100).round(1)

print(f"Combinaciones plaza-producto observadas: {len(combos):,}")
print(f"Posibles (plazas × productos): "
      f"{df[['ciudad','mercado']].drop_duplicates().shape[0] * df['producto_clave'].nunique():,}")

print("\nDistribución de la cobertura:")
print(combos["cobertura_pct"].describe(percentiles=[.1, .25, .5, .75, .9]).round(1))

print("\nCombinaciones con menos del 10% de cobertura (series inservibles):")
print(f"{(combos['cobertura_pct'] < 10).sum():,} de {len(combos):,}")

print("\nLas 15 series más completas:")
print(combos.nlargest(15, "dias").to_string())

# %% [markdown]
# ## 2.4 Continuidad: ¿las series tienen huecos?
#
# Una serie con 80% de cobertura puede ser 80% continuo o pueden ser dos
# bloques con un mes muerto en medio. Para análisis temporal son cosas muy
# distintas.

# %%
def huecos_de(g: pd.DataFrame) -> pd.Series:
    fechas = g["fecha"].sort_values().unique()
    if len(fechas) < 2:
        return pd.Series({"hueco_max_dias": np.nan, "huecos_7d": 0})
    saltos = pd.Series(fechas).diff().dt.days.dropna()
    return pd.Series({
        "hueco_max_dias": saltos.max(),
        "huecos_7d": (saltos > 7).sum(),
    })


top = combos.nlargest(20, "dias").index
muestra = df.set_index(["ciudad", "mercado", "producto_clave"]).loc[top].reset_index()
continuidad = (
    muestra.groupby(["ciudad", "mercado", "producto_clave"], dropna=False)
           .apply(huecos_de, include_groups=False)
)
print("Continuidad de las 20 series más completas:")
print(continuidad.to_string())
print("\nUn hueco máximo de 3-4 días es normal (fin de semana).")
print("Huecos mayores a 7 días son interrupciones que hay que explicar.")

# %% [markdown]
# ---
# ## Cierre de la parte 1
#
# Lo que sigue (parte 2): distribuciones de precio, detección de atípicos,
# correlación entre plazas, y la demostración de por qué el promedio nacional
# diario está mal calculado.
#
# Anota aquí lo que encontraste antes de seguir. El EDA que no se escribe
# se olvida.