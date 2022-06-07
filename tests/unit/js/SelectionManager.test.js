import SelectionManager from '../../../openlibrary/plugins/openlibrary/js/ile/utils/SelectionManager/SelectionManager.js';

describe('SelectionManager', () => {
    describe('getSelectedItems', () => {
        test('empty', () => {
            document.body.innerHTML = `
            <ul>
                <li class="searchResultItem ile-selectable" itemscope="" itemtype="https://schema.org/Book" draggable="true">
                    <h3 itemprop="name" class="booktitle">
                        <a itemprop="url" href="/works/OL15000194W?edition=ia%3Awintersongpoem00shak" class="results">The Long Run</a>
                    </h3>
                </li>
            </ul>`;
            const sm = new SelectionManager();
            expect(sm.getSelectedItems()).toEqual([]);
        });

        test('has selected', () => {
            document.body.innerHTML = `
            <ul>
                <li class="searchResultItem ile-selectable ile-selected" itemscope="" itemtype="https://schema.org/Book" draggable="true">
                    <h3 itemprop="name" class="booktitle">
                        <a itemprop="url" href="/works/OL15000194W?edition=ia%3Awintersongpoem00shak" class="results">The Long Run</a>
                    </h3>
                </li>
                <li class="searchResultItem ile-selectable" itemscope="" itemtype="https://schema.org/Book" draggable="true">
                    <h3 itemprop="name" class="booktitle">
                        <a itemprop="url" href="/works/OL15000194W?edition=ia%3Awintersongpoem00shak" class="results">The Long Run</a>
                    </h3>
                </li>
            </ul>`;
            const sm = new SelectionManager(null, '/search');
            expect(sm.getSelectedItems()).toEqual(['OL15000194W']);
        });
    });
});
