#!/usr/bin/env python3
"""
Pruebas de las reglas de limpieza.

Cada regla que escribiste tiene aquí una prueba que verifica que hace lo que
dice. Sin esto, "limpiar los datos" es una afirmación sin respaldo.

Las pruebas usan datos mínimos construidos a mano, no el parquet real. Una
prueba que depende de datos reales deja de servir cuando los datos cambian, y
además no puede verificar casos que todavía no han ocurrido.

Uso:
    pip install pytest
    pytest test_limpiar.py -v
"""

from __future__ import annotations

import pandas as pd
import pytest

from limpiar import (PRECIO_MAX, PRECIO_MIN, RACHA_SOSPECHOSA, Registro,
                     limpiar, r1_unificar_plazas, r2_unificar_grupos,
                     r3_marcar_fuera_de_rango, r4_marcar_arrastrados,
                     r5_marcar_atipicos)


def fila(**kwargs) -> dict:
    """Fila base con valores válidos; los kwargs sobrescriben lo que interese."""
    base = {
        "fecha": pd.Timestamp("2026-03-09"),
        "ciudad": "Bogotá",
        "mercado": "Corabastos",
        "grupo_alimento": "Frutas frescas",
        "producto": "Banano",
        "producto_clave": "banano",
        "variedad_predominante": False,
        "precio_kg": 2000.0,
        "variacion": 0.0,
        "archivo_origen": "test.xlsx",
        "extraido_en": "2026-09-09T00:00:00",
    }
    base.update(kwargs)
    return base


def tabla(filas: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# R1 — Plazas con dos nombres
# ---------------------------------------------------------------------------

def test_r1_renombra_la_plaza_duplicada():
    df = tabla([
        fila(ciudad="Ibagué", mercado="Plaza La 21"),
        fila(ciudad="Ibagué", mercado="La 21"),
    ])
    out = r1_unificar_plazas(df, Registro(len(df)))
    assert set(out["mercado"]) == {"La 21"}


def test_r1_no_toca_plazas_distintas():
    """Control negativo: Mercasa y La 41-Impala coexisten, son distintas."""
    df = tabla([
        fila(ciudad="Pereira", mercado="Mercasa"),
        fila(ciudad="Pereira", mercado="La 41-Impala"),
    ])
    out = r1_unificar_plazas(df, Registro(len(df)))
    assert set(out["mercado"]) == {"Mercasa", "La 41-Impala"}


def test_r1_no_confunde_ciudades():
    """'La 41' solo se renombra en Pereira, no en cualquier ciudad."""
    df = tabla([fila(ciudad="Cali", mercado="La 41")])
    out = r1_unificar_plazas(df, Registro(len(df)))
    assert out["mercado"].iloc[0] == "La 41"


# ---------------------------------------------------------------------------
# R2 — Grupos de alimento
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("entrada,esperado", [
    ("Verduras y hortalizas", "Verduras y hortalizas"),
    ("Hortalizas y verduras", "Verduras y hortalizas"),
    ("Frutas", "Frutas frescas"),
    ("Frutas frescas", "Frutas frescas"),
    ("Tubérculos y plátanos", "Tubérculos, raíces y plátanos"),
    ("Tubérculos, plátanos", "Tubérculos, raíces y plátanos"),
    ("Tubérculos, raíces y plátanos", "Tubérculos, raíces y plátanos"),
])
def test_r2_normaliza_las_siete_etiquetas(entrada, esperado):
    df = tabla([fila(grupo_alimento=entrada)])
    out = r2_unificar_grupos(df, Registro(len(df)))
    assert out["grupo_alimento"].iloc[0] == esperado


def test_r2_deja_pasar_etiquetas_desconocidas():
    """Si el DANE inventa un grupo nuevo, no se pierde: pasa tal cual.

    Perder silenciosamente una categoría nueva sería peor que dejarla sin
    normalizar, porque nadie se enteraría.
    """
    df = tabla([fila(grupo_alimento="Categoría inventada")])
    out = r2_unificar_grupos(df, Registro(len(df)))
    assert out["grupo_alimento"].iloc[0] == "Categoría inventada"


def test_r2_es_idempotente():
    """Aplicar la regla dos veces da el mismo resultado que aplicarla una."""
    df = tabla([fila(grupo_alimento="Frutas")])
    una = r2_unificar_grupos(df.copy(), Registro(1))
    dos = r2_unificar_grupos(una.copy(), Registro(1))
    assert una["grupo_alimento"].iloc[0] == dos["grupo_alimento"].iloc[0]


# ---------------------------------------------------------------------------
# R3 — Rango de precio
# ---------------------------------------------------------------------------

def test_r3_marca_extremos_y_respeta_los_bordes():
    df = tabla([
        fila(precio_kg=PRECIO_MIN - 1),
        fila(precio_kg=PRECIO_MIN),
        fila(precio_kg=3000.0),
        fila(precio_kg=PRECIO_MAX),
        fila(precio_kg=PRECIO_MAX + 1),
    ])
    out = r3_marcar_fuera_de_rango(df, Registro(len(df)))
    assert out["fuera_de_rango"].tolist() == [True, False, False, False, True]


def test_r3_no_elimina_filas():
    df = tabla([fila(precio_kg=1)])
    out = r3_marcar_fuera_de_rango(df, Registro(len(df)))
    assert len(out) == 1


# ---------------------------------------------------------------------------
# R4 — Precios arrastrados
# ---------------------------------------------------------------------------

def _serie(precios: list[float]) -> pd.DataFrame:
    return tabla([
        fila(fecha=pd.Timestamp("2026-03-09") + pd.Timedelta(days=i), precio_kg=p)
        for i, p in enumerate(precios)
    ])


def test_r4_marca_racha_larga():
    df = _serie([2000, 2000, 2000, 2500])
    out = r4_marcar_arrastrados(df, Registro(len(df)))
    marcados = out.sort_values("fecha")["precio_arrastrado"].tolist()
    assert marcados == [False, True, True, False]


def test_r4_no_marca_racha_corta():
    """Dos días con el mismo precio es normal, no sospechoso."""
    df = _serie([2000, 2000, 2500])
    out = r4_marcar_arrastrados(df, Registro(len(df)))
    assert not out["precio_arrastrado"].any()


def test_r4_separa_series_distintas():
    """Dos productos distintos con el mismo precio no forman una racha."""
    df = tabla([
        fila(producto_clave="banano", precio_kg=2000),
        fila(producto_clave="mango tommy", precio_kg=2000),
        fila(producto_clave="lulo", precio_kg=2000),
    ])
    out = r4_marcar_arrastrados(df, Registro(len(df)))
    assert not out["precio_arrastrado"].any()


def test_r4_umbral_coincide_con_la_constante():
    """La prueba se ajusta si cambias RACHA_SOSPECHOSA, en vez de romperse."""
    df = _serie([2000.0] * RACHA_SOSPECHOSA + [9999.0])
    out = r4_marcar_arrastrados(df, Registro(len(df)))
    assert out["precio_arrastrado"].sum() == RACHA_SOSPECHOSA - 1

def test_r4_no_marca_la_primera_observacion_de_la_racha():
    """Verifica explícitamente que la medición original se conserva."""
    df = _serie([2000.0] * 5 + [3000.0])
    out = r4_marcar_arrastrados(df, Registro(len(df))).sort_values("fecha")
    assert out["precio_arrastrado"].tolist() == [False, True, True, True, True, False]


# ---------------------------------------------------------------------------
# R5 — Atípicos
# ---------------------------------------------------------------------------

def test_r5_detecta_el_valor_extremo():
    df = _serie([2000, 2050, 1980, 2020, 2010, 2030, 1990, 50_000])
    out = r5_marcar_atipicos(df, Registro(len(df)))
    assert out.loc[out["precio_kg"] == 50_000, "atipico"].all()
    assert not out.loc[out["precio_kg"] < 3000, "atipico"].any()


def test_r5_no_marca_serie_constante():
    """MAD = 0 no puede producir división por cero ni marcar todo."""
    df = _serie([2000] * 6)
    out = r5_marcar_atipicos(df, Registro(len(df)))
    assert not out["atipico"].any()


def test_r5_es_relativo_a_su_propia_serie():
    """14.000 es atípico para la papa y normal para el aguacate."""
    papa = [fila(producto_clave="papa negra", precio_kg=p,
                 fecha=pd.Timestamp("2026-03-09") + pd.Timedelta(days=i))
            for i, p in enumerate([1500, 1520, 1490, 1510, 1505, 14_000])]
    aguacate = [fila(producto_clave="aguacate", precio_kg=p,
                     fecha=pd.Timestamp("2026-03-09") + pd.Timedelta(days=i))
                for i, p in enumerate([13_800, 14_000, 13_900, 14_100, 13_950, 14_000])]
    out = r5_marcar_atipicos(tabla(papa + aguacate), Registro(12))

    assert out[(out["producto_clave"] == "papa negra") &
               (out["precio_kg"] == 14_000)]["atipico"].all()
    assert not out[out["producto_clave"] == "aguacate"]["atipico"].any()


# ---------------------------------------------------------------------------
# Pipeline completo
# ---------------------------------------------------------------------------

def test_limpiar_no_pierde_filas():
    """La limpieza marca, no borra. El conteo debe ser idéntico."""
    df = tabla([fila(precio_kg=p) for p in (1500, 2000, 99_999_999)])
    out, _ = limpiar(df)
    assert len(out) == len(df)


def test_limpiar_es_idempotente():
    """Limpiar dos veces da el mismo resultado."""
    df = tabla([
        fila(ciudad="Ibagué", mercado="Plaza La 21", grupo_alimento="Frutas"),
        fila(ciudad="Bogotá", mercado="Corabastos"),
    ])
    una, _ = limpiar(df)
    dos, _ = limpiar(una[df.columns])
    pd.testing.assert_frame_equal(
        una[["ciudad", "mercado", "grupo_alimento"]],
        dos[["ciudad", "mercado", "grupo_alimento"]],
    )


def test_el_registro_anota_todas_las_reglas():
    df = tabla([fila()])
    _, reg = limpiar(df)
    reglas = set(reg.tabla()["regla"])
    assert reglas == {"R1", "R2", "R3", "R4", "R5", "R6", "R7"}


def test_confiable_excluye_los_tres_problemas():
    df = _serie([2000, 2000, 2000, 2100, 2050, 2080])
    out, _ = limpiar(df)
    sospechosas = out["fuera_de_rango"] | out["atipico"] | out["precio_arrastrado"]
    assert (out["confiable"] == ~sospechosas).all()