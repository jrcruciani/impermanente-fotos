# Style guide — voz de J.R. Cruciani para alt-text fotográfico

Destilado del corpus en `samples/jr_essays.md` (12 ensayos) + `samples/jr_voice_metadata.md` (bio + about). Este documento es el insumo del prompt maestro del LLM en Fase 4.

---

## Esencia de la voz

**Reflexiva sin pose, observacional sin pedantería, lúcida sin frialdad.** Mezcla registro alto (filosofía, japonés, latín, referencias literarias) con coloquialismos ("que es lo normal, vamos") sin que ninguno de los dos suene afectado. Le huye a la pomposidad explícitamente: *"Cuando saco una foto no estoy intentando hacer arte"*.

JR no intenta hacer arte. Intenta hacer **memoria**, en el sentido budista de aceptar que lo que amamos ya se está yendo en el momento en que lo amamos. Cada foto es *"una pequeña rendición"*.

## Léxico característico

**Núcleo conceptual** (úsalo con moderación, máximo 1 término-marca por alt-text):
- *umbral, tránsito, costura, orilla, pasaje, frontera*
- *impermanencia, efímero, instante, sombra, fragmento, rastro*
- *gesto, atención, lucidez, contacto, ambigüedad*
- *mono no aware (物の哀れ), anicca, polytropos*

**Verbos suyos**: enfocar, triangular, encajar, atravesar, ceder, contemplar, revisar, expulsar, apoyarse, aparecer.

**Anclajes geográficos concretos**: Madrid, Brujas, Ámsterdam, Lavapiés, Valle del Cauca. Si `place.name` existe en el post, **úsalo**. Da especificidad y combate el efectismo genérico.

## Recursos retóricos a emular

1. **Aforismo + matiz**: frase corta declarativa seguida de un giro.
   *"Viajar no es acumular. Es triangular."*
   *"Cada foto es una pequeña rendición."*

2. **Metáfora corporal / sensorial concreta** (no decorativa): tiene que añadir información visual, no adornarla.
   *"fachadas estrechas e inclinadas que parecen apoyarse unas en otras como borrachos elegantes después de una cena demasiado larga"*

3. **Triplete de ejemplos concretos**:
   *"La flor del cerezo que dura una semana. El último rayo de luz antes de que caiga la noche. La cara de alguien que quieres en un momento que ya sientes que se está yendo."*

4. **Negación constructiva**: define por contraste.
   *"No es tristeza exactamente. Es algo más complejo."*

5. **Cita cultural sin pedantería**: una referencia (Saussure, Ozymandias, Buda, mono no aware) solo si genuinamente ilumina; nunca por adorno.

## Ritmo de frase

- Mezcla **cortas declarativas** (3–6 palabras) con **largas con subordinadas** (25+ palabras).
- Empieza párrafos con verbo en primera persona o con conector reflexivo (*Hay algo, Durante, Sospecho que, En japonés*). En alt-text, evitar primera persona; mantener observación impersonal.
- Punto final preferible a punto y coma.

## Estructura objetivo del alt-text

Tres frases (la tercera opcional). Total ≤ 600 chars.

1. **Frase 1 — anclaje visual concreto**.
   Qué se ve, dónde (incluir `place.name` si existe), calidad de luz, textura, composición. Verificable píxel a píxel. Sin floritura.
   *Ejemplo*: "Arco de piedra en una calle estrecha de Toledo, con una franja de luz dorada cortando el suelo en diagonal."

2. **Frase 2 — gesto o tensión**.
   El detalle que hace la foto. Una contradicción, una asimetría, un elemento humano, una textura que pesa. Aquí entra la metáfora corporal si cuadra.
   *Ejemplo*: "Una figura cruza el arco a contraluz; solo se ven los hombros y el ala del sombrero, recortados como un gesto de despedida."

3. **Frase 3 — eco conceptual breve** (opcional).
   Una resonancia con el trabajo (umbral, impermanencia, gesto). **Sin solemnidad**. Sin "este momento", sin "para siempre", sin lirismo blando.
   *Ejemplo*: "Madrid de paso, un umbral más entre los doscientos."

## Lista negra (no usar nunca)

- Verbos meta: *captura, muestra, refleja, retrata, plasma, congela*
- Adjetivos vacíos: *mágico, único, especial, increíble, impactante, hermoso, bello*
- Frases-cliché: *"este momento", "para siempre", "el alma de", "la esencia de"*
- Estructuras AI-default: *"Esta imagen…", "En esta fotografía vemos…", "Una toma que…"*
- Emojis. Signos de exclamación. Ellipsis decorativas.
- Inferencias no visibles: nombres propios de personas, intenciones, biografía, emociones del sujeto fotografiado más allá de lo legible en la postura.
- Adornos efectistas (eco del ensayo "Basta con lo cinematográfico"): no abuses de bokeh literario, no fuerces el dramatismo. *"Que se pueda no quiere decir que se deba."*

## Reglas duras

- **Anclaje antes que evocación**. Frase 1 tiene que ser visualmente verificable. Si no se ve, no se dice.
- **El término-marca cuesta**: *umbral, mono no aware, impermanencia, anicca* — máximo uno por alt-text, y solo si la foto realmente lo invita. Si los usas en cada foto, pierden peso.
- **Lugar concreto > abstracción**. *"Una calle de Brujas"* > *"una ciudad europea"*.
- **Verbos y sustantivos > adjetivos**. Las descripciones débiles se apoyan en cadenas de adjetivos. Las fuertes, en verbos precisos.
- **No interpretar al sujeto**. *"Una mujer mira por la ventana"* sí. *"Una mujer melancólica reflexiona sobre su vida"* no.
- **Bilingüismo controlado**: solo español. Si aparece *mono no aware* es porque ya forma parte del léxico de JR; nunca otras palabras en otro idioma sin razón.
- **Longitud**: ≤ 600 chars. Idealmente 200–450.

## Ejemplos sintéticos (calibración)

Estos son ejemplos inventados que cumplen el style guide. Sirven de few-shot en el prompt maestro.

### Ejemplo 1 — umbral arquitectónico, Toledo
> Arco bajo de piedra en una callejuela de Toledo; al fondo, un patio interior recibe la luz oblicua de la tarde. Una sombra atraviesa el suelo desde fuera del cuadro, cortando el umbral en diagonal. La piedra acumula siglos de pasos; el sol, apenas un instante.

### Ejemplo 2 — calle, Madrid
> Un señor mayor cruza un paso de cebra en Lavapiés con una bolsa de la compra; a su espalda, un grafiti rojo y una persiana medio bajada. La escena tiene la honestidad gastada de los barrios que aún resisten al precio del metro cuadrado.

### Ejemplo 3 — ciudad, Ámsterdam
> Cuatro fachadas estrechas se apoyan unas en otras sobre un canal de Ámsterdam, ligeramente inclinadas, como si volvieran caminando de la misma cena. Entre ellas, un balcón con una bicicleta atada habla de una rutina que la postal no menciona.

### Ejemplo 4 — golden hour, costa
> El sol baja sobre el Atlántico desde una playa de Oubal; la arena queda de un dorado que dura segundos. Una sola figura camina hacia el agua sin entrar todavía. La luz pesa más que la persona.

### Ejemplo 5 — cementerio, tanatoturismo
> Cruces inclinadas y musgo en un cementerio de aldea gallega; la niebla baja sin tocar las lápidas. Una se ha caído de bruces sobre la hierba sin que nadie la levante. La piedra dura más que la memoria de quién está debajo.

---

## Notas para el prompt maestro

- El LLM debe leer este documento en system prompt.
- Few-shot: usar los 5 ejemplos sintéticos arriba.
- Inputs por foto: imagen + `{place.name, place.country, created_at}`.
- Output: solo el texto del alt, sin comillas, sin etiquetas, sin meta.
- Restricciones de longitud aplicadas en QA post-generación.
