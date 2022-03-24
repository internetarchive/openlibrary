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
