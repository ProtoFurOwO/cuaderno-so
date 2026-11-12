# Guion breve de exposición

## Presentación (30 segundos)

“Construimos un asistente para consultar los documentos reales de Sistemas
Operativos. Un modelo genérico puede inventar respuestas o usar información ajena
al curso. Nuestro sistema primero busca evidencia y después redacta con ese contexto.
Todo el procesamiento predeterminado ocurre en la computadora, sin API de pago.”

## Arquitectura (1 minuto)

1. **Procesamiento de texto:** extraemos por página de los PDF. Aplicamos OCR a
   páginas escaneadas. Conservamos archivo, página y método de extracción.
2. **Fragmentación:** bloques de hasta 1000 caracteres con solapamiento de 160;
   se mantienen dentro de cada página para conservar citas claras. El solapamiento
   ayuda a no perder contexto al cortar, aunque puede producir resultados repetidos.
3. **Embeddings:** EmbeddingGemma convierte texto y preguntas en vectores.
   No responde preguntas: representa significado para recuperar contenido.
4. **Base vectorial:** Chroma guarda vectores y metadatos de forma persistente.
   Buscamos mediante distancia coseno y mostramos hasta cuatro fragmentos. Si el
   primero corta una explicación, incorporamos su continuación en la misma página.
   Limitamos el contexto total para reducir consumo.
5. **Prompt engineering:** instrucciones para responder en español, usar sólo
   evidencia y abstenerse si falta información. El contexto documental se trata
   como datos, no como instrucciones para cambiar el comportamiento.
6. **Generación:** Qwen2.5 1.5B cuantizado redacta una respuesta breve. Pedimos
   JSON estructurado y validamos que los identificadores de citas existan.

“Esto es RAG, no fine-tuning: los pesos de los modelos no se modifican. Agregar
documentos cambia el índice, no entrena el LLM.”

## Demostración (2 minutos)

Antes de exponer: abre Ollama, ejecuta la app, comprueba que el índice esté listo,
haz una pregunta de prueba y verifica que los modelos estén descargados.
No construyas el índice por primera vez frente al grupo.

1. Pregunta: **¿Qué diferencia hay entre tiempo real duro y suave?**
   - Referencia: PDF de tipos de SO, página 4.
   - Abre la fuente y la imagen de la página para contrastar.
2. Pregunta: **¿Para qué sirve el comando chmod?**
   - Referencia: PDF de sistemas de archivos, página 6.
   - Explica que cambió el documento recuperado según la pregunta.
3. Pregunta: **¿Qué diferencia hay entre un pipe y un FIFO?**
   - Referencia: PDF de sistemas de archivos, página 17, escaneada.
   - Enseña el indicador OCR y la página original.
4. Pregunta fuera del material: **¿Cuál es la receta de un pastel de chocolate?**
   - Debe abstenerse. No tendría sentido inventar una receta para completar el chat.
5. Abre **Cómo se obtuvo esta respuesta**: similitud coseno, candidatos y tiempos.
   - Similitud no es “porcentaje de confianza”.

Si el sistema se equivoca, muéstralo como limitación real: revisa recuperación,
OCR y respuesta. No presentes una demostración precargada como inferencia en vivo.

## Evaluación

Hay 20 preguntas de referencia: 17 respondibles y 3 fuera del material.
Se mide recuperación de páginas esperadas y abstención; la fidelidad se revisa
manualmente comparando respuestas, fragmentos y PDF original.
No confundir “encontró la página correcta” con “respondió correctamente”.

Puedes ejecutar `manage.py evaluate --retrieval-only` o evaluación completa y
mostrar resultados reales de esa ejecución. No afirmar porcentajes no medidos.

## Preguntas posibles del profesor

**¿Dónde está la inteligencia artificial?**
En las representaciones semánticas de EmbeddingGemma y la generación de Qwen.
La extracción, la persistencia y validación de citas son programación convencional.

**¿Por qué dos modelos?**
Uno está especializado en representar texto para búsqueda; el otro en generar
lenguaje. Cumplen funciones distintas y pueden sustituirse por separado.

**¿Por qué un LLM tan pequeño?**
Buscamos una demostración local sin GPU. Cuantización y contexto limitado reducen
necesidades, a cambio de menor calidad. El rendimiento depende del equipo final.

**¿Se eliminan las alucinaciones?**
No. RAG aporta evidencia y permite inspeccionarla. Umbral, prompt y validación
de citas reducen ciertos fallos, pero no garantizan fidelidad semántica.

**¿Qué pasa si cambia el material?**
Se detecta por hashes; hay que reconstruir el índice. El índice anterior se mantiene
activo hasta completar el nuevo, salvo que el material haya cambiado y ya sea obsoleto.

**¿Y si cambio de modelo?**
Cambiar el generador no cambia los vectores. Cambiar embeddings sí exige regenerarlos;
mezclar espacios vectoriales vuelve inválida la comparación por similitud.

**¿El material contiene errores?**
Puede estar desactualizado. El asistente atribuye respuestas al material del curso;
no lo corrige con información externa ni asegura que sea universalmente verdadero.

**¿Qué mejorarían?**
Mayor evaluación humana, recuperación híbrida con palabras clave, mejor tratamiento
de tablas/diagramas y comparación de modelos bajo presupuesto fijo de RAM/latencia.
