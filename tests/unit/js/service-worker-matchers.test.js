import { matchMiscFiles, matchSmallMediumCovers, matchLargeCovers, matchStaticImages, matchStaticBuild, matchArchiveOrgImage } from '../../../openlibrary/plugins/openlibrary/js/service-worker-matchers';


// Helper function to create a URL object
function _u(url) {
    return { url: new URL(url) }
}
// Group related tests together
describe('URL Matchers', () => {
    describe('matchMiscFiles', () => {
        test('matches miscellaneous files', () => {
            expect(matchMiscFiles(_u('https://openlibrary.org/favicon.ico'))).toBe(true);
            expect(matchMiscFiles(_u('https://openlibrary.org/static/manifest.json'))).toBe(true);
        });

        test('does not match homepage', () => {
            expect(matchMiscFiles(_u('https://openlibrary.org/'))).toBe(false);
        });
    });

    describe('matchSmallMediumCovers', () => {
        test('matches small and medium cover sizes', () => {
            expect(matchSmallMediumCovers(_u('https://covers.openlibrary.org/a/id/6257045-M.jpg'))).toBe(true);
            expect(matchSmallMediumCovers(_u('https://covers.openlibrary.org/a/id/6257045-S.jpg'))).toBe(true);
            expect(matchSmallMediumCovers(_u('https://covers.openlibrary.org/b/id/1852327-M.jpg'))).toBe(true);
            expect(matchSmallMediumCovers(_u('https://covers.openlibrary.org/a/olid/OL2838765A-M.jpg'))).toBe(true);
        });

        test('does not match large covers', () => {
            expect(matchSmallMediumCovers(_u('https://covers.openlibrary.org/a/id/6257045-L.jpg'))).toBe(false);
        });
    });

    describe('matchLargeCovers', () => {
        test('matches large cover sizes', () => {
            expect(matchLargeCovers(_u('https://covers.openlibrary.org/a/id/6257045-L.jpg'))).toBe(true);
        });

        test('does not match small or medium covers', () => {
            expect(matchLargeCovers(_u('https://covers.openlibrary.org/a/id/6257045-S.jpg'))).toBe(false);
            expect(matchLargeCovers(_u('https://covers.openlibrary.org/a/id/6257045-M.jpg'))).toBe(false);
            expect(matchLargeCovers(_u('https://covers.openlibrary.org/a/id/6257045.jpg'))).toBe(false);
        });
    });

    describe('matchStaticImages', () => {
        test('matches static images', () => {
            expect(matchStaticImages(_u('https://openlibrary.org/static/images/down-arrow.png'))).toBe(true);
            expect(matchStaticImages(_u('https://testing.openlibrary.org/static/images/icons/barcode_scanner.svg'))).toBe(true);
        });

        test('does not match other URLs', () => {
            expect(matchStaticImages(_u('https://openlibrary.org/static/build/4290.a0ae80aacde14696d322.js'))).toBe(false);
            expect(matchStaticImages(_u('https://covers.openlibrary.org/w/id/14348537-L.jpg'))).toBe(false);
        });
    });

    describe('matchStaticBuild', () => {
        test('matches static build files', () => {
            expect(matchStaticBuild(_u('https://openlibrary.org/static/build/4290.a0ae80aacde14696d322.js'))).toBe(true);
            expect(matchStaticBuild(_u('https://testing.openlibrary.org/static/build/page-book.css?v=097b69dc350c972d96da0c70cebe7b75'))).toBe(true);
        });

        test('does not match localhost or gitpod URLs', () => {
            expect(matchStaticBuild(_u('http://localhost:8080/static/build/4290.a0ae80aacde14696d322.js'))).toBe(false);
            expect(matchStaticBuild(_u('https://8080-internetarc-openlibrary-feliyig0grl.ws-eu110.gitpod.io/static/build/4290.a0ae80aacde14696d322.js'))).toBe(false);
        });
    });

    describe('matchArchiveOrgImage', () => {
        test('matches archive.org images', () => {
            expect(matchArchiveOrgImage(_u('https://archive.org/services/img/@raybb'))).toBe(true);
            expect(matchArchiveOrgImage(_u('https://archive.org/services/img/courtofmistfury0000maas'))).toBe(true);
        });

        test('does not match other URLs', () => {
            expect(matchArchiveOrgImage(_u('https://archive.org/services/'))).toBe(false);
        });
    });
});
