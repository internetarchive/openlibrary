import {Carousel} from './carousel/Carousel';

export function initCarouselsPartials() {
    const carousels = document.querySelectorAll('.RelatedWorksCarousel');

    const fetchRelatedWorks = function(carouselElement) {
        const loadingIndicator = carouselElement.querySelector('.loadingIndicator.carousel-loading');
        loadingIndicator.classList.remove('hidden');

        $.ajax({
            url: '/partials.json',
            type: 'GET',
            data: {
                workid: carouselElement.dataset.workid,
                _component: 'RelatedWorkCarousel'
            },
            datatype: 'json',
            success: function (response) {
                loadingIndicator.classList.add('hidden');
                if (response) {
                    response = JSON.parse(response);
                    carouselElement.insertAdjacentHTML('beforeend', response[0]);
                    carouselElement.querySelectorAll('.carousel--progressively-enhanced')
                        .forEach(el => new Carousel($(el)).init());
                }
            }
        });
    };

    // Fallback for browsers without Intersection Observer
    const fallbackLoadCarousels = () => {
        carousels.forEach(carousel => fetchRelatedWorks(carousel));
    };

    // Check if Intersection Observer is supported
    if ('IntersectionObserver' in window) {
        const observerOptions = {
            root: null,
            rootMargin: '200px',
            threshold: 0
        };

        const observerCallback = (entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    fetchRelatedWorks(entry.target);
                    observer.unobserve(entry.target);
                }
            });
        };

        const observer = new IntersectionObserver(observerCallback, observerOptions);

        carousels.forEach(carousel => {
            // Handle anchor link navigation
            if (window.location.hash && window.location.hash === `#${carousel.id}`) {
                fetchRelatedWorks(carousel);
            } else {
                observer.observe(carousel);
            }
        });
    } else {
        // Fallback for older browsers
        fallbackLoadCarousels();
    }
}
