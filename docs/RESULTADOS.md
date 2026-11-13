# Verificaciones locales

Estas comprobaciones se hicieron durante el desarrollo, en Windows con Python
3.12.10, Ollama 0.32.13 y la opción `force_cpu=true`. El equipo de desarrollo tiene
un Ryzen 7 6800H y 63 GB de RAM detectados. **No es la ThinkPad de la exposición**:
estos resultados no garantizan su velocidad ni su consumo de memoria.

## Material y funcionamiento

- Dos PDF, 64 páginas y 173 fragmentos indexados.
- Doce páginas del PDF de sistemas de archivos procesadas mediante OCR.
- Interfaz comprobada en Chrome de escritorio y ventana de 390 píxeles, sin
  desbordamiento horizontal en la pantalla inicial.
- Flujo completo verificado en navegador con la pregunta de mainframes: generación
  local correcta, fuente desplegable y página original visible.
- 41 pruebas automáticas aprobadas, incluyendo conservación del índice al cambiar
  generador, recuperación de continuaciones, caché y rechazo de citas inválidas.
- ZIP extraído en otra carpeta y diagnóstico ejecutado desde esa copia, sin
  copiar el entorno virtual ni depender de rutas absolutas del proyecto original.
- Cambio del generador probado con el mismo índice; no requirió reindexar.

## Evaluación inicial de 20 preguntas

La ejecución inicial con Qwen2.5 1.5B terminó con:

| Comprobación | Resultado |
|---|---|
| Preguntas respondibles cuya recuperación incluyó una página esperada | 17 de 17 |
| Preguntas ajenas al material en las que se abstuvo | 3 de 3 |
| Errores técnicos durante esa ejecución | 0 de 20 |

**Estos números no son exactitud de respuestas.** La revisión del texto encontró
errores: TinyOS se mezclaba con dispositivos mencionados en otros temas, la
comparación de pipes y FIFO añadía una afirmación no respaldada, y una respuesta
sobre funciones de memoria quedaba incompleta. En mainframes se recuperaba la
página correcta pero faltaba el fragmento que enumeraba sus servicios.

Por eso se acortó el prompt a respuestas directas de hasta 65 palabras y se añadió
la continuación del mejor fragmento cuando corta una explicación. En la revisión
focalizada posterior, mainframes, TinyOS, funciones de memoria y componentes del
sistema de archivos respondieron los elementos esperados sin los añadidos
anteriores. La comparación de tiempo real se volvió más corta; sigue necesitando
contraste con el documento para comprobar precisión.

La evaluación inicial completa **no se repitió después de esos cambios**. Para
medir la versión actual, ejecuta `manage.py evaluate` y revisa además las respuestas.

## Límites observados

Hubo cierres intermitentes del runner interno de Ollama fuera de la ejecución
inicial. Se añadió un único reintento con descarga del modelo ante esos fallos.
Una comprobación focalizada de pipes y FIFO volvió a fallar incluso con ese
reintento. La aplicación muestra el error; no fabrica una respuesta para ocultarlo.
Si persiste en el equipo final, reinicia Ollama y vuelve a verificar antes de exponer.

Qwen2.5 0.5B fue más limitado: en la pregunta sobre servicios de mainframes se
abstuvo aunque la lista estaba disponible en el contexto. Se conserva 1.5B como
predeterminado. No presentes 0.5B como calidad equivalente.

Los tiempos medidos en varias consultas con 1.5B estuvieron en decenas de segundos
usando dos hilos de CPU y descarga de modelos entre peticiones. No son un benchmark
controlado ni una estimación para una laptop distinta.

Una demostración defendible debe enseñar la evidencia y reconocer estos límites,
no confundir una cita válida con una afirmación comprobada.

## Corrección de contraste y perfil de laptop (13 de noviembre de 2026)

Se eliminó el fondo blanco fijo de los mensajes, que podía combinarse con texto
blanco al elegir tema oscuro. Los colores de las respuestas y fuentes ahora siguen
el tema activo. Las pruebas de Chrome verifican contraste mínimo 4.5:1 en pregunta,
respuesta y fuentes, en claro y oscuro. Un control negativo reproduce el fondo
blanco anterior y comprueba que la misma medición detecta el contraste insuficiente.
Estas pruebas visuales usan respuestas falsas: no evalúan el LLM.
La comprobación actual pasó 45 pruebas automáticas y dos pruebas de navegador.
La respuesta y el texto de las fuentes midieron aproximadamente 13.47:1 en claro
y 18.11:1 en oscuro; ambas mediciones superan el mínimo 4.5:1 verificado.

La captura del equipo destino muestra i7-1365U, 16 GB de RAM y gráficos integrados.
Se mantiene Qwen 1.5B por CPU, con cuatro hilos configurables y modelos retenidos
hasta cinco minutos para evitar recargas. Se añadió un interruptor para liberar
RAM entre preguntas. Ningún ajuste cambia los vectores ni obliga a reindexar.
No se midió el rendimiento en esa laptop: son ajustes iniciales, no tiempos garantizados.

En la captura quedaban unos 12 GB de almacenamiento libre. Se recomienda liberar
espacio y no instalar herramientas opcionales de OCR o desarrollo en el equipo
destino si se reutiliza el texto ya preparado.
