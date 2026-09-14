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
});
