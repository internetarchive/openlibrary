import { createApp } from 'vue';
import LibraryExplorer from './LibraryExplorer.vue';
// We don't actually use this for LibraryExplorer, but if we
// remove it, it causes a runtime error in the browser. 🙃
import AsyncComputed from 'vue-async-computed';

document.addEventListener('DOMContentLoaded', async () => {
    document.querySelectorAll('ol-library-explorer').forEach((el) => {
        const app = createApp(LibraryExplorer);
        app.use(AsyncComputed);
        app.mount(el);
    });
});
