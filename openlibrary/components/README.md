Files in the root of this directory are compiled and added to `/static/build/components/`.  These components can be rendered from template files like so:

```html
$:render_component('HelloWorld', attrs=dict(name="Jimmy"))
```

The building of these files happens on `make components`.

## Live-reloading dev server

First, update `openlibrary/components/dev.js` to use the component you're developing instead of `HelloWorld.vue`
Then, outside the docker environment, run: 

```shell script
npx @vue/cli-service serve openlibrary/components/dev.js
```

## Caveats

- Currently does not support IE11 because it's using web components (See https://caniuse.com/custom-elementsv1 )
- Vue is currently included with each component, so rendering multiple components per page results in very large load sizes
- JSON attributes currently don't work
- If Vue is embedded within a `<form>` input elments created by vue won't be picked up on form submission.
This seems to be related to Vue's use of shadow dom. For a workaround, see the code in [#5093](https://github.com/internetarchive/openlibrary/pull/5093).

## Examples

For an example of using Vue on existing pages see `openlibrary/components/AuthorIdentifiers.vue`
