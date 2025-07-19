import {Carousel} from './Carousel';

/**
 * Initializes carousels on the page.
 * @param elems {NodeList<HTMLElement>} Collection of carousel elements
 */
export function initialzeCarousels(elems) {
    elems.forEach(elem => {
        new Carousel($(elem)).init()
        const elemSlides = elem.querySelectorAll('.slick-slide')
        elemSlides.forEach(slide => {
            const $slide = $(slide)
            if ($slide.attr('aria-describedby') !== undefined) {
                $slide.attr('id',$(this).attr('aria-describedby'));
            }
        })

        window.ILE?.handleNewDom(elem);
    })
}
