# Cuaderno: asistente local de Sistemas Operativos

Proyecto de Inteligencia Artificial: preguntas sobre documentos del curso mediante
**RAG (Retrieval-Augmented Generation)**. Busca evidencia en PDF, genera una
respuesta en español y muestra archivo, página y fragmentos usados.

**No se entrena un modelo. No usa API de pago. No busca en Internet.**
El navegador muestra la interfaz; Python, Chroma y Ollama trabajan en tu laptop.

## Inicio rápido: Windows

Necesitas **Python 3.12 de 64 bits** y **Ollama actualizado**. No necesitas GPU.
Recomendado: 8 GB de RAM o más y varios GB de disco libre para dependencias y modelos.
Con 4 GB no se garantiza funcionamiento; prueba el generador de 0.5B.
Los tamaños de descarga NO equivalen al consumo de RAM.

1. Instala [Python 3.12](https://www.python.org/downloads/) y [Ollama](https://ollama.com/download).
2. Extrae el ZIP o clona el repositorio (ver sección siguiente).
3. En la carpeta del proyecto, ejecuta `instalar.bat`. También puedes usar PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

4. Abre la aplicación Ollama. En otra terminal descarga:

```powershell
ollama pull embeddinggemma
ollama pull qwen2.5:1.5b
```

5. Ejecuta `iniciar.bat`, o:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

6. Abre **http://127.0.0.1:8501**. Pulsa **Preparar documentos** y espera.
   El primer índice tarda más; después se reutiliza.
7. Haz una pregunta y abre **Fuentes de la respuesta**. Puedes ver la página original.

No hace falta activar el entorno virtual ni cambiar políticas de ejecución de PowerShell.
La app no descarga modelos automáticamente. Internet sólo hace falta para instalar
dependencias/modelos; después puedes consultar sin conexión.

## Pasarlo a la laptop de tu compañero

### Opción A: ZIP, sin Git (la más rápida)

En tu computadora:

```powershell
.\.venv\Scripts\python.exe empaquetar.py
```

Comparte **`dist/Cuaderno-SO.zip`** por USB o tu medio habitual. Tu compañero debe
extraerlo y seguir **Inicio rápido**. No ejecutes la app dentro del ZIP.

El ZIP incluye código, PDF y texto preparado con OCR. No incluye entorno virtual,
modelos, configuraciones locales ni índice vectorial: cada laptop instala sus
dependencias, descarga modelos y construye su índice. No copies `.venv` entre PCs.

### Opción B: Git y GitHub

Repositorio **privado**: https://github.com/ProtoFurOwO/cuaderno-so

Para darle acceso a tu compañero, abre **Settings → Collaborators → Add people**
en GitHub, invítalo con su usuario y pídele que acepte la invitación antes de clonar.
Debe autenticarse con su propia cuenta; no compartas contraseñas ni tokens.

Los documentos y sus textos extraídos pueden estar sujetos a derechos del
profesor/editorial. No hagas público el repositorio sin permiso. Se incluyen PDF
y `data/prepared/`; `.venv`, `data/index/`, `config.local.toml` y secretos quedan
excluidos. Los modelos de Ollama se descargan por separado.

En la laptop de tu compañero, instala [Git](https://git-scm.com/downloads), Python
y Ollama. Dale acceso al repositorio privado y luego:

```powershell
git clone https://github.com/ProtoFurOwO/cuaderno-so.git
cd cuaderno-so
.\instalar.bat
ollama pull embeddinggemma
ollama pull qwen2.5:1.5b
.\iniciar.bat
```

Pulsa **Preparar documentos**. Para recibir actualizaciones después:

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

Si tienes cambios propios, resuélvelos antes de actualizar; no uses comandos de
restablecimiento que borren tu trabajo. Cierra la app antes de actualizar paquetes.

## Cambiar el LLM sin romper el proyecto

### Desde la interfaz: sólo esta sesión

```powershell
ollama pull qwen2.5:0.5b
```

En la barra lateral pulsa **Actualizar conexión y modelos** y selecciónalo en
**Modelo que responde**. No borres el índice y no cambies embeddings.
Modelos nuevos deben admitir chat y salida JSON estructurada en Ollama.

### Cambio permanente por laptop

Crea **`config.local.toml`** en la raíz con este contenido. No copies encima
todo `config.toml`: sólo incluye los valores que quieras cambiar.

```toml
[ollama]
generation_model = "qwen2.5:0.5b"
```

Reinicia la app. Este archivo no se sube a Git ni viaja en el ZIP; cada laptop
elige su modelo. Para volver, usa `qwen2.5:1.5b` o elimina sólo esa opción local.
La versión 0.5B ahorra recursos pero puede responder peor o incumplir el formato.
En una prueba local rechazó una pregunta de mainframes aun teniendo la respuesta
en el contexto. Para exponer, conserva **1.5B** si el equipo lo permite; 0.5B es
un recurso de emergencia, no una sustitución equivalente.

También puedes hacer una prueba desde terminal sin cambiar archivos:

```powershell
.\.venv\Scripts\python.exe manage.py ask "¿Para qué sirve chmod?" --model qwen2.5:0.5b
```

| Cambio | ¿Reconstruir índice? |
|---|---|
| `generation_model` | **No** |
| `embedding_model` o su versión/digest | **Sí** |
| PDF, texto preparado, tamaño/solapamiento de fragmentos | **Sí** |
| Umbral, cantidad de resultados, temperatura o límites de generación | No |

Nunca mezcles embeddings de modelos distintos aunque tengan la misma dimensión.
La app detecta cambios y bloquea consultas hasta reconstruir cuando corresponde.
Sólo cambiar el nombre del generador no cambia los vectores existentes.

## Configuración y rendimiento

Prioridad: `config.toml` < `config.local.toml` < variables de entorno:
`LLM_MODEL`, `EMBEDDING_MODEL`, `OLLAMA_BASE_URL`.

Predeterminados:
- Embeddings: `embeddinggemma:latest`, 300M; descarga aproximada 622 MB.
- Generador: `qwen2.5:1.5b`, Q4_K_M; descarga aproximada 986 MB.
- `force_cpu = true`: usa CPU incluso si esta PC tiene GPU, para probar portabilidad.
- `num_threads = 4`: cuatro hilos por petición, configurables en `config.local.toml`.
  Contexto máximo de 4096 tokens.
- `keep_alive = "5m"`: conserva los modelos cargados hasta cinco minutos entre
  peticiones para evitar recargas. Es el perfil inicial para el i7-1365U con 16 GB
  de RAM del equipo destino; no es un benchmark ni garantiza tiempos de respuesta.
- Si falta RAM, activa **Ahorrar RAM entre preguntas** en la barra lateral:
  libera cada modelo al terminar. Para conservar esa elección entre sesiones,
  establece `keep_alive = "0"` en `config.local.toml`. Ahorra memoria, pero recargar
  los modelos aumenta latencia. También puedes bajar `num_threads` a 2.
- Durante la construcción del índice se conserva sólo el modelo de embeddings
  entre fragmentos y se libera al terminar si `keep_alive="0"`. Se procesa un
  fragmento por petición para reducir picos de RAM y evitar fallos de lotes en Windows.
  Los vectores ya calculados se guardan por contenido y digest del modelo: un fallo
  intermedio no obliga a volver a calcularlos. Ante un cierre del runner interno
  de Ollama se intenta una sola recuperación; otros errores se muestran sin bucle.
- Cuatro fragmentos, hasta 4200 caracteres de texto total y 384 tokens de salida.
- Si el mejor fragmento corta una explicación, se incorpora su continuación en
  la misma página dentro del límite de cuatro resultados. Su similitud se calcula
  con el vector almacenado; no se inventa una puntuación.
- Umbral coseno inicial 0.40. **No es probabilidad de acierto ni umbral universal**;
  evalúalo con preguntas reales. Si lo cambias, vuelve a medir abstenciones.

Evita contextos enormes y respuestas largas en laptops antiguas. Cierra juegos,
otros modelos y pestañas innecesarias. Prueba en el equipo final antes de exponer:
los tiempos de una PC distinta no predicen los de la ThinkPad.

La laptop de destino tiene CPU i7-1365U, 16 GB de RAM y gráficos integrados:
se mantiene Qwen 1.5B por CPU; no hace falta instalar el modelo 0.5B ni otro
embedding. En la captura quedaban unos 12 GB de disco libre. **Conviene liberar
espacio hasta tener al menos 20 GB disponibles**, para dejar margen a Windows,
dependencias y cachés de instalación. No instales OCR ni paquetes de desarrollo
en esa laptop si vas a reutilizar los PDF ya preparados.

Las respuestas y fuentes usan los colores del tema activo de Streamlit, tanto
claro como oscuro. Si actualizas desde una versión con texto invisible, cierra
la terminal de la app con `Ctrl+C`, ejecuta `git pull --ff-only`, abre de nuevo
`iniciar.bat` y recarga el navegador con `Ctrl+F5`. No hace falta reconstruir el índice.

## Material y OCR

Se detectan PDF en la raíz y dentro de `documents/`. El DOCX de seguridad se conserva
sin modificar, pero **no se indexa**. Puedes añadir PDF desde la interfaz.

Los PDF del curso tienen 36 y 28 páginas. El segundo mezcla texto seleccionable
y páginas escaneadas. `data/prepared/` guarda extracción por página identificada
por SHA-256 del PDF, incluyendo método y páginas pendientes.

El texto preparado puede viajar en el repo/ZIP; no necesita OCR en la laptop destino
si se conservan los mismos PDF. **No edites el PDF ni renombres su ruta después
de indexar sin reconstruir.** Se conserva el número físico de página del PDF (base 1).

Para material nuevo con páginas escaneadas, instala OCR opcional:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
.\.venv\Scripts\python.exe manage.py prepare --ocr
.\.venv\Scripts\python.exe manage.py build
```

También puedes marcar **OCR para páginas escaneadas** antes de preparar desde la app.
RapidOCR funciona por CPU y no requiere instalar Tesseract. El OCR automático puede
perder acentos, tablas y diagramas; revisa las páginas originales. No es un modelo
multimodal: sólo se busca el texto extraído. Las advertencias de cobertura son
heurísticas, no una garantía de extracción perfecta.

## Diagnóstico y pruebas

```powershell
.\.venv\Scripts\python.exe manage.py doctor
.\.venv\Scripts\python.exe manage.py ask "¿Qué diferencia hay entre un pipe y un FIFO?"
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Prueba visual de contraste opcional para desarrollo (requiere Chrome):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
$env:RUN_BROWSER_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests/test_browser.py -q
Remove-Item Env:RUN_BROWSER_TESTS
```

Esta prueba usa respuestas falsas para aislar la interfaz, abre los temas claro
y oscuro y exige contraste de al menos 4.5:1 en pregunta, respuesta y fuentes.
No mide calidad del LLM ni necesita Ollama.

`evaluation/questions.json` contiene 20 casos con páginas/respuestas de referencia,
incluyendo preguntas sin respuesta y una instrucción para ignorar documentos.

```powershell
.\.venv\Scripts\python.exe manage.py evaluate --retrieval-only
.\.venv\Scripts\python.exe manage.py evaluate
```

Resultados en `data/evaluation-results*.json` (no se suben a Git). El script mide
aciertos de recuperación por página, abstención fuera de alcance y errores. **No
califica automáticamente exactitud ni fidelidad semántica**: compara respuestas
con evidencia y referencias esperadas manualmente. Las páginas esperadas no siempre
son las únicas que podrían contener evidencia válida.

## Si algo falla

| Problema | Solución |
|---|---|
| No conecta con Ollama | Abre Ollama; o ejecuta `ollama serve` en otra terminal. Si ya está activo no inicies otro servidor. |
| `ollama` no reconocido | Instálalo y abre una terminal nueva. |
| Falta un modelo | Ejecuta el `ollama pull NOMBRE` que indica el error. |
| Equipo sin RAM / respuesta lenta | Prueba Qwen 0.5B, cierra apps y mantén `keep_alive="0"`. |
| Respuesta truncada | Sube `max_answer_tokens` a 512 o cambia generador; puede aumentar consumo/latencia. |
| JSON/citas inválidos | La app rechaza esa respuesta. Prueba Qwen 1.5B u otro modelo compatible. |
| Índice desactualizado | Pulsa **Preparar documentos**. No hace falta borrar carpetas. |
| Pregunta sin respuesta pese a existir en PDF | Revisa OCR, fragmentos recuperados y umbral. Reformula con términos del curso. |
| Falta información de una imagen | Ejecuta OCR; diagramas complejos pueden seguir fuera del alcance. |
| Error instalando paquetes | Usa Python 3.12 de 64 bits, no Python 3.14. Revisa espacio y conectividad. |

## Estructura

```text
app.py                     Interfaz Streamlit
manage.py                  CLI: doctor, prepare, build, ask, evaluate
config.toml                Valores predeterminados
config.local.toml           Ajustes propios (opcional, ignorado por Git)
asistente/config.py        Carga y validación de configuración
asistente/documents.py     PDF, OCR, fragmentación y carga segura
asistente/ollama_client.py  Embeddings y generación mediante HTTP local
asistente/index.py         Persistencia, búsqueda e invalidación de Chroma
asistente/pipeline.py      RAG, abstención y validación de referencias
data/prepared/             Texto portátil; incluye material del curso
data/index/                Base vectorial local; no se comparte por Git
evaluation/questions.json  Evaluación sobre páginas reales
docs/EXPOSICION.md         Guion y explicación técnica
tests/                     Pruebas automáticas sin descargar modelos
```

## Alcances, privacidad y licencias

La configuración predeterminada usa `127.0.0.1`: ni app ni Ollama se exponen a la red.
Si cambias `base_url` por un servidor remoto, **le enviarás los fragmentos y preguntas**;
ya no será procesamiento totalmente local. No abras estos puertos a Internet.
No incluyas credenciales en documentos ni subas secretos al repositorio.

No hay garantía de cero alucinaciones. Se comprueba que los IDs de las citas
pertenezcan al contexto recuperado; esto **no demuestra** que cada afirmación esté
respaldada. El asistente puede repetir errores del material o del OCR.
Cada pregunta es independiente: el historial es visual, no memoria del modelo.
No se incluyen cuentas, despliegue multiusuario, navegación web ni entrenamiento.

Respeta las licencias de modelos, bibliotecas y documentos. EmbeddingGemma usa los
términos de Gemma, Qwen2.5 1.5B indica Apache 2.0 y PyMuPDF tiene condiciones
AGPL/comerciales. No se relicencian los PDF del curso.

Referencias de modelos:
- https://ollama.com/library/embeddinggemma
- https://ai.google.dev/gemma/docs/embeddinggemma/model_card
- https://ollama.com/library/qwen2.5:1.5b

Resultados y límites de las verificaciones locales: [docs/RESULTADOS.md](docs/RESULTADOS.md).
