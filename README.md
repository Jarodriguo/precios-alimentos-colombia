# Precios mayoristas de alimentos en Colombia

Pipeline automatizado que captura, depura y analiza los precios mayoristas que el DANE publica cada día hábil, y responde una pregunta incómoda: **¿cuánto de lo que llamamos "inflación de alimentos" depende de cómo decidimos medirla?**

[![Actualizar datos SIPSA](https://github.com/Jarodriguo/sipsa-pipeline/actions/workflows/actualizar-datos.yml/badge.svg)](https://github.com/Jarodriguo/sipsa-pipeline/actions/workflows/actualizar-datos.yml)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![Registros](https://img.shields.io/badge/registros-44K+-green)
![Actualización](https://img.shields.io/badge/actualización-diaria%20automática-brightgreen)

<!-- Reemplaza por una captura del dashboard: ![Dashboard](reports/figuras/dashboard.png) -->

---

## Los tres hallazgos

### 1. La fórmula del índice importa tres veces más que la calidad de los datos

Sobre **exactamente el mismo panel** de 75 series de precios, entre marzo y septiembre de 2026:

| Fórmula del índice | Resultado |
|---|---:|
| Carli (media aritmética de razones) | **+16,2 %** |
| Jevons (media geométrica) | **+7,3 %** |
| Dutot (razón de medias) | **+4,8 %** |

Mismos datos, mismas fechas, mismos productos. Tres respuestas separadas por 11 puntos porcentuales.

Para comparar: todos los problemas de calidad de datos encontrados en el proyecto (precios repetidos, valores atípicos, plazas mal nombradas) mueven el resultado **menos de medio punto**.

> La conclusión práctica: antes de discutir si los datos están sucios, hay que preguntar cómo se está calculando la métrica. Es el mismo problema que aparece cuando dos áreas de una empresa reportan "el mismo" KPI y no coinciden.

### 2. Existe un ciclo semanal de precios, y es aprovechable

Los precios mayoristas son sistemáticamente más altos el lunes y más bajos el jueves.

| Día | Índice relativo (Corabastos) |
|---|---:|
| Lunes | 1,0373 |
| Martes | 1,0283 |
| Miércoles | 1,0112 |
| **Jueves** | **1,0093** |
| Viernes | 1,0183 |

Son **2,8 puntos porcentuales** entre el día más caro y el más barato, medidos dentro de una sola plaza para descartar cualquier efecto de composición de muestra.

El efecto se concentra en los perecederos:

| Producto | Amplitud semanal |
|---|---:|
| Habichuela | 20,2 % |
| Cebolla junca | 15,5 % |
| Remolacha | 11,4 % |
| Mandarina | 11,1 % |
| Chócolo mazorca | 10,8 % |

La habichuela oscila una quinta parte de su precio dentro de la misma semana. Para un restaurante o un tendero que compra al por mayor, elegir el día de compra tiene efecto medible sobre el costo.

Además, estas cifras son **cotas mínimas**: al excluir los precios arrastrados (ver [Calidad de datos](#calidad-de-datos)), la volatilidad diaria sube de 2,22 % a 2,44 %, lo que indica que el ciclo real es más marcado.

### 3. El resultado principal, con su rango

> Entre el 9 de marzo y el 10 de septiembre de 2026, los precios mayoristas de 36 alimentos frescos subieron **+7,3 %** en las tres plazas de reporte continuo (Corabastos, Central Mayorista de Antioquia y Santa Marta), medido con índice de Jevons sobre panel fijo.
>
> **Rango: +7,0 % a +7,5 %** según el tratamiento de observaciones sospechosas.
> **Robustez:** el resultado se mantiene entre +7,03 % y +7,87 % con umbrales de cobertura del 70 % al 100 %.

---

## Una hipótesis que se cayó

Este proyecto empezó con una tesis distinta, y los datos la refutaron. Queda documentada porque el proceso importa tanto como el resultado.

**Hipótesis inicial.** El DANE no encuesta las mismas plazas todos los días: 16 los viernes, 11 los martes, 14 los lunes. Esa rotación debería sesgar cualquier promedio calculado por fecha, porque el índice se movería al cambiar la muestra y no los precios.

**Cómo se puso a prueba.** Se construyeron las cuatro combinaciones de muestra (variable / panel fijo) y fórmula (Dutot / Carli), comparando pares que difieren en una sola variable a la vez.

**Resultado.**

| Efecto | Aporte |
|---|---:|
| Muestra (variable → panel fijo) | **+0,09 puntos** |
| Fórmula (Dutot → Carli) | +6,44 puntos |
| Interacción | +4,96 puntos |

El efecto de la muestra es prácticamente cero. La rotación de plazas es real y está medida, pero las plazas que entran y salen tienen niveles de precio equivalentes, así que al intercambiarse el promedio no se mueve.

**Lo que enseña.** Una estructura problemática en los datos no implica automáticamente un sesgo en el resultado. El sesgo se mide, no se deduce. El primer análisis atribuía 11 puntos a un problema de datos que en realidad venía de la fórmula.

El desarrollo completo está en `notebooks/eda_02_distribuciones_sesgo.py` (hipótesis) y `notebooks/eda_03_descomposicion.py` (refutación).

---

## Cómo funciona

```
DANE (anexo .xlsx diario)
        |
        v
  extraer.py  ------>  data/raw/*.xlsx        (crudo, inmutable)
        |
        v   formato ancho -> largo, carga idempotente
  precios_sipsa.parquet
        |
        v   7 reglas documentadas
  limpiar.py  ------>  precios_limpio.parquet
        |
        v   5 controles de calidad
  pipeline.py ------>  metricas.json + pipeline.log
        |
        v
  GitHub Actions (lun-vie, 17:00 COT)  ------>  commit automático
```

**Extracción.** El anexo del DANE tiene URL predecible a partir de la fecha (`anex-SIPSADiario-08sep2026.xlsx`), así que no hace falta raspar HTML. El Excel viene en formato ancho, con un bloque de dos columnas por plaza, encabezado en dos niveles con celdas combinadas, rótulos de grupo intercalados entre los datos y notas al pie dentro de la tabla. El parser lo convierte a formato largo.

**Por qué formato largo.** El número de plazas encuestadas cambia según el día de la semana. En formato ancho eso significa columnas que aparecen y desaparecen, y un esquema que se rompe. En formato largo, un día con menos plazas simplemente aporta menos filas.

**Idempotencia.** La llave natural es `(fecha, ciudad, mercado, producto)`, verificada con cero violaciones sobre 44 mil filas. Al reprocesar una fecha se eliminan sus filas y se vuelven a insertar. Correr el pipeline una vez o cien produce el mismo resultado.

Eso no es un detalle académico: GitHub ejecuta los cron con retraso y ocasionalmente se salta una corrida. Por eso el pipeline procesa los últimos cinco días hábiles en lugar de solo el de hoy. Si se pierde una ejecución, la siguiente se pone al día sola.

**Controles de calidad.** Cinco verificaciones antes de guardar: esquema, volumen, vocabulario, rango y duplicados. Las expectativas no están escritas a mano: se derivan del histórico acumulado, comparando cada día contra otros días de la misma semana. El pipeline se recalibra solo a medida que acumula datos.

Si un control falla, la ejecución termina con código 2 y GitHub la marca en amarillo. Si algo se rompe de verdad, termina con código 1 y no guarda nada. **Un fallo ruidoso es preferible a tres semanas cargando basura en silencio.**

---

## Calidad de datos

Siete reglas, todas derivadas de hallazgos medidos en el EDA. Ninguna se aplicó por precaución genérica.

| Regla | Qué corrige | Filas | % | Acción |
|---|---|---:|---:|---|
| R1 | Plazas con dos nombres | 627 | 1,45 % | corrige |
| R2 | Etiquetas de grupo inconsistentes (7 -> 3) | 512 | 1,18 % | corrige |
| R3 | Precio fuera de rango físico | 0 | 0,00 % | marca |
| R4 | Precio idéntico 3+ días seguidos | 5.844 | 13,47 % | marca |
| R5 | Atípico dentro de su serie (z MAD > 5) | 214 | 0,49 % | marca |
| R6 | Día posterior a un puente festivo | 3.740 | 8,62 % | marca |
| R7 | Serie con cobertura >= 95 % (panel fijo) | 8.983 | 20,70 % | marca |

**Principio: marcar, no borrar.** Ninguna regla elimina filas. Las que detectan problemas agregan una columna booleana y el analista decide. Si se borraran, nadie podría revisar el criterio ni medir cuánto pesaba cada problema.

Cada regla tiene pruebas automáticas (`test_limpiar.py`, 26 casos), incluidos **controles negativos**: pruebas que verifican que la regla *no* actúe donde no debe. Una regla demasiado agresiva pasaría todas las pruebas positivas sin problema.

### Hallazgos sobre la fuente

**El DANE es riguroso con los números.** Cero precios fuera de rango en 44 mil registros. Su desorden está en el formato y las etiquetas, no en los valores.

**Tres archivos defectuosos con fecha.** El 14 de abril, el 6 de mayo y el 8 de julio de 2026 los anexos usan nomenclatura de grupos distinta al resto del periodo. El del 14 de abril además nombra la plaza de Pereira como "La 41" en lugar de "La 41-Impala": dos anomalías en el mismo archivo.

**Una plaza con dos nombres.** `Ibagué / La 21` y `Ibagué / Plaza La 21` nunca coexisten: la primera aparece martes, miércoles y viernes; la segunda **únicamente** los jueves. Confirmado con tres pruebas independientes (patrón de aparición complementario, catálogo de productos idéntico, niveles de precio equivalentes) más un control negativo sobre dos plazas que sí son distintas.

**Problema de captura localizado.** El 60,7 % de las observaciones de Armenia/Mercar repiten el precio del día anterior, contra 4,2 % en Corabastos. En Armenia, el **tomate** repite el 73,2 % de los días y la **cebolla junca** el 71,8 %: perecederos volátiles con precio congelado tres de cada cuatro días. Ninguna explicación de mercado cubre eso. Armenia no forma parte del panel de referencia.

**Doce días sin publicación**, todos festivos colombianos. El pipeline los distingue de un fallo real y no genera alerta.

---

## Decisiones metodológicas

**Índice de Jevons (media geométrica de razones).** Es el estándar moderno para índices elementales de precios, no tiene el sesgo al alza documentado de Carli, y encaja con la distribución log-normal confirmada en el EDA: la asimetría de los precios desaparece al pasar a escala logarítmica.

**Panel fijo con 95 % de cobertura.** Se sacrifica representatividad por comparabilidad, igual que en el IPC o en los índices bursátiles. La decisión se declara y se somete a prueba de sensibilidad: el resultado varía menos de un punto entre umbrales del 70 % y el 100 %.

Efecto secundario no planeado: las tres plazas del panel tienen poco arrastre de precios (4,2 %, 8,6 % y 9,1 %), mientras que Armenia con su 60,7 % queda fuera. La decisión tomada por comparabilidad también protegió el resultado del problema de captura.

**Marcar en lugar de filtrar.** Ver la sección anterior.

---

## Limitaciones

Ninguna de estas es un defecto oculto: son el alcance real del proyecto.

- **No es un índice nacional.** El panel lo componen tres plazas: Corabastos (Bogotá), Central Mayorista de Antioquia (Medellín) y Santa Marta. Ni siquiera bajando el umbral al 70 % entran más de cuatro. Cualquier lectura nacional sería una extrapolación.
- **Seis meses de historia.** Permite hablar del efecto de Semana Santa, que cae dentro del periodo, pero no de estacionalidad anual.
- **36 alimentos frescos**, no la canasta completa del SIPSA. El anexo diario es un subconjunto enfocado.
- **`Var %` reconstruida al 83,8 %.** El campo publicado por el DANE se validó recalculándolo desde los precios; la diferencia mediana (0,0023) corresponde al redondeo a pesos enteros de los precios publicados.
- **Armenia y Manizales** tienen problemas de captura documentados. Sus series no deberían usarse para análisis de volatilidad.

---

## Ejecutar el proyecto

```bash
git clone https://github.com/Jarodriguo/sipsa-pipeline.git
cd sipsa-pipeline

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

pytest test_limpiar.py -v        # 26 pruebas
python pipeline.py --dias 5      # descarga, limpia y valida
```

Carga histórica desde cero:

```bash
python extraer.py --desde 2026-03-09 --hasta 2026-09-10
python limpiar.py
```

Los notebooks de EDA usan celdas `# %%`: se abren como notebook en VS Code o Jupyter, pero se versionan como `.py` para que git muestre diferencias legibles.

---

## Estructura

```
sipsa-pipeline/
├── extraer.py                  Descarga y parseo del anexo
├── limpiar.py                  7 reglas de limpieza
├── test_limpiar.py             26 pruebas automáticas
├── pipeline.py                 Orquestador con controles de calidad
├── notebooks/
│   ├── eda_01_integridad_cobertura.py
│   ├── eda_02_distribuciones_sesgo.py     <- hipótesis inicial
│   ├── eda_03_descomposicion.py           <- refutación
│   └── eda_04_arrastre_y_formato.py
├── data/
│   ├── raw/                    Anexos .xlsx originales, sin modificar
│   └── processed/              Parquet crudo y limpio
├── reports/                    Métricas, log, reporte de limpieza, figuras
└── .github/workflows/          Automatización diaria
```

---

## Fuente

**DANE — SIPSA, componente de precios mayoristas.** Publicación diaria de lunes a viernes.
[Página oficial](https://www.dane.gov.co/index.php/estadisticas-por-tema/agropecuario/sistema-de-informacion-de-precios-sipsa/componente-precios-mayoristas)

Los datos son de dominio público. Este proyecto no está afiliado al DANE ni sus resultados constituyen cifras oficiales. Para estadísticas oficiales de inflación de alimentos, consultar el IPC publicado por el DANE.

---

## Autor

**Juan Alberto Rodríguez** — [@Jarodriguo](https://github.com/Jarodriguo)