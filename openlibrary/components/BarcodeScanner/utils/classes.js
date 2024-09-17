// @ts-check
/* eslint-disable no-console */
import { createWorker, createScheduler } from 'tesseract.js';

export class OCRScanner {
    constructor() {
        this.scheduler = createScheduler();
        /** @type {number | null} */
        this.timerId = null;

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
            const worker = await createWorker();
            await worker.load();
            await worker.loadLanguage('eng');
            await worker.initialize('eng');
            this.scheduler.addWorker(worker);
            console.log(`Loaded worker ${i}`);
        }

        console.log('Tesseract.js initialized');
    }

    /**
     * @param {HTMLCanvasElement} canvas
     */
    async doOCR(canvas) {
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

/**
 * @template {(...args: any) => void} TFunc
 */
export class ThrottleGrouping {
    /**
     * @param {object} param0
     * @param {TFunc} param0.func
     * @param {function(Parameters<TFunc>[]): Parameters<TFunc>} param0.reducer
     * @param {number} param0.wait
     */
    constructor({func, reducer, wait=100}) {
        this.func = func;
        this.reducer = reducer;
        this.wait = wait;
        /** @type {Parameters<TFunc>[]} */
        this.curGroup = [];
        this.timeout = null;
    }

    submitGroup() {
        this.timeout = null;
        this.func(...this.reducer(this.curGroup));
        this.curGroup = [];
    }

    /**
     * @param  {Parameters<TFunc>} args
     */
    takeNext(...args) {
        this.curGroup.push(args);
        if (!this.timeout) {
            this.timeout = setTimeout(this.submitGroup.bind(this), this.wait);
        }
    }

    asFunction() {
        return this.takeNext.bind(this);
    }
}
