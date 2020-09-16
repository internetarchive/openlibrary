import 'slick-carousel';
import '../../../../static/css/components/carousel--js.less';
import Carousel from './carousel/Carousel';

export function initCarouselsPartials() {
    $('.loadingIndicator').removeClass('hidden');
    jQuery(window).load(function () {
        $.ajax({
            url: '/partials',
            type: 'GET',
            data: {
                workid: $('.RelatedWorksCarousel').attr('workId'),
                _component: 'RelatedWorkCarousel'
            },
            datatype: 'json',
            success: function (response) {
                $('.loadingIndicator').addClass('hidden');
                if (response){
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
    });
}
