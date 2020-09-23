Files in the root of this directory are compiled and added to `/static/build/components/`.  These components can be rendered from template files like so:

```html
$:render_component('HelloWorld', olids="['OL123W']")
```

The building of these files happens on `make components`


## Caveats

- Currently does not support IE11 because it's using web components (See https://caniuse.com/custom-elementsv1 )
- Vue is currently included with each component, so rendering multiple components per page results in very large load sizes
