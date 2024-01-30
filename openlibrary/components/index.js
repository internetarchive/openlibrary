import {defineCustomElement} from 'vue'
import LibraryExplorer from './LibraryExplorer.vue'

main()

async function main() {
    LibraryExplorer.styles = LibraryExplorer.styles || [];
    LibraryExplorer.styles.push(...(await get_styles()).flat());

    customElements.define('ol-library-explorer', defineCustomElement(LibraryExplorer))
}

async function get_styles() {
    const modules = import.meta.glob('./LibraryExplorer/**/*.vue');

    return Promise.all(Object.values(modules).map(module_import => {
        return module_import().then(mode => mode.default.styles)
    }));
}
