/**
 * A lightweight wrapper for enabling a Slick carousel
 */
const Carousel = {
    add: function (selector, a, b, c, d, e, f, loadMore) {
        import(
            /* webpackChunkName: "carousels" */
            './carousels'
        ).then((module) => {
            const carousels = module.default;
            carousels.add(selector, a, b, c, d, e, f, loadMore);
        });
    }
};

export default Carousel;
