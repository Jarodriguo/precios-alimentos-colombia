#!/usr/bin/env python3
# %% [markdown]
# # EDA — Parte 4: dos cabos sueltos
#
# 1. ¿En qué fecha exacta cambió el DANE la nomenclatura de los grupos?
# 2. El 17,2% de precios repetidos, ¿es comportamiento de mercado o arrastre
#    del encuestador? ¿Afecta el índice de +7,3%?
#
# La segunda pregunta puede cambiar el número principal del proyecto, así que
# hay que responderla antes de publicarlo.

# %%
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
plt.rcParams["figure.figsize"] = (11, 5)
plt.rcParams["figure.dpi"] = 110

FIGURAS = Path("reports/figuras")
FIGURAS.mkdir(parents=True, exist_ok=True)

df = pd.read_parquet("data/processed/precios_limpio.parquet")
df["fecha"] = pd.to_datetime(df["fecha"])
print(f"{len(df):,} filas | {df['plaza'].nunique()} plazas")

# %% [markdown]
# ## 1. Fechar el cambio de formato
#
# Cargamos el crudo (sin normalizar) para ver qué etiqueta se usó cada día.

# %%
crudo = pd.read_parquet("data/processed/precios_sipsa.parquet")
crudo["fecha"] = pd.to_datetime(crudo["fecha"])

etiquetas = (
    crudo.groupby(["fecha", "grupo_alimento"]).size().unstack(fill_value=0) > 0
)
print("Primer y último día de uso de cada etiqueta:\n")
for col in etiquetas.columns:
    dias = etiquetas.index[etiquetas[col]]
    print(f"  {col:<34} {dias.min().date()} → {dias.max().date()}  "
          f"({len(dias)} días)")

# ¿Hay una fecha de corte limpia?
antiguas = [c for c in etiquetas.columns if c in
            ("Verduras y hortalizas", "Frutas frescas",
             "Tubérculos, raíces y plátanos")]
if antiguas:
    usa_antigua = etiquetas[antiguas].any(axis=1)
    cambios = usa_antigua.ne(usa_antigua.shift()).cumsum()
    print(f"\nBloques de uso continuo: {cambios.nunique()}")
    print("1 o 2 bloques = cambio único con fecha limpia.")
    print("Muchos bloques = el DANE alterna sin patrón.")

    transiciones = usa_antigua[usa_antigua.ne(usa_antigua.shift())]
    print(f"\nFechas de transición:\n{transiciones.to_string()}")

print("\nCompara con el 2026-05-28, cuando el archivo saltó de 320 a 337 KB.")

# %% [markdown]
# ## 2. ¿Dónde se concentran los precios repetidos?
#
# Si están repartidos parejo entre plazas, es comportamiento de mercado.
# Si se concentran en unas pocas, es práctica de captura de esas plazas.

# %%
por_plaza = (
    df.groupby("plaza")
      .agg(obs=("precio_arrastrado", "size"),
           arrastrados=("precio_arrastrado", "sum"))
      .assign(pct=lambda d: (d["arrastrados"] / d["obs"] * 100).round(1))
      .sort_values("pct", ascending=False)
)
print(por_plaza.to_string())

print(f"\nDispersión entre plazas: min {por_plaza['pct'].min():.1f}%, "
      f"max {por_plaza['pct'].max():.1f}%, "
      f"desv {por_plaza['pct'].std():.1f}")
print("\nUna desviación baja apunta a fenómeno de mercado.")
print("Una desviación alta apunta a práctica de captura desigual.")

# %% [markdown]
# ### Lo mismo por producto
#
# Si los productos de larga vida repiten más que los perecederos, es real:
# la papa efectivamente no cambia de precio a diario, la lechuga sí.

# %%
por_producto = (
    df.groupby("producto")
      .agg(obs=("precio_arrastrado", "size"),
           arrastrados=("precio_arrastrado", "sum"))
      .assign(pct=lambda d: (d["arrastrados"] / d["obs"] * 100).round(1))
      .sort_values("pct", ascending=False)
)
print(por_producto.to_string())

print("\nSi arriba están tubérculos y abajo hojas verdes, el patrón es real.")
print("Si el orden parece aleatorio, es problema de captura.")

# %% [markdown]
# ### La prueba decisiva: cruce plaza × producto
#
# El caso delator es un producto perecedero con precio congelado en una plaza
# específica pero variable en las demás. Eso no puede ser mercado.

# %%
cruce = (
    df.groupby(["plaza", "producto"])["precio_arrastrado"]
      .agg(["size", "sum"])
      .assign(pct=lambda d: (d["sum"] / d["size"] * 100).round(1))
)
cruce = cruce[cruce["size"] >= 30]

print("Combinaciones con más del 60% de precios repetidos:")
graves = cruce[cruce["pct"] > 60].sort_values("pct", ascending=False)
print(f"{len(graves)} casos de {len(cruce)}")
print(graves.head(25).to_string())

# %% [markdown]
# ## 3. ¿Cambia el índice si excluimos los arrastrados?
#
# Esta es la pregunta que importa. El índice de +7,3% se calculó sobre el
# panel fijo sin distinguir precios repetidos. Si al excluirlos el resultado
# se mueve mucho, el número principal del proyecto no es defendible como está.

# %%
print("Arrastre dentro del panel fijo:")
panel = df[df["en_panel"]]
print(panel.groupby("plaza")["precio_arrastrado"].agg(["size", "mean"]).round(3)
      .to_string())

f0 = df["fecha"].min()


def jevons(datos: pd.DataFrame) -> pd.Series:
    """Media geométrica de las razones respecto a la fecha base."""
    base = (
        datos[datos["fecha"] == f0]
        .set_index(["plaza", "producto_clave"])["precio_kg"]
    )
    d = datos.copy()
    idx = pd.MultiIndex.from_arrays([d["plaza"], d["producto_clave"]])
    d["base"] = base.reindex(idx).to_numpy()
    d = d.dropna(subset=["base"])
    d["rel"] = d["precio_kg"] / d["base"]
    return np.exp(d.groupby("fecha")["rel"].apply(lambda x: np.log(x).mean())) * 100


variantes = {
    "todo el panel": panel,
    "sin arrastrados": panel[~panel["precio_arrastrado"]],
    "sin atípicos": panel[~panel["atipico"]],
    "solo confiables": panel[panel["confiable"]],
}

resultados = {}
for nombre, datos in variantes.items():
    idx = jevons(datos)
    resultados[nombre] = idx
    print(f"{nombre:<18} final = {idx.iloc[-1]:6.2f}  "
          f"({idx.iloc[-1] - 100:+.2f}%)  n = {len(datos):,}")

fig, eje = plt.subplots()
for nombre, idx in resultados.items():
    eje.plot(idx.index, idx.values, lw=1.5, label=nombre, alpha=0.85)
eje.axhline(100, color="gray", ls=":", lw=0.8)
eje.set_title("Índice de Jevons según qué observaciones se incluyen")
eje.set_ylabel("índice (base 100)")
eje.legend(fontsize=9)
plt.tight_layout()
plt.savefig(FIGURAS / "06_sensibilidad_arrastre.png", bbox_inches="tight")
plt.show()

print("\nSi las cuatro variantes terminan dentro de un punto entre sí, el")
print("resultado es robusto y el arrastre no importa para la conclusión.")
print("Si se separan varios puntos, hay que reportar el rango, no un número.")

# %% [markdown]
# ## 4. ¿El arrastre amortigua la volatilidad?
#
# Aunque la tendencia no cambie, los precios repetidos sí podrían estar
# aplanando la variabilidad diaria. Eso importa para el hallazgo del ciclo
# semanal.

# %%
for nombre in ("todo el panel", "sin arrastrados"):
    idx = resultados[nombre]
    cambios = idx.pct_change().dropna()
    print(f"{nombre:<18} volatilidad diaria = {cambios.std() * 100:.3f}%")

print("\nSi la volatilidad sube al excluir arrastrados, esos precios repetidos")
print("estaban aplanando la serie y el ciclo semanal real es más marcado")
print("de lo que mediste.")