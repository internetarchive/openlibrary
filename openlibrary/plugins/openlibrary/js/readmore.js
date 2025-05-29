import { debounce } from './nonjquery_utils.js';

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

        this.collapsedHeight = parseFloat(this.$content.style.maxHeight);
        this.fullHeight = this.$content.scrollHeight;
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
        // scroll top of the read-more container into view if the top is not visible
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
    }

    collapse() {
        this.$container.classList.remove('read-more--expanded');
        this.$content.style.maxHeight = `${this.collapsedHeight}px`;
    }

    reset() {
        this.fullHeight = this.$content.scrollHeight;
        if (this.$readMoreButton && this.$readMoreButton.offsetHeight) {
            this.readMoreHeight = this.$readMoreButton.offsetHeight;
        }
        const collapsedHeight = this.collapsedHeight;
        const readMoreButtonHeight = this.readMoreHeight || 0;

        // Fudge factor to account for non-significant read/more
        // (e.g missing a bit of padding)
        if (this.fullHeight <= (collapsedHeight + readMoreButtonHeight + 1)) {
            this.expand();
            this.$container.classList.add('read-more--unnecessary');
        } else {
            // Don't collapse if the user has manually expanded. Fixes
            // issue where user e.g. presses ctrl-f, triggering a resize
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
