import { move_to_work, move_to_author } from '../../../openlibrary/plugins/openlibrary/js/ile/utils/ol.js';

describe('move_to_work', () => {
    const originalFetch = global.fetch;

    afterEach(() => {
        global.fetch = originalFetch;
    });

    it('reports no failures when all PUTs succeed', async() => {
        global.fetch = jest.fn()
            .mockResolvedValueOnce({ json: () => Promise.resolve({ works: [] }) })
            .mockResolvedValueOnce({ ok: true, status: 200 });

        const result = await move_to_work(['OL1M'], 'OL1W', 'OL2W');

        expect(result).toEqual({ total: 1, failed: 0 });
    });

    it('counts PUTs that return a non-successful status as failed and warns', async() => {
        const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
        global.fetch = jest.fn()
            .mockResolvedValueOnce({ json: () => Promise.resolve({ works: [] }) })
            .mockResolvedValueOnce({ ok: false, status: 500 })
            .mockResolvedValueOnce({ json: () => Promise.resolve({ works: [] }) })
            .mockResolvedValueOnce({ ok: true, status: 200 });

        const result = await move_to_work(['OL1M', 'OL2M'], 'OL1W', 'OL2W');

        expect(result).toEqual({ total: 2, failed: 1 });
        expect(warnSpy).toHaveBeenCalledWith('failed to move OL1M; 500');
        warnSpy.mockRestore();
    });
});

describe('move_to_author', () => {
    const originalFetch = global.fetch;

    afterEach(() => {
        global.fetch = originalFetch;
    });

    function workRecord() {
        return { authors: [{ author: { key: '/authors/OL1A' } }] };
    }

    it('reports no failures when all PUTs succeed', async() => {
        global.fetch = jest.fn()
            .mockResolvedValueOnce({ json: () => Promise.resolve(workRecord()) })
            .mockResolvedValueOnce({ ok: true, status: 200 });

        const result = await move_to_author(['OL1W'], 'OL1A', 'OL2A');

        expect(result).toEqual({ total: 1, failed: 0 });
    });

    it('counts PUTs that return a non-successful status as failed and warns', async() => {
        const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
        global.fetch = jest.fn()
            .mockResolvedValueOnce({ json: () => Promise.resolve(workRecord()) })
            .mockResolvedValueOnce({ ok: false, status: 400 })
            .mockResolvedValueOnce({ json: () => Promise.resolve(workRecord()) })
            .mockResolvedValueOnce({ ok: true, status: 200 });

        const result = await move_to_author(['OL1W', 'OL2W'], 'OL1A', 'OL2A');

        expect(result).toEqual({ total: 2, failed: 1 });
        expect(warnSpy).toHaveBeenCalledWith('failed to move OL1W; 400');
        warnSpy.mockRestore();
    });
});
