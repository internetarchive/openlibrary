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
- If Vue is embedded within a `<form>` input elements created by vue won't be picked up on form submission.
This seems to be related to Vue's use of shadow dom. For a workaround, see the code in [#5093](https://github.com/internetarchive/openlibrary/pull/5093).

## Examples

For an example of using Vue on existing pages see `openlibrary/components/AuthorIdentifiers.vue`


# Vue 3 Migration

This is the working directory for Open Library's Vue 3 migration.  Much like the /openlibrary/components directory, this will contain the migrated source code for our Vue 3 component library.

Currently, the directory contains a blend of Vue 2 and Vue 3 components.  The Vue 2 components and associated files were copied from /openlibrary/components. In order to avoid build failures, the Vue 2 directories were hidden and the file extension for the root components was changed to `.vue2`.

More information about how to migrate components can be found in the migration [section](#migrating-components)

## Building the Components
Since our Vue 2 build tool, Vue CLI, is in maintenance mode, Vite is being used to compile our components.
Our components are now being compiled into a single file as a library (previously, each component had its own file). This library is imported by our main JS initialization code, where the custom components are registered.  Currently, all components are registered on every page, but we can easily register only what is necessary for the page.

Vite build configuration can be found in the `vite.config.js` file, found in the repo's root directory.
### Build Steps
Components can be built by running the following in the web container:
`npm run build-assets:vue`

Because our JS is now dependent on the library produced by the component build, we have to build our components before our JS.  The `build-assets` script has been updated accordingly.

### Build Notes
- Vue custom element [guide](https://vuejs.org/guide/extras/web-components.html)
- Vite library mode [guide](https://vitejs.dev/guide/build.html#library-mode)
- Vite library build option [documentation](https://vitejs.dev/config/build-options.html#build-lib)

## Changes to `render_component()`
Components are still rendered as expected by calling the `render_component` function:

```html
$:render_component('HelloWorld', attrs=dict(name="Jimmy"))
```

`render_component` no longer renders the Vue library and the component's script as `<script>` tags.  It now only formats the attribute string and renders the custom element tag.

## Migrating Components
Here's a small migration checklist:
- [ ] Remove `.` from component's directory name
- [ ] Change extension of each Vue file to `.ce.vue`
- [ ] Upgrade or replace any external Vue libraries used by the component
- [ ] Upgrade paths of any imported Open Library JS code
- [ ] Replace any `Vue` API calls (`Vue.set()`, `Vue.delete()`, etc.)
- [ ] Uncomment the component's import and registration code in `/openlibrary/components/index.js`
- [ ] Build and test

Here's a list of [breaking changes](https://v3-migration.vuejs.org/breaking-changes/) that may be helpful.
