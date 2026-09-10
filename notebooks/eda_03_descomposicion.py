#!/usr/bin/env python3
# %% [markdown]
# # EDA — Parte 3: descomponer la brecha
#
# La parte 2 encontró 11 puntos de diferencia entre el método ingenuo y el
# panel fijo. Pero esa comparación cambió **dos cosas a la vez**:
#
# | | Muestra | Fórmula |
# |---|---|---|
# | Ingenuo | variable | razón de promedios (Dutot) |
# | Panel | fija | promedio de razones (Carli) |
#
# Con dos cambios simultáneos, el resultado no dice cuál fue responsable.
#
# Aquí construimos las **cuatro combinaciones** para aislar cada efecto. Es la
# misma lógica de un experimento controlado: una variable a la vez.

# %%
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
plt.rcParams["figure.figsize"] = (12, 6)
plt.rcParams["figure.dpi"] = 110

FIGURAS = Path("reports/figuras")
FIGURAS.mkdir(parents=True, exist_ok=True)

df = pd.read_parquet("data/processed/precios_sipsa.parquet")
df["fecha"] = pd.to_datetime(df["fecha"])
df["plaza"] = df["ciudad"] + " / " + df["mercado"].fillna("—")
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes"]

# %% [markdown]
# ## 1. ¿Qué hay realmente dentro del panel?
#
# Antes de defender un índice hay que poder decir sobre qué se calcula.

# %%
dias_totales = df["fecha"].nunique()
cobertura = df.groupby(["plaza", "producto_clave"])["fecha"].nunique() / dias_totales

for umbral in (0.95, 0.90, 0.80, 0.70):
    sel = cobertura[cobertura >= umbral]
    plazas = sorted({p for p, _ in sel.index})
    print(f"Umbral {umbral:.0%}: {len(sel):3d} series | "
          f"{len(plazas)} plazas | {len({q for _, q in sel.index})} productos")
    print(f"    {plazas}")

print("\nEl umbral es una decisión con consecuencias: más alto da más")
print("comparabilidad y menos representatividad. Hay que declararlo, no")
print("esconderlo. Y hay que probar si el resultado depende de él.")

# %% [markdown]
# ## 2. Las cuatro combinaciones
#
# - **Dutot** (razón de promedios): promedia precios y luego divide.
#   Le da más peso a los productos caros.
# - **Carli** (promedio de razones): calcula el cambio de cada serie y luego
#   promedia. Trata todos los productos por igual, pero se sabe que sesga
#   hacia arriba.
# - **Jevons** (media geométrica de razones): el estándar moderno para
#   índices de precios elementales. No tiene el sesgo de Carli y encaja con
#   la distribución log-normal que vimos en la parte 2.

# %%
UMBRAL = 0.95
panel = cobertura[cobertura >= UMBRAL].index
df_panel = df.set_index(["plaza", "producto_clave"]).loc[panel].reset_index()

f0 = df["fecha"].min()


def dutot(datos: pd.DataFrame) -> pd.Series:
    """Razón de promedios. Sensible a qué series están presentes cada día."""
    prom = datos.groupby("fecha")["precio_kg"].mean()
    return prom / prom.iloc[0] * 100


def relativos(datos: pd.DataFrame) -> pd.DataFrame:
    """Añade el precio de cada serie en la fecha base."""
    base = (
        datos[datos["fecha"] == f0]
        .set_index(["plaza", "producto_clave"])["precio_kg"]
    )
    d = datos.copy()
    idx = pd.MultiIndex.from_arrays([d["plaza"], d["producto_clave"]])
    d["base"] = base.reindex(idx).to_numpy()
    d["rel"] = d["precio_kg"] / d["base"]
    return d.dropna(subset=["rel"])


def carli(datos: pd.DataFrame) -> pd.Series:
    """Media aritmética de razones."""
    return relativos(datos).groupby("fecha")["rel"].mean() * 100


def jevons(datos: pd.DataFrame) -> pd.Series:
    """Media geométrica de razones."""
    d = relativos(datos)
    return np.exp(d.groupby("fecha")["rel"].apply(lambda x: np.log(x).mean())) * 100


series = pd.DataFrame({
    "A_variable_dutot": dutot(df),
    "B_variable_carli": carli(df),
    "C_panel_dutot": dutot(df_panel),
    "D_panel_carli": carli(df_panel),
    "E_panel_jevons": jevons(df_panel),
}).dropna()

print(series.tail(10).round(2).to_string())

# %% [markdown]
# ## 3. La descomposición
#
# Comparando pares que difieren en una sola cosa:
#
# - **A → C**: misma fórmula (Dutot), cambia la muestra → **efecto muestra**
# - **A → B**: misma muestra (variable), cambia la fórmula → **efecto fórmula**

# %%
fin = series.iloc[-1]
print("Índice al final del periodo (base 100 al inicio):")
print(fin.round(2).to_string())

efecto_muestra = fin["C_panel_dutot"] - fin["A_variable_dutot"]
efecto_formula = fin["B_variable_carli"] - fin["A_variable_dutot"]
brecha_total = fin["D_panel_carli"] - fin["A_variable_dutot"]

print(f"\n{'=' * 60}")
print(f"Brecha total original (D - A) : {brecha_total:+6.2f} puntos")
print(f"  atribuible a la muestra     : {efecto_muestra:+6.2f} puntos")
print(f"  atribuible a la fórmula     : {efecto_formula:+6.2f} puntos")
print(f"  interacción / residuo       : "
      f"{brecha_total - efecto_muestra - efecto_formula:+6.2f} puntos")
print("=" * 60)
print("\nSi el efecto muestra domina, el hallazgo se sostiene.")
print("Si domina la fórmula, la conclusión de la parte 2 estaba mal.")

# %%
fig, eje = plt.subplots()
estilos = {
    "A_variable_dutot": ("#C44E52", 1.0, "-", "A · muestra variable + Dutot (ingenuo)"),
    "B_variable_carli": ("#C44E52", 1.0, "--", "B · muestra variable + Carli"),
    "C_panel_dutot": ("#4C72B0", 1.6, "-", "C · panel fijo + Dutot"),
    "D_panel_carli": ("#4C72B0", 1.6, "--", "D · panel fijo + Carli"),
    "E_panel_jevons": ("#55A868", 2.0, "-", "E · panel fijo + Jevons (recomendado)"),
}
for col, (color, ancho, linea, etiqueta) in estilos.items():
    eje.plot(series.index, series[col], color=color, lw=ancho, ls=linea,
             label=etiqueta, alpha=0.9)
eje.axhline(100, color="gray", ls=":", lw=0.8)
eje.set_title("Descomposición: efecto muestra vs efecto fórmula")
eje.set_ylabel("índice (base 100)")
eje.legend(fontsize=8)
plt.tight_layout()
plt.savefig(FIGURAS / "04_descomposicion.png", bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 4. El patrón semanal: la prueba directa del sesgo
#
# Independiente de la fórmula, hay una prueba limpia: si el índice tiene un
# patrón por día de la semana con muestra variable y ese patrón desaparece
# con panel fijo, el sesgo de composición es real.
#
# Ningún mecanismo económico explica que la comida cueste distinto los martes.

# %%
semanal = series.copy()
semanal["dia"] = semanal.index.weekday

tabla = semanal.groupby("dia")[list(estilos)].mean()
tabla.index = [DIAS[i] for i in tabla.index]
print("Índice promedio por día de la semana:")
print(tabla.round(2).to_string())

print("\nAmplitud del patrón semanal (máx - mín):")
amplitud = (tabla.max() - tabla.min()).round(2)
print(amplitud.to_string())
print("\nUna amplitud grande en A y pequeña en C/D/E confirma el sesgo.")

fig, eje = plt.subplots(figsize=(9, 4.5))
for col, (color, ancho, linea, etiqueta) in estilos.items():
    eje.plot(tabla.index, tabla[col], marker="o", color=color,
             lw=ancho, ls=linea, label=etiqueta, alpha=0.9)
eje.set_title("Índice promedio por día de la semana")
eje.set_ylabel("índice")
eje.legend(fontsize=8)
plt.tight_layout()
plt.savefig(FIGURAS / "05_patron_semanal.png", bbox_inches="tight")
plt.show()

# %% [markdown]
# ## 5. Prueba de sensibilidad al umbral
#
# Si el resultado cambia mucho según dónde pongas el corte de cobertura, el
# hallazgo es frágil. Si se mantiene, es robusto. Esta prueba es lo que
# distingue un resultado defendible de uno afortunado.

# %%
filas = []
for umbral in (0.70, 0.80, 0.90, 0.95, 1.00):
    sel = cobertura[cobertura >= umbral].index
    if len(sel) < 10:
        continue
    sub = df.set_index(["plaza", "producto_clave"]).loc[sel].reset_index()
    idx = jevons(sub)
    filas.append({
        "umbral": f"{umbral:.0%}",
        "series": len(sel),
        "plazas": len({p for p, _ in sel}),
        "indice_final": round(idx.iloc[-1], 2),
        "variacion_pct": round(idx.iloc[-1] - 100, 2),
    })

sensibilidad = pd.DataFrame(filas)
print(sensibilidad.to_string(index=False))
print(f"\nÍndice ingenuo para comparar: {fin['A_variable_dutot']:.2f}")
print("\nSi la variación se mantiene parecida en todos los umbrales, el")
print("resultado no depende de una decisión arbitraria tuya.")

# %% [markdown]
# ## 6. Qué se puede afirmar y qué no
#
# Escribe aquí las conclusiones con sus límites. Un resultado bien acotado
# vale más que uno grande sin condiciones.
#
# - El panel al 95% cubre solo las plazas que reportan a diario. **No es un
#   índice nacional**: es un índice de esas plazas. Nómbralo así.
# - El efecto muestra y el efecto fórmula deben reportarse por separado.
# - Seis meses no permiten hablar de estacionalidad anual. Sí de Semana Santa,
#   que cae dentro del periodo.

cora = df[df["plaza"] == "Bogotá / Corabastos"].copy()
cora["dia"] = cora["fecha"].dt.weekday
cora["rel"] = cora.groupby("producto_clave")["precio_kg"].transform(lambda x: x / x.median())
print(cora.groupby("dia")["rel"].mean().round(4))
print("\nPor producto (los 10 con mayor amplitud semanal):")
amp = cora.groupby(["producto_clave", "dia"])["rel"].mean().unstack()
print((amp.max(axis=1) - amp.min(axis=1)).nlargest(10).round(3))