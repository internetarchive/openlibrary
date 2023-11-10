import SwaggerUI from 'swagger-ui';

export function initializeSwaggerUI() {
    const ui = SwaggerUI({
        url: '../../../static/openapi.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
            SwaggerUI.presets.apis,
            SwaggerUI.SwaggerUIStandalonePreset
        ],
        plugins: [
            SwaggerUI.plugins.DownloadUrl
        ],
        layout: 'StandaloneLayout',
    });

    window.ui = ui;
}
