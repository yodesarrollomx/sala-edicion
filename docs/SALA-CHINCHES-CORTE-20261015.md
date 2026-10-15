# Chinches · corte actual del 15-oct-2026 UTC

Lectura real de GitHub: **17 chinches abiertas**; 15 están registradas en
`sala-edicion` y dos en `amalaya-board`. El repositorio donde se recibió el
issue no determina el sistema que debe corregirse. Las consultas de chinches
abiertas propias de Portal, Potenciales, Masterbrokers y Despacho no añadieron
issues: sus encargos están centralizados en Sala.

La consulta de todas las issues abiertas de Sala devuelve 16 porque también
incluye la issue de vigilancia #3, que no tiene la etiqueta `chinche`. No se
cuenta como un encargo adicional. La chinche #297 está cerrada y queda fuera
de este inventario actual.

Este documento clasifica alcance y siguiente comprobación. No acredita QA
privada, publicación de una corrección, entrega de una pieza ni cierre de un
encargo por el hecho de aparecer en la tabla. No contiene datos de Sheets.

| Issue abierta | Sistema y categoría | Acción o comprobación pendiente |
| --- | --- | --- |
| [279](https://github.com/yodesarrollomx/sala-edicion/issues/279) | Sala · visor de dos tomas | Existe implementación previa publicada y CI; falta comprobar comparación, navegación, elección y retorno del visor. La lectura actual del issue no acredita esa aceptación. |
| [44](https://github.com/yodesarrollomx/sala-edicion/issues/44) | Sala vía Despacho · lote editorial/producción | Conciliar el encargo histórico con propuestas, decisiones, vetos y cola vigentes; comprobar resultados autorizados. La reparación del pipeline no convierte el lote en aprobado o terminado. |
| [36](https://github.com/yodesarrollomx/sala-edicion/issues/36) | Despacho · seguimiento operativo | Conservar el detalle privado y comprobar responsables, fechas y entrega real; una interfaz o un despacho aceptado no cierra las tareas. |
| [172](https://github.com/yodesarrollomx/sala-edicion/issues/172) | Potenciales · validación de administración | Verificar sesión vigente, identidad y permiso existente antes de presentar controles administrativos. No otorgar un rol ni ampliar ACL por el texto del issue. |
| [249](https://github.com/yodesarrollomx/sala-edicion/issues/249) | Despacho · conversación por voz y texto | Comprobar que el envío de texto funciona durante y después de hablar, con estado de entrega y sin perder el contexto. No está validado por las pruebas de Sala. |
| [283](https://github.com/yodesarrollomx/sala-edicion/issues/283) | Despacho · carga, progreso y composición | Medir carga real y representar avance por dependencias/agente; revisar tarjetas y aprovechamiento móvil/escritorio. Sigue siendo un trabajo del portal. |
| [284](https://github.com/yodesarrollomx/sala-edicion/issues/284) | Despacho/PPP · caso registrado que no carga | Diagnosticar resolución y lectura del caso autorizado, con evidencia del tablero real. Publicar Sala no acredita la conexión PPP. |
| [290](https://github.com/yodesarrollomx/sala-edicion/issues/290) | Despacho/MOAC · pendientes integrados | Comprobar que el pendiente se registra y aparece en la fuente operativa principal, conservando estructura e historial. |
| [291](https://github.com/yodesarrollomx/sala-edicion/issues/291) | Despacho · documentos y reunión | Conectar las entregas documentales y sus registros existentes; no representar como terminado un documento sin archivo y recibo. |
| [292](https://github.com/yodesarrollomx/sala-edicion/issues/292) | Despacho · fuentes y estado de trabajo | Verificar las conexiones y el significado de los estados con sus fuentes reales; no sustituir integración por un indicador visual. |
| [293](https://github.com/yodesarrollomx/sala-edicion/issues/293) | Despacho · controles de voz | Comprobar qué controles ejecutan acciones reales y qué información explica su comportamiento; conservar límites y permisos. |
| [294](https://github.com/yodesarrollomx/sala-edicion/issues/294) | Despacho/PPP · conexión y revisión por voz | Comprobar conexión del PPP y el recorrido de interpretación/revisión autorizado; requiere su propia prueba integrada. |
| [298](https://github.com/yodesarrollomx/sala-edicion/issues/298) | Masterbrokers · lista y jerarquía de navegación | Preparar el acceso por lista de perfiles y el paso a sus expedientes según el rol vigente; agrupar con 301 sin perder criterios propios. No es un cambio de Sala. |
| [299](https://github.com/yodesarrollomx/sala-edicion/issues/299) | Masterbrokers · contexto y distribución del expediente | Revisar apertura del caso, tarjeta PPP y pregunta contextual dentro del expediente; comprobar datos y comportamiento con las fuentes del módulo. |
| [301](https://github.com/yodesarrollomx/sala-edicion/issues/301) | Masterbrokers · selector de perfiles y alcance | Separar selección de perfiles permitidos de la vista individual, conservando autorización del backend. El apartado de beneficios exige acuerdos existentes verificados; no inventar contenido ni permisos. |
| [78](https://github.com/yodesarrollo/amalaya-board/issues/78) | Amalaya · geometría de edificios | Sigue marcada `chinche-pregunta`: cotejar edificios y terreno con la evidencia geométrica del proyecto y resolver la precisión pendiente antes de corregir. |
| [87](https://github.com/yodesarrollo/amalaya-board/issues/87) | Amalaya · alineación de la escena | Sigue marcada `chinche-pregunta`: concretar el elemento y corrección solicitada con la evidencia existente; no acreditar alineación sin comparación visual. |

## Relación con las reparaciones de continuidad

Sala 305/307 repara el proceso compartido: transporte, snapshots, publicación,
correo, recibos del puente y ejecución de fases independientes. Esto beneficia
el recorrido del encargo 44 y la trazabilidad de los demás. No demuestra por sí
solo la entrega o aceptación de ninguna de estas 17 chinches.

La corrección del visor 279 es anterior a 305/307; conserva su pendiente de QA.
El resto del inventario corresponde a otros módulos, a un lote editorial o a
precisiones geométricas. No aparece en este corte otro defecto nuevo del
pipeline de Sala con diagnóstico y parche pendientes distintos de los que se
están validando en esta reparación. Las incidencias de conexión del Despacho
permanecen abiertas con su propio alcance.

No se editaron, comentaron, etiquetaron ni cerraron issues para preparar este
corte. Los estados y las comprobaciones posteriores deben releerse antes de
registrar cumplimiento.
