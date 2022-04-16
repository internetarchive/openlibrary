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
    $('.restricted-view').each(function() {
        if ($(this).outerHeight()<50) {
            $(`.${$(this).parent().attr('class')}.read-more`).addClass('hidden');
        } else {
            $(this).addClass('restricted-height');
        }
    });
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
            $(clamper).on('click', function(event) {
                const up = $(this);
            if (event.target.nodeName=="A"){
                return
            }
            else{
                
                if (up.hasClass('clamp')) {
                    up.css({display: up.css('display') === '-webkit-box' ? 'unset' : '-webkit-box'});

                    if (up.attr('data-before') === '\u25BE ') {
                        up.attr('data-before', '\u25B8 ')
                    } else {
                        up.attr('data-before', '\u25BE ')
                    }
                }
                }
            })
        }
    }
}
