import { debounce } from './nonjquery_utils.js';
import $ from 'jquery';

export class ReadMoreComponent {
    /**
     * @param {HTMLElement} container
     */
    constructor(container) {
        /** @type {HTMLElement} */
        this.$container = container;
        this.$content = container.querySelector('.read-more__content');
        this.$readMoreButton = container.querySelector('.read-more__toggle--more');
        this.$readLessButton = container.querySelector('.read-more__toggle--less');

        this.maxHeight = parseFloat(this.$content.style.height);
    }

    attach() {
        this.$readMoreButton.addEventListener('click', () => this.expand());
        this.$readLessButton.addEventListener('click', () => this.collapse());
        window.addEventListener('resize', debounce(() => this.reset()), 50);

        this.reset();
    }

    expand() {
        this.$container.classList.add('read-more--expanded');
        this.$content.style.height = 'auto';
    }

    collapse() {
        this.$container.classList.remove('read-more--expanded');
        this.$content.style.height = `${this.maxHeight}px`;
    }

    reset() {
        // Fudge factor to account for non-significant read/more
        // (e.g missing a bit of padding)
        if (this.$content.scrollHeight <= (this.maxHeight + 1)) {
            this.expand();
            this.$container.classList.add('read-more--unnecessary');
        } else {
            this.collapse();
            this.$container.classList.remove('read-more--unnecessary');
        }
    }

    static init() {
        for (const el of document.querySelectorAll('.read-more')) {
            new ReadMoreComponent(el).attach();
        }
    }
}

export function initClampers(clampers) {
    for (const clamper of clampers) {
        if (clamper.clientHeight === clamper.scrollHeight) {
            clamper.classList.remove('clamp')
        } else {
            /*
                Clamper shows used to show more/less by toggling `hidden`
                style on parent .clamp tag
            */
            $(clamper).on('click', function (event) {
                const up = $(this);

                // prevent the subjects from collapsing/expanding when the <a> link is being clicked
                if (event.target.nodeName === 'A') {
                    return
                }

                if (up.hasClass('clamp')) {
                    clamper.style.display = clamper.style.display === '-webkit-box' || clamper.style.display === '' ? 'unset' : '-webkit-box'

                    if (up.attr('data-before') === '\u25BE ') {
                        up.attr('data-before', '\u25B8 ')
                    } else {
                        up.attr('data-before', '\u25BE ')
                    }
                }
            })
        }
    }
}
