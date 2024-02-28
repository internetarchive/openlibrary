import {Carousel} from './carousel/Carousel';

export function initCarouselsPartials() {

    const fetchRelatedWorks = function() {
        $.ajax({
            url: '/partials.json',
            type: 'GET',
            data: {
                workid: $('.RelatedWorksCarousel').data('workid'),
                _component: 'RelatedWorkCarousel'
            },
            datatype: 'json',
            success: function (response) {
                $('.loadingIndicator.carousel-loading').addClass('hidden');
                if (response){
                    response = JSON.parse(response)
                    $('.RelatedWorksCarousel').append(response[0]);
                    $('.RelatedWorksCarousel .carousel--progressively-enhanced')
                        .each((_i, el) => new Carousel($(el)).init());
                }
            }
        });
    };

    $('.loadingIndicator.carousel-loading').removeClass('hidden');

    fetchRelatedWorks();
}
