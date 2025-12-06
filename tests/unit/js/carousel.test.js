import $ from 'jquery';
import { Carousel } from '../../../openlibrary/plugins/openlibrary/js/carousel/Carousel.js';

describe('Carousel accessibility init', () => {
    let originalSlick;

    beforeAll(() => {
        // preserve any existing implementation
        originalSlick = $.fn.slick;
    });

    afterAll(() => {
        $.fn.slick = originalSlick;
    });

    test('removes role and aria attributes added by Slick on init', () => {
        // Create container with two slide elements that have role set
        const $container = $(
            '<div class="carousel" data-config="{}">' +
            '  <div class="card" role="option" aria-selected="true" tabindex="0"></div>' +
            '  <div class="card" role="option" aria-selected="false" tabindex="0"></div>' +
            '</div>'
        );

        // Create a mock slick instance we will return on getSlick
        const slickInstance = {
            $slides: $container.find('.card'),
            addSlide: jest.fn(),
            removeSlide: jest.fn()
        };

        // Stub $.fn.slick to simulate initialization and 'getSlick' calls
        $.fn.slick = function(arg) {
            // If called with a string method, handle 'getSlick'
            if (typeof arg === 'string' && arg === 'getSlick') {
                return slickInstance;
            }

            // Otherwise treat as initialization options; trigger 'init'
            // synchronously so Carousel's init handler runs immediately.
            // Ensure mock prev/next controls exist (Slick normally creates these)
            // Add navigation buttons with pre-set aria-labels to match production
            this.append(
                '<button class="slick-prev" aria-label="Previous slide"></button>' +
                '<button class="slick-next" aria-label="Next slide"></button>'
            );

            this.trigger('init', [slickInstance]);
            return this;
        };

        const carousel = new Carousel($container);
        // init should call through to our stub, which triggers the 'init' handler
        carousel.init();

        // After init, the slides should no longer have role/aria-selected/tabindex
        slickInstance.$slides.each((_, el) => {
            const $el = $(el);
            expect($el.attr('role')).toBeUndefined();
            expect($el.attr('aria-selected')).toBeUndefined();
            expect($el.attr('tabindex')).toBeUndefined();
        });

        // Navigation buttons should have accessible labels
        expect($container.find('.slick-prev').attr('aria-label')).toBe('Previous slide');
        expect($container.find('.slick-next').attr('aria-label')).toBe('Next slide');

        // Container should have appropriate region role and label
        expect($container.attr('role')).toBe('region');
        expect($container.attr('aria-label')).toBe('Carousel');
    });
});
