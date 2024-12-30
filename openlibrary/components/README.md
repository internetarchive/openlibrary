Files in the root of this directory are compiled and added to `/static/build/components/`.  These components can be rendered from template files like so:

```html
$:render_component('HelloWorld', attrs=dict(name="Jimmy"))
```

The building of these files happens on `make components`.

## Live-reloading dev server

The Vue components follow the following structure:

```
openlibrary/components/{MainComponent}.vue  -- The entrypoint to the component
openlibrary/components/{MainComponent}/...  -- Any sub components, utils, etc.
```

**Outside the docker environment**, run:

```shell script
npm install --no-audit
npm run serve --component=HelloWorld
```

Changing `HelloWorld` to be the name of the main component you want to work on.

For apps that are configured for it (like `LibraryExplorer` and `MergeUI`), when run
in this mode, the vue server will make requests to production openlibrary.org
for data like books, search results, covers, etc. You can configure where it fetches data
from by setting url parameters on the running app, eg `?ol_base=http://localhost:8080`. See
`openlibrary/components/configs.js` for all the available url parameters.

## Caveats

- Currently does not support IE11 because it's using web components (See https://caniuse.com/custom-elementsv1 )
- Vue is currently included with each component, so rendering multiple components per page results in very large load sizes
- JSON attributes currently don't work
- If Vue is embedded within a `<form>` input elements created by vue won't be picked up on form submission.
This seems to be related to Vue's use of shadow dom. For a workaround, see the code in [#5093](https://github.com/internetarchive/openlibrary/pull/5093).

## Examples

For an example of using Vue on existing pages see `openlibrary/components/IdentifiersInput.vue`
