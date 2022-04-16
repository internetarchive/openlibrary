const websocket = require('websocket');
const WebSocketServer = websocket.server;
const http = require('http');

class AutoReloadServer {
    port = 9292;

    httpServer = http.createServer(function(request, response) {
        console.log((new Date().toISOString()) + ' Received request for ' + request.url);
        response.writeHead(404);
        response.end();
    });

    wsServer = new WebSocketServer({
        httpServer: this.httpServer,
        autoAcceptConnections: false
    });

    /** @type {Set<websocket.connection>} */
    wsConnections = new Set();

    start() {
        this.httpServer.listen(this.port, () => {
            console.log(`${new Date().toISOString()} Server is listening on port ${this.port}`);
        });
        this.httpServer.on('request', this.onHTTPRequest.bind(this));
        this.wsServer.on('request', this.onWSRequest.bind(this));
    }

    /**
     * @param {http.IncomingMessage} request
     * @param {http.ServerResponse} response
     */
    onHTTPRequest(request, response) {
        if (request.method === 'GET' && request.url === '/reload') {
            this.broadcastReload();
            response.writeHead(200);
        }
        else {
            response.writeHead(404);
        }
    }

    /**
     * @param {string} origin
     */
    isValidOrigin(origin) {
        return origin.startsWith('http://localhost') || origin.endsWith('.gitpod.io');
    }

    /**
     * @param {websocket.request} request
     */
    onWSRequest(request) {
        if (!this.isValidOrigin(request.origin)) {
            // Make sure we only accept requests from an allowed origin
            request.reject();
            console.log(`${new Date().toISOString()} Connection from origin ${request.origin} rejected.`);
            return;
        }

        const connection = request.accept(null, request.origin);
        this.wsConnections.add(connection);
        console.log(`${new Date().toISOString()} Connection accepted.`);
        connection.on('close', () => {
            this.wsConnections.delete(connection);
            console.log(`${new Date().toISOString()} Connection closed.`);
        });
    }

    broadcastReload() {
        for (const connection of this.wsConnections) {
            try {
                connection.sendUTF('reload');
            } catch (e) {
                console.error(`${new Date().toISOString()} Error sending reload message to ${connection.remoteAddress}: ${e}`);
            }
        };
    }
}

new AutoReloadServer().start();
