import $ from 'jquery';

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
