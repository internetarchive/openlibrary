import {Carousel} from "./carousel/Carousel";

export function initLazyCarousel(elems) {
    // Create intersection observer
    const intersectionObserver = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const target = entry.target
                intersectionObserver.unobserve(target)
                const config = JSON.parse(target.dataset.config)
                fetchPartials(config)
                    .then(resp => resp.json())
                    .then(data => {
                        const newElem = document.createElement("div")
                        newElem.innerHTML = data.partials.trim()
                        target.parentNode.insertBefore(newElem, target)
                        target.remove()
                        const $carouselElements = $(newElem.querySelector('.carousel--progressively-enhanced'))
                        $carouselElements.each((_i, el) => new Carousel($(el)).init())
                        $(newElem.querySelectorAll('.slick-slide')).each(function () {
                            if ($(this).attr('aria-describedby') !== undefined) {
                                $(this).attr('id', $(this).attr('aria-describedby'));
                            }
                        })
                    })
            }
        })
    }, {
        root: null,
        rootMargin: "200px",
        threshold: 0
    })

    elems.forEach(elem => intersectionObserver.observe(elem))
}

async function fetchPartials(data) {
    const searchParams = new URLSearchParams({...data, _component: "LazyCarousel"})
    return fetch(`/partials.json?${searchParams.toString()}`)
}
