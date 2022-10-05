// @ts-check
import { createWorker, createScheduler } from 'tesseract.js';

export default class OCRScanner {
    /**
     * @param {HTMLVideoElement} video
     */
    constructor(video) {
        this.scheduler = createScheduler();
        this.video = video;
        /** @type {number | null} */
        this.timerId = null;
        this.userCanvas = document.createElement('canvas');
        this.userCanvas.width = 1280;
        this.userCanvas.height = 720;
        this.userCanvas.style.maxWidth = '100%';

        this.listeners = {
            /** @type {Array<(isbn: string) => void>} */
            onISBNDetected: []
        }
    }

    /** @param {(isbn: string) => void} callback */
    onISBNDetected(callback) {
        this.listeners.onISBNDetected.push(callback);
    }

    async init() {
        this._initPromise = this._initPromise || this._init();
        await this._initPromise;
    }

    async _init() {
        console.log('Initializing Tesseract.js');
        for (let i = 0; i < 1; i++) {
            const worker = createWorker();
            await worker.load();
            await worker.loadLanguage('eng');
            await worker.initialize('eng');
            this.scheduler.addWorker(worker);
            console.log(`Loaded worker ${i}`);
        }

        console.log('Tesseract.js initialized');

        this.userCanvas.width = this.video.videoWidth;
        this.userCanvas.height = this.video.videoHeight;
    }

    start() {
        if (!this.video.paused) {
            this._startListening();
        }
        this.video.addEventListener('play', this._startListening.bind(this));
        this.video.addEventListener('pause', this._stopListening.bind(this));
    }

    stop() {
        this._stopListening();
        this.video.removeEventListener('play', this._startListening);
        this.video.removeEventListener('pause', this._stopListening);
    }

    _startListening() {
        console.log('watching for ISBNs');
        this.timerId = setInterval(this.doOCR.bind(this), 2500);
    }

    _stopListening() {
        if (this.timerId) {
            clearInterval(this.timerId);
        }
    }

    async doOCR() {
        /** @type {HTMLCanvasElement} */
        const canvas = document.createElement('canvas');
        canvas.width = this.video.videoWidth;
        canvas.height = this.video.videoHeight;
        canvas.getContext('2d').drawImage(this.video, 0, 0, canvas.width, canvas.height);
        if (this.userCanvas.parentElement) {
            this.userCanvas.getContext('2d').drawImage(this.video, 0, 0, 640, 360);
        }
        const { data: { lines } } = await this.scheduler.addJob('recognize', canvas);
        const textLines = lines.map(l => l.text.trim()).filter(line => line);
        console.log(textLines.join('\n'));
        for (const line of textLines) {
            const sanitizedLine = line.replace(/[\s-'.–—]/g, '');
            if (!/\d{2}/.test(sanitizedLine)) continue;
            console.log(sanitizedLine);
            if (sanitizedLine.includes('isbn') || /97[0-9]{10}[0-9x]/i.test(sanitizedLine) || /[0-9]{9}[0-9x]/i.test(sanitizedLine)) {
                const isbn = sanitizedLine.match(/(97[0-9]{10}[0-9x]|[0-9]{9}[0-9x])/i)[0];
                console.log(`ISBN detected: ${isbn}`);
                this.listeners.onISBNDetected.forEach(callback => callback(isbn));
            }
        }
    }
}
