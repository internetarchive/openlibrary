export function initReadMoreButton() {
    var el, p, up, height;
    var cls; // eslint-disable-line no-unused-vars

    $('.read-more-button').on('click',function(){
        el = $(this);
        p  = el.parent();
        up = p.parent();
        cls =  up.attr('class'); // eslint-disable-line no-unused-vars
        $('.${cls}-content').removeClass('restricted-height', 300);
        $('.${cls}.read-more').addClass('hidden');
        $('.${cls}.read-less').removeClass('hidden');
    });
    $('.read-less-button').on('click',function(){
        el = $(this);
        p  = el.parent();
        up = p.parent();
        cls =  up.attr('class'); // eslint-disable-line no-unused-vars
        $('.${cls}-content').addClass('restricted-height', 300);
        $('.${cls}.read-more').removeClass('hidden');
        $('.${cls}.read-less').addClass('hidden');
    });
    $('.restricted-view').each(function() {
        height = $(this).outerHeight();
        if (height>50){
            $(this).addClass('restricted-height');
        }
    });
}
