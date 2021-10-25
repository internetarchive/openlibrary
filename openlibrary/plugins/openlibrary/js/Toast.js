// @ts-check
import $ from 'jquery';
import '../../../../static/css/components/toast.less';

/**
 * @constant {number} Default amount of time to display a toast component, in milliseconds.
 */
const DEFAULT_TIMEOUT = 2500;

export class Toast {
    /**
     * @param {JQuery} $toast The element containing the appropriate parts
     * @param {JQuery|HTMLElement} containerParent where to add the toast bar
     */
    constructor($toast, containerParent=document.body) {
        const $parent = $(containerParent);
        if (!$parent.has('.toast-container').length) {
            $parent.prepend('<div class="toast-container"></div>')
        }
        if ($toast.data('toast-trigger')) {
            $($toast.data('toast-trigger')).on('click', () => this.show());
        }
        /** The toast bar that the toast will be added to. */
        this.$container = $parent.children('.toast-container').first();
        this.$toast = $toast;
    }

    /** Displays the toast component on the page. */
    show() {
        this.$toast
            .appendTo(this.$container)
            .fadeIn();
        this.$toast.find('.toast__close')
            .one('click', () => this.close());
    }

    /** Hides the toast component and removes it from the DOM. */
    close() {
        this.$toast.fadeOut('slow', () => this.$toast.remove());
    }
}

/**
 * Creates a small pop-up message that closes after some amount of time.
 */
export class FadingToast extends Toast {
    /**
     * Creates a new toast component, adds a close listener to the component, and adds the component
     * as the first child of the given parent element.
     *
     * @param {string} message Message that will be displayed in the toast component
     * @param {JQuery} [$parent] Designates where the toast component will be attached
     * @param {number} [timeout] Amount of time, in milliseconds, that the component will be visible
     */
    constructor(message, $parent=null, timeout=DEFAULT_TIMEOUT) {
        super(
            // TODO(i18n-js)
            $(`<div class="toast">
                <span class="toast__body">${message}</span>
                <a class="toast__close">&times;<span class="shift">Close</span></a>
            </div>`),
            $parent
        );
        this.timeout = timeout;
    }

    /** @override */
    show() {
        super.show();

        setTimeout(() => {
            this.close();
        }, this.timeout);
    }
}
