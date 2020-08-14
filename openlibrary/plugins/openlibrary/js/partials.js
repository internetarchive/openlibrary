export function initPartials() {
    jQuery(window).load(function () {
        $.ajax({
            url: '/partials',
            type: 'GET',
            data: {
                workid: $('.RelatedWorksCarousel').attr('workId'),
                _component: true
            },
            datatype: 'json',
            success: function (response) {
                $('.RelatedWorksCarousel').append(response[0]);
            }
        });
    });
}
