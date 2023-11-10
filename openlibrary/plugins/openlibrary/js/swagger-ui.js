import { SwaggerUIBundle, SwaggerUIStandalonePreset } from 'swagger-ui-dist';

export function initializeSwaggerUI() {
    const ui = SwaggerUIBundle({
        url: '../../../static/openapi.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
            SwaggerUIBundle.presets.apis,
            SwaggerUIStandalonePreset
        ],
        plugins: [
            SwaggerUIBundle.plugins.DownloadUrl
        ],
        layout: 'StandaloneLayout',
    });

    window.ui = ui;
}
