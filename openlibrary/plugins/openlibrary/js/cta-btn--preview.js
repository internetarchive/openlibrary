import 'jquery-colorbox';

export function init() {
    // Colorbox modal + iframe for Book Preview Button
    const $buttons = $('.cta-btn--preview');
    $buttons.each((i, button) => {
        const $button = $(button);
        $button.colorbox({
            width: '100%',
            maxWidth: '640px',
            inline: true,
            opacity: '0.5',
            href: '#bookPreview',
            onOpen() {
                const $iframe = $('#bookPreview iframe');
                $iframe.prop('src', $button.data('iframe-src'));

                const $link = $('#bookPreview .learn-more a');
                $link[0].href = $button.data('iframe-link');
            },
            onCleanup() {
                $('#bookPreview iframe').prop('src', '');
            },
        });
    });
}
