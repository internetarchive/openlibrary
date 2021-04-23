import $ from 'jquery';

const DEFAULT_TIMEOUT = 5000;


export class Toast {
    constructor(message) {
        this.$toast = $(`<div class="toast">
            <span class="toast-message">${message}</span>
            <a class="toast--close">&times;<span class="shift">$_("Close")</span></a>
          </div>
        `);

        this.$toast.find('.toast--close').on('click', () => {
            this.$toast.remove();
        });
    }

    show() {
        $('#test-body-mobile').prepend(this.$toast);

        setTimeout(() => {
            this.$toast.remove();
        }, DEFAULT_TIMEOUT);
    }

    close() {
        this.$toast.remove()
    }
}
