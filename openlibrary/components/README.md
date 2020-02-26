Files in the root directory are pre-rendered and added to `/static/build/components/`.  These components can be rendered from template files like so:

```html
$:render_component('MergeUI', olids="['OL123W']")
```

The building of these files happens on `make components`
