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

        if (!this.$content || !this.$readMoreButton || !this.$readLessButton) {
            return;
        }
        this.collapsedHeight = parseFloat(getComputedStyle(this.$content).maxHeight);
        this.fullHeight = this.$content.scrollHeight;
        this.manuallyExpanded = false;
    }

    attach() {
        this.$readMoreButton.addEventListener('click', this.readMoreClick);
        this.$readLessButton.addEventListener('click', this.readLessClick);
        window.addEventListener('resize', debounce(() => this.reset(), 50));

        this.reset();
    }

    readMoreClick = () => {
        this.expand();
        this.manuallyExpanded = true;
    }

    readLessClick = () => {
        this.collapse();
        this.manuallyExpanded = false;
        if (this.$container.getBoundingClientRect().top < 0) {
            this.$container.scrollIntoView({
                behavior: 'smooth',
                block: 'start',
            });
        }
    }

    expand() {
        this.$container.classList.add('read-more--expanded');
        this.$content.style.maxHeight = `${this.fullHeight}px`;
        this.$readMoreButton.style.display = 'none';
        this.$readLessButton.style.display = 'block';
    }

    collapse() {
        this.$container.classList.remove('read-more--expanded');
        this.$content.style.maxHeight = `${this.collapsedHeight}px`;
        this.$readMoreButton.style.display = 'block';
        this.$readLessButton.style.display = 'none';
    }

    reset() {
        if (!this.$content || !this.$readMoreButton) return;
        this.fullHeight = this.$content.scrollHeight;

        // If content is short enough that it doesn't need to be clamped
        if (this.fullHeight <= this.collapsedHeight + this.$readMoreButton.offsetHeight) {
            this.expand();
            this.$container.classList.add('read-more--unnecessary');
        } else {
            if (!this.manuallyExpanded) {
                this.collapse();
            }
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
