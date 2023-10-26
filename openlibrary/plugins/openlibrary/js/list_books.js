export class ListBooks {
    /**
     * @param {HTMLElement} listBooks
     * @param {HTMLElement} layoutToolbar
     **/
    constructor(listBooks, layoutToolbar) {
        this.listBooks = listBooks;
        this.layoutToolbar = layoutToolbar;

        this.activeLayout = this.layoutToolbar.querySelector('a.active');
    }

    attach() {
        $(this.layoutToolbar).on('click', 'a', this.updateLayout.bind(this));
    }

    /**
     * @param {MouseEvent} event
     */
    updateLayout(event) {
        event.preventDefault();
        const layoutAnchor = event.target;
        this.layoutToolbar.querySelector('a.active').classList.remove('active');
        layoutAnchor.classList.add('active');
        const layout = layoutAnchor.dataset.value;
        this.listBooks.classList.toggle('list-books--grid', layout === 'grid');
        document.cookie = `LIST_BOOKS_LAYOUT=${layout}; path=/; max-age=31536000`;
    }

    static init() {
        // Assume only one list-books/layout per page
        new ListBooks(
            document.querySelector('.list-books'),
            document.querySelector('.tools--layout'),
        ).attach();
    }
}
