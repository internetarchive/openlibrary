export function initReadMoreButton() { 
    var el, p, up;
    $('.read-more-button').on("click",function(){
        el = $(this);
        p  = el.parent();
        up = p.parent();
        $('.'+up.attr('class')+'-content').removeClass("restricted-height");
        $('.'+up.attr('class')+'.read-more').addClass("hidden");
        $('.'+up.attr('class')+'.read-less').removeClass("hidden");
    });
    $('.read-less-button').on("click",function(){
        el = $(this);
        p  = el.parent();
        up = p.parent();
        $('.'+up.attr('class')+'-content').addClass("restricted-height");
        $('.'+up.attr('class')+'.read-more').removeClass("hidden");
        $('.'+up.attr('class')+'.read-less').addClass("hidden");
    });

    var all, height;
    $(".restricted-view").each(function() {
        height = $(this).outerHeight();
        if(height<100){
            var parent;
            parent = $(this).parent();
            $('.' + parent.attr('class')+'.read-more').addClass("hidden")
        }
        else{
            $(this).addClass("restricted-height");
        }
    });
}
