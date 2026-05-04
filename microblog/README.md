# microblog/

Source of truth del HTML+JS de páginas custom servidas en micro.blog.

## fotos-page.html

Renderiza la galería de `/fotos/` consumiendo `https://fotos.impermanente.es/feed.json`
(las 30 últimas). Cada card tiene caption (alt-text o content), ubicación + fecha,
y enlaza a `https://fotos.impermanente.es/foto/{status_id}/` (no a Pixelfed).

### Cómo desplegarlo en micro.blog

1. micro.blog → Design → Edit Pages → seleccionar `/fotos/` (o crear si no existe).
2. **Reemplazar TODO el contenido** de la página por el de `fotos-page.html`.
3. Guardar. micro.blog regenera el sitio (~30s).
4. Verificar visualmente en `https://impermanente.es/fotos/`:
   - Galería se renderiza con las 30 últimas fotos.
   - Cada card muestra alt-text + "Ciudad, País · fecha".
   - Click va a `https://fotos.impermanente.es/foto/{status_id}/`.

### Workflow al modificar el template

1. Editar `microblog/fotos-page.html` en este repo.
2. Commit + push (el cron no toca esto; esta pieza es solo template).
3. Copy-paste manual a micro.blog UI.
4. Anotar en el commit message si el cambio requiere paso manual posterior.

### Bug conocido: HTML entity decoding en `<script>`

micro.blog **decodifica entidades HTML dentro de `<script>`** antes de servir
la página. Eso significa que `&amp;` literal en el JS se convertiría en `&` y
puede romper la sintaxis. Reglas defensivas aplicadas en `fotos-page.html`:

- No usar entidades HTML literales (`&amp;`, `&quot;`, `&lt;`, etc.) dentro de strings JS.
- Para escape HTML dinámico: `document.createElement('div').textContent = value` y leer `div.innerHTML`.
- Si en algún momento hace falta `&` literal en JS, construirlo con `String.fromCharCode(38)`.

### Cache

`?cb=Date.now()` se añade al fetch del feed para evitar caché del navegador.
GitHub Pages CDN sirve el feed con `cache-control: max-age=600`, así que el
peor caso es ver feed con hasta 10 min de retraso tras cada cron.
