#!/usr/bin/env python3
# %% [markdown]
# # EDA — Precios mayoristas SIPSA
# ## Parte 2: distribuciones, atípicos y el sesgo de composición
#
# La parte 1 dejó tres cosas por resolver:
#
# 1. `Ibagué/La 21` y `Ibagué/Plaza La 21` parecen la misma plaza.
# 2. Los grupos de alimento tienen 7 etiquetas para 3 categorías reales.
# 3. Hay precios exactos repetidos que huelen a arrastre de dato.
#
# Y sobre todo, falta demostrar el hallazgo central: que el promedio nacional
# diario está mal calculado.
#
# **Sigue vigente la regla: aquí no se arregla nada.** Se mide y se documenta.
# La limpieza es la etapa siguiente.

# %%
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 40)
plt.rcParams["figure.figsize"] = (11, 5)
plt.rcParams["figure.dpi"] = 110

FIGURAS = Path("reports/figuras")
FIGURAS.mkdir(parents=True, exist_ok=True)

df = pd.read_parquet("data/processed/precios_sipsa.parquet")
df["fecha"] = pd.to_datetime(df["fecha"])
df["plaza"] = df["ciudad"] + " / " + df["mercado"].fillna("—")
df["dia_semana"] = df["fecha"].dt.weekday

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes"]
print(f"{len(df):,} filas | {df['fecha'].nunique()} días | {df['plaza'].nunique()} plazas")

# %% [markdown]
# ---
# ## 2.5 Confirmar la hipótesis de la plaza duplicada
#
# La parte 1 mostró patrones complementarios. Aquí lo verificamos de tres
# formas independientes. Una coincidencia puede ser casualidad; tres, no.

# %%
def comparar_plazas(a: str, b: str) -> None:
    pa, pb = df[df["plaza"] == a], df[df["plaza"] == b]
    fa, fb = set(pa["fecha"]), set(pb["fecha"])

    print(f"\n{'=' * 64}\n{a}  vs  {b}\n{'=' * 64}")
    print(f"Días en común: {len(fa & fb)}")
    print("  (si es 0, nunca coexisten -> candidatas a ser la misma)")

    # Prueba 2: ¿venden el mismo catálogo de productos?
    prod_a, prod_b = set(pa["producto_clave"]), set(pb["producto_clave"])
    solape = len(prod_a & prod_b) / len(prod_a | prod_b) if (prod_a | prod_b) else 0
    print(f"Solape de catálogo de productos: {solape:.0%}")
    print("  (plazas distintas rara vez venden exactamente lo mismo)")

    # Prueba 3: ¿los niveles de precio son compatibles?
    med_a = pa.groupby("producto_clave")["precio_kg"].median()
    med_b = pb.groupby("producto_clave")["precio_kg"].median()
    comunes = med_a.index.intersection(med_b.index)
    if len(comunes):
        razon = (med_a[comunes] / med_b[comunes])
        print(f"Razón de precios medianos: {razon.median():.3f} "
              f"(rango {razon.min():.2f}–{razon.max():.2f})")
        print("  (cerca de 1.0 = mismos niveles = probablemente la misma plaza)")


comparar_plazas("Ibagué / La 21", "Ibagué / Plaza La 21")
comparar_plazas("Pereira / La 41-Impala", "Pereira / La 41")
# Control negativo: dos plazas que sabemos distintas
comparar_plazas("Pereira / Mercasa", "Pereira / La 41-Impala")

# %% [markdown]
# ## 2.6 ¿Cuándo cambió el vocabulario de grupos?
#
# Hipótesis: la redacción de los grupos cambió el mismo día que saltó el
# tamaño del archivo (28 de mayo). Fecharlo convierte una molestia en un
# hallazgo documentado.

# %%
cambios = (
    df.groupby("grupo_alimento")["fecha"]
      .agg(primera="min", ultima="max", dias="nunique")
      .sort_values("primera")
)
print(cambios.to_string())

print("\nSi las etiquetas se turnan sin solaparse, hubo un cambio de formato")
print("en una fecha concreta. Si conviven, el DANE es inconsistente día a día.")

# Línea de tiempo de qué etiqueta se usó cada día
linea = df.groupby(["fecha", "grupo_alimento"]).size().unstack(fill_value=0)
linea = (linea > 0).astype(int)
print(f"\nDías en que cada etiqueta aparece:\n{linea.sum().to_string()}")
print(f"\nDías con más de una etiqueta del mismo grupo: "
      f"{(linea.sum(axis=1) > 3).sum()}")

# %% [markdown]
# ---
# # NIVEL 3 — DISTRIBUCIONES
#
# Ahora sí miramos cómo se comportan los precios por sí solos.

# %% [markdown]
# ## 3.1 La distribución global engaña
#
# Un histograma de todos los precios juntos mezcla papa con granadilla. No
# dice nada útil, pero sirve para ver la asimetría típica de datos de precio.

# %%
fig, ejes = plt.subplots(1, 2)
ejes[0].hist(df["precio_kg"].dropna(), bins=60, color="#4C72B0")
ejes[0].set_title("Precio por kilo (escala lineal)")
ejes[0].set_xlabel("pesos/kg")

ejes[1].hist(np.log10(df["precio_kg"].dropna()), bins=60, color="#DD8452")
ejes[1].set_title("Precio por kilo (log10)")
ejes[1].set_xlabel("log10(pesos/kg)")
plt.tight_layout()
plt.savefig(FIGURAS / "01_distribucion_precios.png", bbox_inches="tight")
plt.show()

print("Asimetría:", round(df["precio_kg"].skew(), 2))
print("En log10:", round(np.log10(df['precio_kg'].dropna()).skew(), 2))
print("\nLos precios casi siempre son log-normales: no pueden bajar de cero")
print("pero sí subir mucho. Por eso conviene razonar en cambios porcentuales")
print("y no en diferencias absolutas de pesos.")

# %% [markdown]
# ## 3.2 Precios pegajosos: ¿dato real o arrastre?
#
# En la parte 1 vimos aguacate a exactamente 14.000 tres días distintos.
# Si un encuestador no consigue cotización y repite la del día anterior, el
# dato se ve normal pero es inventado. Se detecta buscando repeticiones
# exactas consecutivas.

# %%
s = df.dropna(subset=["precio_kg"]).sort_values("fecha").copy()
s["previo"] = s.groupby(["plaza", "producto_clave"])["precio_kg"].shift(1)
s["repetido"] = (s["precio_kg"] == s["previo"])

print(f"Observaciones con precio idéntico al anterior: "
      f"{s['repetido'].sum():,} ({s['repetido'].mean():.1%})")

print("\nPlazas con más repetición (sospechosas de arrastrar el dato):")
por_plaza = (
    s.groupby("plaza")
     .agg(obs=("repetido", "size"), repetidos=("repetido", "sum"))
     .assign(pct=lambda d: (d["repetidos"] / d["obs"] * 100).round(1))
     .sort_values("pct", ascending=False)
)
print(por_plaza.to_string())

# Rachas: cuántas veces se repite seguido el mismo valor
s["cambio"] = s.groupby(["plaza", "producto_clave"])["precio_kg"].transform(
    lambda x: (x != x.shift()).cumsum()
)
rachas = s.groupby(["plaza", "producto_clave", "cambio"]).size()
print(f"\nRacha más larga de precio idéntico: {rachas.max()} observaciones")
print("Rachas de 5 o más:")
largas = rachas[rachas >= 5].sort_values(ascending=False)
print(f"{len(largas)} casos. Los 10 mayores:")
print(largas.head(10).to_string())

# %% [markdown]
# ## 3.3 Atípicos por serie, no globales
#
# Un precio de 14.000 es atípico para la papa y normal para el aguacate. Los
# atípicos se buscan **dentro de cada par plaza-producto**, no en la columna
# entera.
#
# Usamos desviación absoluta mediana (MAD) en vez de desviación estándar,
# porque la desviación estándar la infla el mismo atípico que queremos
# encontrar.

# %%
def z_robusto(x: pd.Series) -> pd.Series:
    mediana = x.median()
    mad = (x - mediana).abs().median()
    if mad == 0:
        return pd.Series(0.0, index=x.index)
    return 0.6745 * (x - mediana) / mad


df["z"] = df.groupby(["plaza", "producto_clave"])["precio_kg"].transform(z_robusto)
atipicos = df[df["z"].abs() > 5]

print(f"Atípicos (|z robusto| > 5): {len(atipicos):,} de {len(df):,} "
      f"({len(atipicos) / len(df):.2%})")
print("\nLos 20 más extremos:")
cols = ["fecha", "plaza", "producto", "precio_kg", "variacion", "z"]
print(atipicos.reindex(atipicos["z"].abs().sort_values(ascending=False).index)
      .head(20)[cols].to_string(index=False))

print("\nRevisa si se concentran en alguna plaza, producto o fecha.")
print("Un atípico aislado es un dato raro; muchos juntos son un problema.")

# %% [markdown]
# ---
# # NIVEL 4 — EL SESGO DE COMPOSICIÓN
#
# Esta es la sección central del proyecto.

# %% [markdown]
# ## 4.1 El gráfico que casi todo el mundo haría
#
# Agrupar por fecha, promediar el precio, graficar. Parece razonable.

# %%
ingenuo = df.groupby("fecha")["precio_kg"].mean()

fig, eje = plt.subplots()
eje.plot(ingenuo.index, ingenuo.values, lw=1, color="#C44E52")
eje.set_title("Precio promedio nacional por día — CÁLCULO INGENUO")
eje.set_ylabel("pesos/kg")
plt.tight_layout()
plt.savefig(FIGURAS / "02_promedio_ingenuo.png", bbox_inches="tight")
plt.show()

print("Promedio por día de la semana (cálculo ingenuo):")
comp = df.groupby("dia_semana")["precio_kg"].agg(["mean", "count"])
comp.index = [DIAS[i] for i in comp.index]
print(comp.round(0).to_string())
print("\n¿La comida cuesta distinto según el día de la semana?")
print("Sería absurdo. Veamos de dónde sale la diferencia.")

# %% [markdown]
# ## 4.2 De dónde sale el falso patrón
#
# Cada plaza tiene su propio nivel de precios. Si unas plazas solo se
# encuestan ciertos días, esos días el promedio se corre.

# %%
nivel = (
    df.groupby("plaza")
      .agg(precio_mediano=("precio_kg", "median"), obs=("precio_kg", "size"))
      .sort_values("precio_mediano", ascending=False)
)
print("Nivel de precios por plaza:")
print(nivel.round(0).to_string())
print(f"\nLa plaza más cara mediana: {nivel['precio_mediano'].max():,.0f}")
print(f"La más barata            : {nivel['precio_mediano'].min():,.0f}")
print(f"Diferencia               : "
      f"{nivel['precio_mediano'].max() / nivel['precio_mediano'].min():.2f}x")

print("\nAhora: qué plazas entran cada día de la semana")
presencia = (
    df.groupby(["dia_semana", "plaza"])["fecha"].nunique()
      .unstack(fill_value=0).T
)
presencia.columns = [DIAS[i] for i in presencia.columns]
presencia["nivel"] = nivel["precio_mediano"]
print(presencia.sort_values("nivel", ascending=False).to_string())

print("\nSi las plazas caras se concentran en unos días, el promedio de esos")
print("días sube sin que ningún precio haya cambiado. Eso es el sesgo.")

# %% [markdown]
# ## 4.3 El cálculo correcto: panel fijo
#
# Solución: definir un conjunto de pares plaza-producto presentes casi todos
# los días, y calcular el índice siempre sobre ese mismo conjunto.
#
# Es el mismo principio del IPC y de los índices bursátiles. Se sacrifica
# cobertura para ganar comparabilidad, y ese intercambio se documenta.

# %%
UMBRAL = 0.95
dias_totales = df["fecha"].nunique()

cobertura = (
    df.groupby(["plaza", "producto_clave"])["fecha"].nunique() / dias_totales
)
panel = cobertura[cobertura >= UMBRAL].index
print(f"Pares con cobertura >= {UMBRAL:.0%}: {len(panel):,}")
print(f"Plazas en el panel: {len({p for p, _ in panel})}")
print(f"Productos en el panel: {len({q for _, q in panel})}")

df_panel = df.set_index(["plaza", "producto_clave"]).loc[panel].reset_index()
print(f"Filas en el panel: {len(df_panel):,} "
      f"({len(df_panel) / len(df):.1%} del total)")

# Índice base 100 en el primer día, sobre el panel fijo
base = (
    df_panel[df_panel["fecha"] == df_panel["fecha"].min()]
    .set_index(["plaza", "producto_clave"])["precio_kg"]
)
df_panel["relativo"] = df_panel.apply(
    lambda r: r["precio_kg"] / base.get((r["plaza"], r["producto_clave"]), np.nan),
    axis=1,
)
indice = df_panel.groupby("fecha")["relativo"].mean() * 100

fig, eje = plt.subplots()
eje.plot(ingenuo.index, ingenuo / ingenuo.iloc[0] * 100,
         lw=1, alpha=0.6, color="#C44E52", label="Ingenuo (muestra variable)")
eje.plot(indice.index, indice.values, lw=1.8, color="#4C72B0",
         label=f"Panel fijo ({len(panel)} series)")
eje.axhline(100, color="gray", ls=":", lw=0.8)
eje.set_title("Índice de precios base 100 — comparación de métodos")
eje.set_ylabel("índice")
eje.legend()
plt.tight_layout()
plt.savefig(FIGURAS / "03_ingenuo_vs_panel.png", bbox_inches="tight")
plt.show()

print("\nVariación por día de la semana, con panel fijo:")
comp2 = df_panel.assign(ds=df_panel["fecha"].dt.weekday).groupby("ds")["relativo"].mean()
comp2.index = [DIAS[i] for i in comp2.index]
print((comp2 * 100).round(2).to_string())
print("\nSi el patrón semanal desapareció, era artefacto de muestra.")
print("Si persiste, hay estacionalidad semanal real y hay que explicarla.")

# %% [markdown]
# ## 4.4 ¿Cuánto vale la diferencia?
#
# Cuantificar el error del método ingenuo es lo que convierte una observación
# metodológica en un resultado.

# %%
comparacion = pd.DataFrame({
    "ingenuo": ingenuo / ingenuo.iloc[0] * 100,
    "panel": indice,
}).dropna()
comparacion["brecha"] = comparacion["ingenuo"] - comparacion["panel"]

print(comparacion["brecha"].describe().round(2).to_string())
print(f"\nBrecha máxima: {comparacion['brecha'].abs().max():.1f} puntos")
print(f"Días donde los métodos difieren en más de 2 puntos: "
      f"{(comparacion['brecha'].abs() > 2).sum()} de {len(comparacion)}")

print("\nSi la brecha llega a varios puntos, el método ingenuo puede mostrar")
print("una 'inflación' que no existe. Ese es el titular del proyecto.")

# %% [markdown]
# ---
# ## Cierre
#
# Con esto termina el diagnóstico. Lo que sigue es la etapa 4: convertir cada
# hallazgo en una regla de limpieza con su prueba automática.
#
# Antes de avanzar, escribe en un archivo aparte las conclusiones. Un EDA que
# no se resume se pierde.