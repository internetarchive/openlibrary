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
    // document.addEventListener('scroll', function() {
    //     console.log('Scrolling');
    //     if(isElementInViewport(document.getElementsByClassName('editions-table'))){
    //         console.log('In editions-table');
    //         $('.work-menu li').each(function(){
    //             $(this).removeClass('selected');
    //         });
    //         $('.work-menu.view-all-editions').addClass('selected');
    //     }
    //     else if(isElementInViewport(document.getElementsByClassName('work-info'))) {
    //         console.log('In work info');
    //         $('.work-menu li').each(function(){
    //             $(this).removeClass('selected');
    //         });
    //         $('.work-menu.work-details').addClass('selected');
    //     }
    //     else if(isElementInViewport(document.getElementsByClassName('edition-info'))) {
    //         console.log('In editions info');
    //         $('.work-menu li').each(function(){
    //             $(this).removeClass('selected');
    //         });
    //         $('.work-menu.edition-details').addClass('selected');
    //     }
    // });

    // function isElementInViewport(el) {
    //     console.log(el);
    //     var rect = el.getBoundingClientRect();
    //     return rect.bottom > 0 &&
    //         rect.right > 0 &&
    //         rect.left < (window.innerWidth || document.documentElement.clientWidth) /* or $(window).width() */ &&
    //         rect.top < (window.innerHeight || document.documentElement.clientHeight) /* or $(window).height() */;
    // }
}
