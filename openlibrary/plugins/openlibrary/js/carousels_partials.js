import 'slick-carousel';
import '../../../../static/css/components/carousel--js.less';
import Carousel from './carousel/Carousel';

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
                $('.loadingIndicator').addClass('hidden');
                if (response){
                    response = JSON.parse(response)
                    $('.RelatedWorksCarousel').append(response[0]);
                    const $carouselElements = $('.RelatedWorksCarousel .carousel--progressively-enhanced');
                    if ($carouselElements.length) {
                        $carouselElements.each(function (_i, carouselElement) {
                            Carousel.add.apply(
                                Carousel,
                                JSON.parse(carouselElement.dataset.config)
                            );
                        });
                    }
                }
            }
        });
    };

    $('.loadingIndicator').removeClass('hidden');

    fetchRelatedWorks();
}
