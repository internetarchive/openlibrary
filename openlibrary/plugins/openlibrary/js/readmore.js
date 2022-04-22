import { debounce } from './nonjquery_utils.js';
import $ from 'jquery';

export function resetReadMoreButtons(){
    $('.restricted-view').each(function() {
        const className = $(this).parent().attr('class');
        // 58 is based on the height attribute of .restricted-height
        if ($(this)[0].scrollHeight <= 58) {
            $(`.${className}.read-more`).addClass('hidden');
            $(`.${className}.read-less`).addClass('hidden');
            $(this).removeClass('restricted-height');
        } else {
            $(`.${className}.read-more`).removeClass('hidden');
            $(`.${className}.read-less`).addClass('hidden');
            $(this).addClass('restricted-height');
        }
    });
}


export function initReadMoreButton() {
    $('.read-more-button').on('click',function(){
        const up = $(this).parent().parent();
        $(`.${up.attr('class')}-content`).removeClass('restricted-height', 300);
        $(`.${up.attr('class')}.read-more`).addClass('hidden');
        $(`.${up.attr('class')}.read-less`).removeClass('hidden');
    });
    $('.read-less-button').on('click',function(){
        const up = $(this).parent().parent();
        $(`.${up.attr('class')}-content`).addClass('restricted-height', 300);
        $(`.${up.attr('class')}.read-more`).removeClass('hidden');
        $(`.${up.attr('class')}.read-less`).addClass('hidden');
    });
    resetReadMoreButtons();
    $(window).on('resize', debounce(resetReadMoreButtons, 50));
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
                    up.css({ display: up.css('display') === '-webkit-box' ? 'unset' : '-webkit-box' });

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
