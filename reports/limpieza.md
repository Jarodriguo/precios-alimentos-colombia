# Reglas de limpieza aplicadas

Filas de entrada: **44,097**

| Regla | Qué corrige | Filas | % | Acción |
|---|---|---:|---:|---|
| R1 | Plazas con dos nombres (Ibagué La 21, Pereira La 41) | 652 | 1.479% | corrige |
| R2 | Etiquetas de grupo inconsistentes (7 -> 3) | 512 | 1.161% | corrige |
| R3 | Precio fuera de [100, 100,000] | 0 | 0.0% | marca |
| R4 | Precio idéntico 3+ días seguidos | 5,949 | 13.491% | marca |
| R5 | Atípico dentro de su serie (|z MAD| > 5.0) | 256 | 0.581% | marca |
| R6 | Día posterior a un puente (>3 días sin publicación) | 3,740 | 8.481% | marca |
| R7 | Serie con cobertura >= 95% (panel fijo) | 9,133 | 20.711% | marca |

> Las reglas marcadas como *marca* no eliminan filas: agregan una columna booleana para que el análisis decida.