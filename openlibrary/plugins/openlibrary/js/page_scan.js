import Quagga from 'quagga';

export function init() {
    Quagga.init({
        inputStream : {
            name: "Live",
            type: "LiveStream",
            target: $('#interactive')[0],
        },
        decoder: {
            readers: ["ean_reader"]
        },
    }, function(err) {
        if (err) {
            console.log(err);
            return
        }
        Quagga.start();
    });

    Quagga.onProcessed(function(result) {
        const drawingCtx = Quagga.canvas.ctx.overlay;
        const drawingCanvas = Quagga.canvas.dom.overlay;

        if (result) {
            if (result.boxes) {
                drawingCtx.clearRect(0, 0, parseInt(drawingCanvas.getAttribute("width")), parseInt(drawingCanvas.getAttribute("height")));
                result.boxes
                .filter(box => box !== result.box)
                .forEach(box => {
                    Quagga.ImageDebug.drawPath(box, {x: 0, y: 1}, drawingCtx, {color: "green", lineWidth: 2});
                });
            }

            if (result.box) {
                Quagga.ImageDebug.drawPath(result.box, {x: 0, y: 1}, drawingCtx, {color: "blue", lineWidth: 2});
            }

            if (result.codeResult && result.codeResult.code) {
                Quagga.ImageDebug.drawPath(result.line, {x: 'x', y: 'y'}, drawingCtx, {color: 'red', lineWidth: 15});
            }
        }
    });

    let lastResult = null;
    Quagga.onDetected(function(result) {
        const code = result.codeResult.code;

        if (code.startsWith('97') && lastResult !== code) {
            console.log(code);
        
            lastResult = code;
            var $node = null, canvas = Quagga.canvas.dom.image;

            $node = $(`
            <li>
                <a class="thumbnail">
                    <img />
                    <div class="caption">
                        <span class="code"></span>
                    </div>
                </a>
            </li>`.trim());
            $node.find("img").attr("src", canvas.toDataURL());
            $node.find("a").attr('href', `/isbn/${code}`);
            $node.find(".code").text(code);
            $("#result-strip ul.thumbnails").prepend($node);
        }
    });
};
