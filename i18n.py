"""
Traducciones del dashboard.

Regla de diseño: **el DataFrame nunca se traduce.** Los datos conservan sus
valores originales en español (que es como los publica el DANE) y la
traducción ocurre solo al renderizar.

Si se tradujeran los valores del DataFrame, cambiar de idioma a mitad de
sesión alteraría los datos: los filtros guardados en session_state dejarían
de coincidir y los agrupamientos producirían categorías distintas.
"""

from __future__ import annotations

import streamlit as st

IDIOMAS = {"es": "Español", "en": "English"}
POR_DEFECTO = "es"

DIAS_ORDEN = ["lunes", "martes", "miércoles", "jueves", "viernes"]


# ---------------------------------------------------------------------------
# INTERFAZ
# ---------------------------------------------------------------------------

T: dict[str, dict[str, str]] = {
    "app.titulo": {
        "es": "Precios mayoristas de alimentos · Colombia",
        "en": "Wholesale Food Prices · Colombia",
    },
    "app.sub": {
        "es": "Datos del DANE (SIPSA), actualizados automáticamente cada día hábil",
        "en": "DANE data (SIPSA), automatically updated every business day",
    },
    "app.idioma": {"es": "Idioma", "en": "Language"},

    # --- Sidebar ---
    "f.titulo": {"es": "Filtros", "en": "Filters"},
    "f.fechas": {"es": "Rango de fechas", "en": "Date range"},
    "f.plazas": {"es": "Plazas", "en": "Markets"},
    "f.grupos": {"es": "Grupo de alimento", "en": "Food group"},
    "f.solo_confiables": {"es": "Solo datos confiables", "en": "Reliable data only"},
    "f.ayuda_confiables": {
        "es": "Excluye precios repetidos, atípicos y fuera de rango",
        "en": "Excludes carried-over, outlier and out-of-range prices",
    },
    "f.limpiar": {"es": "Restablecer filtros", "en": "Reset filters"},
    "f.vacio": {
        "es": "No hay datos con los filtros seleccionados.",
        "en": "No data matches the selected filters.",
    },

    # --- Pestañas ---
    "tab.indice": {"es": "Índice de precios", "en": "Price Index"},
    "tab.formulas": {"es": "Comparador de fórmulas", "en": "Formula Comparison"},
    "tab.dia": {"es": "Mejor día para comprar", "en": "Best Day to Buy"},
    "tab.explorador": {"es": "Explorador", "en": "Explorer"},
    "tab.calidad": {"es": "Calidad de datos", "en": "Data Quality"},

    # --- KPIs ---
    "kpi.indice": {"es": "Índice actual", "en": "Current index"},
    "kpi.variacion": {"es": "Variación del periodo", "en": "Period change"},
    "kpi.ultima": {"es": "Última actualización", "en": "Last updated"},
    "kpi.registros": {"es": "Registros", "en": "Records"},
    "kpi.plazas": {"es": "Plazas", "en": "Markets"},
    "kpi.productos": {"es": "Productos", "en": "Products"},

    # --- Índice ---
    "idx.titulo": {
        "es": "Índice de precios mayoristas (base 100)",
        "en": "Wholesale price index (base 100)",
    },
    "idx.metodo": {
        "es": "Calculado con índice de Jevons sobre panel fijo: solo las series "
              "con cobertura de al menos 95 % de los días. Esto garantiza que el "
              "índice se mueva por cambios de precio y no por cambios de muestra.",
        "en": "Computed with a Jevons index over a fixed panel: only series with "
              "at least 95 % day coverage. This ensures the index moves because "
              "prices change, not because the sample changes.",
    },
    "idx.panel": {"es": "Plazas del panel", "en": "Panel markets"},
    "idx.series": {"es": "Series en el panel", "en": "Series in panel"},
    "idx.por_grupo": {
        "es": "Variación por grupo de alimento",
        "en": "Change by food group",
    },
    "idx.top_sube": {"es": "Productos que más subieron", "en": "Biggest increases"},
    "idx.top_baja": {"es": "Productos que más bajaron", "en": "Biggest decreases"},

    # --- Fórmulas ---
    "for.titulo": {
        "es": "El mismo dato, tres respuestas distintas",
        "en": "Same data, three different answers",
    },
    "for.intro": {
        "es": "Sobre exactamente las mismas series, la fórmula elegida cambia el "
              "resultado en más de 11 puntos porcentuales. Para comparar: todos los "
              "problemas de calidad de datos del proyecto lo mueven menos de medio "
              "punto. Antes de discutir si los datos están sucios, hay que preguntar "
              "cómo se calcula la métrica.",
        "en": "Over exactly the same series, the chosen formula changes the result "
              "by more than 11 percentage points. For comparison: every data quality "
              "issue in this project moves it by less than half a point. Before "
              "debating whether the data is dirty, ask how the metric is computed.",
    },
    "for.elegir": {"es": "Fórmulas a mostrar", "en": "Formulas to display"},
    "for.resultado": {"es": "Resultado final", "en": "Final result"},
    "for.brecha": {"es": "Brecha máxima entre fórmulas", "en": "Maximum gap between formulas"},
    "for.jevons.nom": {"es": "Jevons (media geométrica)", "en": "Jevons (geometric mean)"},
    "for.jevons.des": {
        "es": "Estándar moderno para índices elementales. Sin el sesgo al alza de "
              "Carli y coherente con la distribución log-normal de los precios.",
        "en": "Modern standard for elementary indices. Free of Carli's upward bias "
              "and consistent with the log-normal distribution of prices.",
    },
    "for.carli.nom": {"es": "Carli (media aritmética de razones)", "en": "Carli (arithmetic mean of ratios)"},
    "for.carli.des": {
        "es": "Promedia el cambio de cada serie. Trata todos los productos por igual "
              "pero tiene un sesgo al alza conocido, agravado con precios volátiles.",
        "en": "Averages each series' change. Treats all products equally but has a "
              "known upward bias, worsened by volatile prices.",
    },
    "for.dutot.nom": {"es": "Dutot (razón de promedios)", "en": "Dutot (ratio of averages)"},
    "for.dutot.des": {
        "es": "Promedia precios y luego divide. Da más peso a los productos caros, "
              "así que el resultado depende de qué haya en la canasta.",
        "en": "Averages prices then divides. Gives more weight to expensive products, "
              "so the result depends on what is in the basket.",
    },

    # --- Mejor día ---
    "dia.titulo": {
        "es": "¿Qué día conviene comprar?",
        "en": "Which day is best to buy?",
    },
    "dia.intro": {
        "es": "Los precios mayoristas son sistemáticamente más altos el lunes y más "
              "bajos el jueves. El patrón se verifica dentro de una misma plaza, así "
              "que no se explica por cambios en la muestra de mercados.",
        "en": "Wholesale prices are systematically highest on Monday and lowest on "
              "Thursday. The pattern holds within a single market, so it cannot be "
              "explained by changes in the sample.",
    },
    "dia.producto": {"es": "Producto", "en": "Product"},
    "dia.mejor": {"es": "Día más barato", "en": "Cheapest day"},
    "dia.peor": {"es": "Día más caro", "en": "Most expensive day"},
    "dia.ahorro": {"es": "Ahorro potencial", "en": "Potential saving"},
    "dia.grafico": {
        "es": "Precio relativo por día de la semana",
        "en": "Relative price by weekday",
    },
    "dia.ranking": {
        "es": "Productos con mayor oscilación semanal",
        "en": "Products with the largest weekly swing",
    },
    "dia.amplitud": {"es": "Amplitud semanal", "en": "Weekly amplitude"},
    "dia.nota": {
        "es": "Estas cifras son cotas mínimas: al excluir los precios repetidos la "
              "volatilidad diaria sube, lo que indica que el ciclo real es mayor.",
        "en": "These figures are lower bounds: excluding carried-over prices raises "
              "daily volatility, indicating the real cycle is larger.",
    },

    # --- Explorador ---
    "exp.titulo": {"es": "Explorar precios", "en": "Explore prices"},
    "exp.producto": {"es": "Producto", "en": "Product"},
    "exp.serie": {"es": "Evolución del precio", "en": "Price over time"},
    "exp.comparar": {"es": "Precio mediano por plaza", "en": "Median price by market"},
    "exp.dispersion": {
        "es": "Dispersión de precios entre plazas",
        "en": "Price dispersion across markets",
    },
    "exp.mas_cara": {"es": "Plaza más cara", "en": "Most expensive market"},
    "exp.mas_barata": {"es": "Plaza más barata", "en": "Cheapest market"},
    "exp.diferencia": {"es": "Diferencia", "en": "Difference"},
    "exp.tabla": {"es": "Datos filtrados", "en": "Filtered data"},
    "exp.descargar": {"es": "Descargar CSV", "en": "Download CSV"},

    # --- Calidad ---
    "cal.titulo": {
        "es": "Qué se corrigió y qué se marcó",
        "en": "What was corrected and what was flagged",
    },
    "cal.intro": {
        "es": "Ninguna regla elimina filas. Las que detectan problemas agregan una "
              "marca y el análisis decide. Si se borraran, nadie podría revisar el "
              "criterio ni medir cuánto pesaba cada problema.",
        "en": "No rule deletes rows. Those that detect problems add a flag and the "
              "analysis decides. If rows were deleted, nobody could review the "
              "criteria or measure how large each problem was.",
    },
    "cal.regla": {"es": "Problema detectado", "en": "Detected issue"},
    "cal.filas": {"es": "Filas", "en": "Rows"},
    "cal.pct": {"es": "% del total", "en": "% of total"},
    "cal.arrastre": {
        "es": "Precios repetidos por plaza",
        "en": "Carried-over prices by market",
    },
    "cal.arrastre_nota": {
        "es": "Un precio idéntico durante tres días o más en un producto fresco "
              "sugiere que el encuestador repitió la cotización anterior. Armenia "
              "concentra el problema: allí el tomate repite el 73 % de los días. "
              "Esa plaza no forma parte del panel de referencia.",
        "en": "An identical price for three or more days on a fresh product suggests "
              "the surveyor repeated the previous quote. Armenia concentrates the "
              "problem: tomato repeats on 73 % of days there. That market is not part "
              "of the reference panel.",
    },
    "cal.cobertura": {"es": "Cobertura por plaza", "en": "Coverage by market"},
    "cal.cobertura_nota": {
        "es": "Solo tres plazas reportan todos los días hábiles. El panel de "
              "referencia se construye con ellas, lo que gana comparabilidad y "
              "cuesta representatividad. Este índice no es nacional.",
        "en": "Only three markets report every business day. The reference panel is "
              "built from them, gaining comparability at the cost of "
              "representativeness. This index is not national.",
    },
    "cal.confiables": {"es": "Registros sin marcas", "en": "Unflagged records"},

    # --- Común ---
    "com.plaza": {"es": "Plaza", "en": "Market"},
    "com.producto": {"es": "Producto", "en": "Product"},
    "com.precio": {"es": "Precio ($/kg)", "en": "Price (COP/kg)"},
    "com.fecha": {"es": "Fecha", "en": "Date"},
    "com.dia": {"es": "Día", "en": "Day"},
    "com.indice": {"es": "Índice", "en": "Index"},
    "com.grupo": {"es": "Grupo", "en": "Group"},
    "com.variacion": {"es": "Variación", "en": "Change"},
    "com.obs": {"es": "Observaciones", "en": "Observations"},
    "com.fuente": {"es": "Fuente", "en": "Source"},
    "com.repo": {"es": "Código del proyecto", "en": "Project code"},
}


# ---------------------------------------------------------------------------
# VALORES DE DATOS
# ---------------------------------------------------------------------------

DIAS = {
    "lunes": {"es": "Lunes", "en": "Monday"},
    "martes": {"es": "Martes", "en": "Tuesday"},
    "miércoles": {"es": "Miércoles", "en": "Wednesday"},
    "jueves": {"es": "Jueves", "en": "Thursday"},
    "viernes": {"es": "Viernes", "en": "Friday"},
}

GRUPOS = {
    "Frutas frescas": {"es": "Frutas frescas", "en": "Fresh fruit"},
    "Verduras y hortalizas": {"es": "Verduras y hortalizas", "en": "Vegetables"},
    "Tubérculos, raíces y plátanos": {
        "es": "Tubérculos, raíces y plátanos",
        "en": "Tubers, roots and plantains",
    },
}

PRODUCTOS = {
    "Aguacate": "Avocado", "Ahuyama": "Squash",
    "Arracacha": "Arracacha", "Arveja verde en vaina": "Green peas in pod",
    "Banano": "Banana", "Cebolla cabezona blanca": "White onion",
    "Cebolla junca": "Spring onion", "Chócolo mazorca": "Corn on the cob",
    "Coco": "Coconut", "Fríjol verde": "Green beans (shelled)",
    "Granadilla": "Granadilla", "Guayaba": "Guava",
    "Habichuela": "Green beans", "Lechuga Batavia": "Batavia lettuce",
    "Limón Tahití": "Tahiti lime", "Limón común": "Common lime",
    "Lulo": "Lulo", "Mandarina": "Mandarin",
    "Mango Tommy": "Tommy mango", "Manzana royal gala": "Royal gala apple",
    "Maracuyá": "Passion fruit", "Mora de Castilla": "Andean blackberry",
    "Naranja": "Orange", "Papa criolla": "Criolla potato",
    "Papa negra": "Black potato", "Papaya Maradol": "Maradol papaya",
    "Pepino cohombro": "Cucumber", "Pimentón": "Bell pepper",
    "Piña": "Pineapple", "Plátano guineo": "Guineo plantain",
    "Plátano hartón verde": "Green hartón plantain", "Remolacha": "Beetroot",
    "Tomate": "Tomato", "Tomate de árbol": "Tree tomato",
    "Yuca": "Cassava", "Zanahoria": "Carrot",
}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def idioma() -> str:
    if "idioma" not in st.session_state:
        st.session_state.idioma = POR_DEFECTO
    return st.session_state.idioma


def t(clave: str) -> str:
    """Traduce una clave de interfaz.

    Si falta, devuelve [clave] entre corchetes. Es deliberado: una clave sin
    traducir visible en pantalla se detecta al instante; un texto vacío no.
    """
    e = T.get(clave)
    if e is None:
        return f"[{clave}]"
    return e.get(idioma(), e.get(POR_DEFECTO, f"[{clave}]"))


def tr_dia(dia: str) -> str:
    return DIAS.get(dia, {}).get(idioma(), dia)


def tr_grupo(grupo: str) -> str:
    return GRUPOS.get(grupo, {}).get(idioma(), grupo)


def tr_producto(producto: str) -> str:
    if idioma() == "es":
        return producto
    return PRODUCTOS.get(producto, producto)


def dias_traducidos() -> list[str]:
    return [tr_dia(d) for d in DIAS_ORDEN]


def selector_idioma() -> str:
    """Streamlit reejecuta el script al cambiar el widget, así que toda la
    interfaz se retraduce sola sin necesidad de st.rerun()."""
    codigos = list(IDIOMAS)
    sel = st.sidebar.radio(
        t("app.idioma"),
        options=codigos,
        index=codigos.index(idioma()),
        format_func=lambda c: IDIOMAS[c],
        horizontal=True,
        key="selector_idioma",
    )
    st.session_state.idioma = sel
    return sel


def claves_faltantes() -> list[str]:
    """Para una prueba automática: si no está vacío, hay interfaz sin traducir."""
    faltan = []
    for clave, trads in T.items():
        for cod in IDIOMAS:
            if cod not in trads or not trads[cod].strip():
                faltan.append(f"{clave} [{cod}]")
    return faltan