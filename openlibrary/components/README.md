Files in the root of this directory are compiled and added to `/static/build/components/`.  These components can be rendered from template files like so:

```html
$:render_component('HelloWorld', olids="['OL123W']")
```

The building of these files happens on `make components`
