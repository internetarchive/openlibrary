import $ from 'jquery';

import { Carousel } from '../../../openlibrary/plugins/openlibrary/js/carousel/Carousel';

vi.mock('slick-carousel', () => ({}));

const flushPromises = () => new Promise(resolve => setTimeout(resolve, 0));

function makeSlides(count, activeCount = 3) {
    const slides = Array.from({ length: count }, (_, index) => {
        const slide = document.createElement('div');
        if (index < activeCount) {
            slide.classList.add('slick-active');
        }
        return slide;
    });
    return $(slides);
}

describe('Carousel', () => {
    let carousel;
    let slick;

    beforeEach(() => {
        document.body.innerHTML = `
            <input type="hidden" name="carousel-i18n-strings" value='{"loading":"Loading..."}'>
            <div
                class="carousel carousel--progressively-enhanced"
                data-config='{
                    "loadMore": {
                        "queryType": "SUBJECTS",
                        "q": "subject:science",
                        "pageMode": "offset",
                        "limit": 18,
                        "key": "science"
                    }
                }'
            >
                <div class="carousel__item"></div>
                <div class="carousel__item"></div>
                <div class="carousel__item"></div>
                <div class="carousel__item"></div>
                <div class="carousel__item"></div>
                <div class="carousel__item"></div>
            </div>
        `;

        slick = {
            $slides: makeSlides(6),
            addSlide: vi.fn(() => {
                slick.$slides = makeSlides(slick.$slides.length + 1);
            }),
            removeSlide: vi.fn(() => {
                slick.$slides = makeSlides(slick.$slides.length - 1);
            })
        };

        $.fn.slick = vi.fn(function(arg) {
            if (arg === 'getSlick') {
                return slick;
            }
            return this;
        });

        carousel = new Carousel($('.carousel'));
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    test('unlocks and removes the loading slide when loading more cards fails', async() => {
        const request = $.Deferred();
        $.ajax = vi.fn(() => request.promise());
        carousel.loadMore.locked = true;

        carousel.fetchPartials();
        request.reject(new Error('Request failed'));
        await flushPromises();

        expect(slick.addSlide).toHaveBeenCalledWith('<div class="carousel__item carousel__loading-end">Loading...</div>');
        expect(slick.removeSlide).toHaveBeenCalledWith(6);
        expect(carousel.loadMore.locked).toBe(false);
        expect(carousel.loadMore.allDone).toBe(false);
    });

    test('uses i18n strings from data-config, even without the hidden input', async() => {
        document.querySelector('input[name="carousel-i18n-strings"]').remove();
        document.querySelector('.carousel').dataset.config = JSON.stringify({
            i18n: { loading: 'Cargando...' },
            loadMore: {
                queryType: 'SUBJECTS',
                q: 'subject:science',
                pageMode: 'offset',
                limit: 18,
                key: 'science'
            }
        });
        carousel = new Carousel($('.carousel'));
        const request = $.Deferred();
        $.ajax = vi.fn(() => request.promise());
        carousel.loadMore.locked = true;

        carousel.fetchPartials();
        request.reject(new Error('Request failed'));
        await flushPromises();

        expect(slick.addSlide).toHaveBeenCalledWith('<div class="carousel__item carousel__loading-end">Cargando...</div>');
        expect(carousel.loadMore.locked).toBe(false);
    });

    test('does not remain locked when the i18n input is missing', async() => {
        document.querySelector('input[name="carousel-i18n-strings"]').remove();
        carousel = new Carousel($('.carousel'));
        const request = $.Deferred();
        vi.spyOn($, 'ajax').mockReturnValue(request.promise());
        carousel.loadMore.locked = true;

        expect(() => carousel.fetchPartials()).not.toThrow();
        request.reject(new Error('Request failed'));
        await flushPromises();

        expect(carousel.loadMore.locked).toBe(false);
        expect(carousel.loadMore.allDone).toBe(false);
    });

    test('makes shelf buttons in hidden slides inert, and frees them again when shown', async() => {
        carousel = new Carousel($('.carousel'));
        carousel.init();
        const container = document.querySelector('.carousel');
        container.innerHTML = `
            <div class="slick-slide" aria-hidden="false"><ol-shelf-button variant="icon"></ol-shelf-button></div>
            <div class="slick-slide" aria-hidden="true"><ol-shelf-button variant="icon"></ol-shelf-button></div>
        `;
        await flushPromises();
        const [shown, hidden] = container.querySelectorAll('ol-shelf-button');
        expect(shown.hasAttribute('inert')).toBe(false);
        expect(hidden.hasAttribute('inert')).toBe(true);

        // The slide scrolls into view: slick flips aria-hidden.
        hidden.parentElement.setAttribute('aria-hidden', 'false');
        await flushPromises();
        expect(hidden.hasAttribute('inert')).toBe(false);
    });

    describe('cursor page mode', () => {
        beforeEach(() => {
            document.querySelector('.carousel').dataset.config = JSON.stringify({
                loadMore: {
                    queryType: 'LIST',
                    q: '/people/curator/lists/OL1L',
                    pageMode: 'cursor',
                    page: 20,
                    limit: 20,
                    key: 'list'
                }
            });
            carousel = new Carousel($('.carousel'));
        });

        function respondWith(response) {
            const request = $.Deferred();
            $.ajax = vi.fn(() => request.promise());
            return () => request.resolve(response);
        }

        test('starts from the seed offset the server rendered', () => {
            expect(carousel.loadMore.page).toBe(20);
        });

        test('does not infer the offset from the number of slides', () => {
            carousel.init();
            $.ajax = vi.fn(() => $.Deferred().promise());

            // 6 slides are on screen, but the server consumed 20 seeds to render them
            slick.$slides = makeSlides(6);
            $('.carousel').trigger('afterChange', [slick, 3]);

            expect(carousel.loadMore.page).toBe(20);
            expect($.ajax.mock.calls[0][0].url.searchParams.get('page')).toBe('20');
        });

        test('resumes from the offset in the response', async() => {
            const resolve = respondWith({ partials: ['<div></div>'], nextOffset: 40 });
            carousel.loadMore.locked = true;

            carousel.fetchPartials();
            resolve();
            await flushPromises();

            expect(carousel.loadMore.page).toBe(40);
            expect(carousel.loadMore.allDone).toBe(false);
            expect(carousel.loadMore.locked).toBe(false);
        });

        test('is done when the response has no next offset', async() => {
            const resolve = respondWith({ partials: ['<div></div>'], nextOffset: null });
            carousel.loadMore.locked = true;

            carousel.fetchPartials();
            resolve();
            await flushPromises();

            expect(carousel.loadMore.allDone).toBe(true);
            expect(carousel.loadMore.locked).toBe(false);
        });

        test('keeps going when a page of seeds has no cards, instead of stalling', async() => {
            const responses = [
                { partials: [], nextOffset: 40 },
                { partials: ['<div></div>'], nextOffset: null }
            ];
            $.ajax = vi.fn(() => $.Deferred().resolve(responses.shift()).promise());
            carousel.loadMore.locked = true;

            carousel.fetchPartials();
            await flushPromises();
            await flushPromises();

            expect($.ajax).toHaveBeenCalledTimes(2);
            expect($.ajax.mock.calls[1][0].url.searchParams.get('page')).toBe('40');
            expect(carousel.loadMore.allDone).toBe(true);
        });
    });

    test('offset mode still starts the next request from the last slide', () => {
        carousel.init();
        $.ajax = vi.fn(() => $.Deferred().promise());

        slick.$slides = makeSlides(6);
        $('.carousel').trigger('afterChange', [slick, 3]);

        expect(carousel.loadMore.page).toBe(6);
    });
});
