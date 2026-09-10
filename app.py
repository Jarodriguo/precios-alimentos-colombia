#!/usr/bin/env python3
"""
Dashboard de precios mayoristas de alimentos — SIPSA / DANE.

Ejecutar:
    streamlit run app.py

Los datos vienen del parquet que el pipeline actualiza cada día hábil. Cuando
GitHub Actions hace commit de datos nuevos, Streamlit Cloud redespliega solo.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from i18n import (DIAS_ORDEN, dias_traducidos, selector_idioma, t, tr_dia,
                  tr_grupo, tr_producto)

DATOS = Path("data/processed/precios_limpio.parquet")
REPO = "https://github.com/Jarodriguo/precios-alimentos-colombia"
FUENTE = ("https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/"
          "sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas")

COLORES = {"jevons": "#2E7D32", "carli": "#C62828", "dutot": "#1565C0"}

st.set_page_config(page_title="Precios mayoristas · Colombia",
                   page_icon="🥬", layout="wide")


# ---------------------------------------------------------------------------
# DATOS
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def cargar() -> pd.DataFrame:
    df = pd.read_parquet(DATOS)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def indice(datos: pd.DataFrame, metodo: str) -> pd.Series:
    """Calcula un índice de precios base 100 en la primera fecha.

    Los tres métodos son estándar en teoría de índices:
      dutot  = razón de promedios          -> pondera por nivel de precio
      carli  = media aritmética de razones -> sesgo al alza conocido
      jevons = media geométrica de razones -> sin ese sesgo
    """
    if datos.empty:
        return pd.Series(dtype=float)

    f0 = datos["fecha"].min()

    if metodo == "dutot":
        prom = datos.groupby("fecha")["precio_kg"].mean()
        return prom / prom.iloc[0] * 100

    base = (datos[datos["fecha"] == f0]
            .set_index(["plaza", "producto_clave"])["precio_kg"])
    d = datos.copy()
    idx = pd.MultiIndex.from_arrays([d["plaza"], d["producto_clave"]])
    d["base"] = base.reindex(idx).to_numpy()
    d = d.dropna(subset=["base"])
    if d.empty:
        return pd.Series(dtype=float)
    d["rel"] = d["precio_kg"] / d["base"]

    if metodo == "carli":
        return d.groupby("fecha")["rel"].mean() * 100
    return np.exp(d.groupby("fecha")["rel"].apply(lambda x: np.log(x).mean())) * 100


def ciclo_semanal(datos: pd.DataFrame) -> pd.Series:
    """Precio relativo promedio por día de la semana.

    Cada observación se normaliza contra la mediana de su propia serie
    plaza-producto. Así el resultado no depende de qué productos entren.
    """
    d = datos.copy()
    d["rel"] = d.groupby(["plaza", "producto_clave"])["precio_kg"].transform(
        lambda x: x / x.median()
    )
    return d.groupby("nombre_dia")["rel"].mean().reindex(DIAS_ORDEN)


df = cargar()

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------

selector_idioma()
st.sidebar.divider()
st.sidebar.header(t("f.titulo"))

fmin, fmax = df["fecha"].min().date(), df["fecha"].max().date()
rango = st.sidebar.date_input(t("f.fechas"), (fmin, fmax),
                              min_value=fmin, max_value=fmax)
if isinstance(rango, tuple) and len(rango) == 2:
    ini, fin = rango
else:
    ini, fin = fmin, fmax

plazas = sorted(df["plaza"].unique())
sel_plazas = st.sidebar.multiselect(t("f.plazas"), plazas, default=plazas)

grupos = sorted(df["grupo_alimento"].dropna().unique())
sel_grupos = st.sidebar.multiselect(
    t("f.grupos"), grupos, default=grupos, format_func=tr_grupo
)

solo_conf = st.sidebar.checkbox(t("f.solo_confiables"), value=False,
                                help=t("f.ayuda_confiables"))

d = df[
    (df["fecha"].dt.date >= ini) & (df["fecha"].dt.date <= fin)
    & df["plaza"].isin(sel_plazas)
    & df["grupo_alimento"].isin(sel_grupos)
]
if solo_conf:
    d = d[d["confiable"]]

st.sidebar.divider()
st.sidebar.caption(f"[{t('com.fuente')}: DANE SIPSA]({FUENTE})")
st.sidebar.caption(f"[{t('com.repo')}]({REPO})")

# ---------------------------------------------------------------------------
# ENCABEZADO
# ---------------------------------------------------------------------------

st.title(t("app.titulo"))
st.caption(t("app.sub"))

if d.empty:
    st.warning(t("f.vacio"))
    st.stop()

tabs = st.tabs([t("tab.indice"), t("tab.formulas"), t("tab.dia"),
                t("tab.explorador"), t("tab.calidad")])

# ===========================================================================
# 1 · ÍNDICE
# ===========================================================================
with tabs[0]:
    panel = d[d["en_panel"]]
    serie = indice(panel, "jevons")

    c1, c2, c3, c4 = st.columns(4)
    if not serie.empty:
        c1.metric(t("kpi.indice"), f"{serie.iloc[-1]:.1f}",
                  f"{serie.iloc[-1] - 100:+.1f}%")
    c2.metric(t("kpi.registros"), f"{len(d):,}")
    c3.metric(t("kpi.plazas"), d["plaza"].nunique())
    c4.metric(t("kpi.ultima"), d["fecha"].max().strftime("%Y-%m-%d"))

    st.subheader(t("idx.titulo"))
    if serie.empty:
        st.info(t("f.vacio"))
    else:
        fig = px.line(x=serie.index, y=serie.values,
                      labels={"x": t("com.fecha"), "y": t("com.indice")})
        fig.update_traces(line_color=COLORES["jevons"], line_width=2)
        fig.add_hline(y=100, line_dash="dot", line_color="gray")
        fig.update_layout(height=420, margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

    st.info(t("idx.metodo"))
    cols = st.columns(2)
    cols[0].metric(t("idx.panel"), panel["plaza"].nunique())
    cols[1].metric(t("idx.series"),
                   panel.groupby(["plaza", "producto_clave"]).ngroups)

    # --- Variación por producto -------------------------------------------
    st.subheader(t("idx.por_grupo"))

    def variacion_producto(datos: pd.DataFrame) -> pd.DataFrame:
        prim = datos.loc[datos.groupby("producto")["fecha"].idxmin()]
        ult = datos.loc[datos.groupby("producto")["fecha"].idxmax()]
        v = (ult.set_index("producto")["precio_kg"] /
             prim.set_index("producto")["precio_kg"] - 1) * 100
        g = datos.groupby("producto")["grupo_alimento"].first()
        return pd.DataFrame({"var": v, "grupo": g}).dropna()

    vp = variacion_producto(panel if not panel.empty else d)
    vp["etiqueta"] = [tr_producto(p) for p in vp.index]
    vp = vp.sort_values("var")

    fig = px.bar(vp, x="var", y="etiqueta", orientation="h",
                 color="var", color_continuous_scale="RdYlGn_r",
                 labels={"var": t("com.variacion") + " (%)", "etiqueta": ""})
    fig.update_layout(height=max(420, 18 * len(vp)), showlegend=False,
                      coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# 2 · COMPARADOR DE FÓRMULAS
# ===========================================================================
with tabs[1]:
    st.subheader(t("for.titulo"))
    st.write(t("for.intro"))

    nombres = {"jevons": t("for.jevons.nom"), "carli": t("for.carli.nom"),
               "dutot": t("for.dutot.nom")}
    elegidas = st.multiselect(t("for.elegir"), list(nombres),
                              default=list(nombres),
                              format_func=lambda k: nombres[k])

    panel = d[d["en_panel"]]
    series = {k: indice(panel, k) for k in elegidas}
    series = {k: v for k, v in series.items() if not v.empty}

    if series:
        fig = go.Figure()
        for k, s in series.items():
            fig.add_trace(go.Scatter(x=s.index, y=s.values, name=nombres[k],
                                     line=dict(color=COLORES[k], width=2)))
        fig.add_hline(y=100, line_dash="dot", line_color="gray")
        fig.update_layout(height=440, yaxis_title=t("com.indice"),
                          margin=dict(t=20),
                          legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig, use_container_width=True)

        finales = {k: s.iloc[-1] for k, s in series.items()}
        cols = st.columns(len(finales) + 1)
        for col, (k, v) in zip(cols, sorted(finales.items(),
                                            key=lambda x: -x[1])):
            col.metric(nombres[k], f"{v:.2f}", f"{v - 100:+.2f}%")
        if len(finales) > 1:
            brecha = max(finales.values()) - min(finales.values())
            cols[-1].metric(t("for.brecha"), f"{brecha:.2f} pp")

    st.divider()
    for k in ("jevons", "carli", "dutot"):
        with st.expander(nombres[k]):
            st.write(t(f"for.{k}.des"))

# ===========================================================================
# 3 · MEJOR DÍA PARA COMPRAR
# ===========================================================================
with tabs[2]:
    st.subheader(t("dia.titulo"))
    st.write(t("dia.intro"))

    productos = sorted(d["producto"].unique())
    prod = st.selectbox(t("dia.producto"), productos,
                        format_func=tr_producto)

    sub = d[d["producto"] == prod]
    ciclo = ciclo_semanal(sub).dropna()

    if len(ciclo) >= 2:
        barato, caro = ciclo.idxmin(), ciclo.idxmax()
        ahorro = (ciclo.max() / ciclo.min() - 1) * 100

        c1, c2, c3 = st.columns(3)
        c1.metric(t("dia.mejor"), tr_dia(barato))
        c2.metric(t("dia.peor"), tr_dia(caro))
        c3.metric(t("dia.ahorro"), f"{ahorro:.1f}%")

        vis = pd.DataFrame({
            "dia": [tr_dia(x) for x in ciclo.index],
            "rel": (ciclo.values - 1) * 100,
        })
        fig = px.bar(vis, x="dia", y="rel", color="rel",
                     color_continuous_scale="RdYlGn_r",
                     labels={"dia": t("com.dia"),
                             "rel": t("com.precio") + " (%)"})
        fig.update_layout(height=380, coloraxis_showscale=False,
                          title=t("dia.grafico"), margin=dict(t=50))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader(t("dia.ranking"))

    filas = []
    for p, g in d.groupby("producto"):
        c = ciclo_semanal(g).dropna()
        if len(c) >= 4:
            filas.append({
                t("com.producto"): tr_producto(p),
                t("dia.amplitud"): round((c.max() / c.min() - 1) * 100, 1),
                t("dia.mejor"): tr_dia(c.idxmin()),
                t("com.obs"): len(g),
            })

    ranking = (pd.DataFrame(filas)
               .sort_values(t("dia.amplitud"), ascending=False)
               .reset_index(drop=True))
    st.dataframe(ranking, use_container_width=True, hide_index=True)
    st.caption(t("dia.nota"))

# ===========================================================================
# 4 · EXPLORADOR
# ===========================================================================
with tabs[3]:
    st.subheader(t("exp.titulo"))

    prod2 = st.selectbox(t("exp.producto"), sorted(d["producto"].unique()),
                         format_func=tr_producto, key="exp_prod")
    sub = d[d["producto"] == prod2]

    if not sub.empty:
        vis = sub.copy()
        vis["etiqueta"] = vis["plaza"]
        fig = px.line(vis, x="fecha", y="precio_kg", color="etiqueta",
                      labels={"fecha": t("com.fecha"),
                              "precio_kg": t("com.precio"),
                              "etiqueta": t("com.plaza")})
        fig.update_layout(height=420, title=t("exp.serie"), margin=dict(t=50))
        st.plotly_chart(fig, use_container_width=True)

        medianas = (sub.groupby("plaza")["precio_kg"].median()
                    .sort_values(ascending=False))
        c1, c2, c3 = st.columns(3)
        c1.metric(t("exp.mas_cara"), medianas.index[0],
                  f"${medianas.iloc[0]:,.0f}")
        c2.metric(t("exp.mas_barata"), medianas.index[-1],
                  f"${medianas.iloc[-1]:,.0f}")
        c3.metric(t("exp.diferencia"),
                  f"{medianas.iloc[0] / medianas.iloc[-1]:.2f}x")

        fig = px.box(sub, x="plaza", y="precio_kg",
                     labels={"plaza": t("com.plaza"),
                             "precio_kg": t("com.precio")})
        fig.update_layout(height=420, title=t("exp.dispersion"),
                          margin=dict(t=50), xaxis={"categoryorder": "median descending"})
        st.plotly_chart(fig, use_container_width=True)

    with st.expander(t("exp.tabla")):
        cols = ["fecha", "plaza", "producto", "grupo_alimento",
                "precio_kg", "variacion", "confiable"]
        st.dataframe(d[cols].sort_values("fecha", ascending=False).head(1000),
                     use_container_width=True, hide_index=True)
        st.download_button(t("exp.descargar"),
                           d[cols].to_csv(index=False).encode("utf-8"),
                           "precios_sipsa.csv", "text/csv")

# ===========================================================================
# 5 · CALIDAD DE DATOS
# ===========================================================================
with tabs[4]:
    st.subheader(t("cal.titulo"))
    st.write(t("cal.intro"))

    total = len(d)
    c1, c2 = st.columns(2)
    c1.metric(t("cal.confiables"),
              f"{d['confiable'].sum():,}",
              f"{d['confiable'].mean() * 100:.1f}%")
    c2.metric(t("kpi.registros"), f"{total:,}")

    marcas = {
        t("cal.regla") + " · fuera de rango": "fuera_de_rango",
        t("cal.regla") + " · repetido 3+ días": "precio_arrastrado",
        t("cal.regla") + " · atípico": "atipico",
        t("cal.regla") + " · post-festivo": "post_puente",
    }
    resumen = pd.DataFrame([
        {t("cal.regla"): nombre.split(" · ")[1],
         t("cal.filas"): int(d[col].sum()),
         t("cal.pct"): round(d[col].mean() * 100, 2)}
        for nombre, col in marcas.items()
    ])
    st.dataframe(resumen, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader(t("cal.arrastre"))
    arr = (d.groupby("plaza")["precio_arrastrado"].mean() * 100).sort_values()
    fig = px.bar(x=arr.values, y=arr.index, orientation="h",
                 color=arr.values, color_continuous_scale="Reds",
                 labels={"x": "%", "y": ""})
    fig.update_layout(height=max(400, 20 * len(arr)),
                      coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(t("cal.arrastre_nota"))

    st.divider()
    st.subheader(t("cal.cobertura"))
    dias_totales = d["fecha"].nunique()
    cob = (d.groupby("plaza")["fecha"].nunique() / dias_totales * 100
           ).sort_values(ascending=False)
    fig = px.bar(x=cob.index, y=cob.values,
                 color=cob.values, color_continuous_scale="Greens",
                 labels={"x": t("com.plaza"), "y": "%"})
    fig.add_hline(y=95, line_dash="dash", line_color="gray")
    fig.update_layout(height=420, coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(t("cal.cobertura_nota"))