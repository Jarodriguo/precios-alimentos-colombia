# Reglas de limpieza aplicadas

Filas de entrada: **43,390**

| Regla | Qué corrige | Filas | % | Acción |
|---|---|---:|---:|---|
| R1 | Plazas con dos nombres (Ibagué La 21, Pereira La 41) | 627 | 1.445% | corrige |
| R2 | Etiquetas de grupo inconsistentes (7 -> 3) | 512 | 1.18% | corrige |
| R3 | Precio fuera de [100, 100,000] | 0 | 0.0% | marca |
| R4 | Precio idéntico 3+ días seguidos | 5,844 | 13.469% | marca |
| R5 | Atípico dentro de su serie (|z MAD| > 5.0) | 214 | 0.493% | marca |
| R6 | Día posterior a un puente (>3 días sin publicación) | 3,740 | 8.619% | marca |
| R7 | Serie con cobertura >= 95% (panel fijo) | 8,983 | 20.703% | marca |

> Las reglas marcadas como *marca* no eliminan filas: agregan una columna booleana para que el análisis decida.