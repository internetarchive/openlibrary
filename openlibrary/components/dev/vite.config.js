/*
This is the config used for the dev server ala `npm run serve`
This does not effect production builds
*/
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
    plugins: [vue()],
})
