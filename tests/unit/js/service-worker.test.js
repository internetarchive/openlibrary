import {matchMiscFiles, matchSmallMediumCovers, matchLargeCovers, matchStaticImages, matchStaticBuild} from '../../../openlibrary/plugins/openlibrary/js/service-worker-matchers';


test('matchMiscFiles', () => {
    expect(matchMiscFiles({url: new URL('https://openlibrary.org/static/favicon.ico')})).toBe(true);
    expect(matchMiscFiles({url: new URL('https://openlibrary.org/')})).toBe(false);
})


test('matchSmallMediumCovers', () => {
    // Test for author covers
    expect(matchSmallMediumCovers({url: new URL('https://covers.openlibrary.org/a/id/6257045-M.jpg')})).toBe(true);

    // Test for random dot images
    expect(matchSmallMediumCovers({url: new URL('https://covers.openlibrary.org/a/olid/OL2838765A-M.jpg')})).toBe(true);

    // Test for book covers
    expect(matchSmallMediumCovers({url: new URL('https://covers.openlibrary.org/b/id/1852327-M.jpg')})).toBe(true);

    // Test for redirects to Internet Archive with a 302
    // Note: This test assumes you have a way to simulate or check for a 302 redirect.
    // If not, you might need to adjust this test based on your testing environment's capabilities.
    expect(matchSmallMediumCovers({url: new URL('https://covers.openlibrary.org/w/id/14348537-M.jpg')})).toBe(true);

    // Test localhost case (will also apply to Gitpod and other domains)
    expect(matchSmallMediumCovers({url: new URL('http://localhost:7075/a/id/1-M.jpg')})).toBe(true);

    // Negative cases
    expect(matchSmallMediumCovers({url: new URL('https://openlibrary.org')})).toBe(false);
    expect(matchSmallMediumCovers({url: new URL('http://localhost:7075/a/id/1-L.jpg')})).toBe(false);
    expect(matchSmallMediumCovers({url: new URL('http://localhost:7075/a/id/1.jpg')})).toBe(false);
});


test('matchLargeCovers', () => {
    // Test for author covers
    expect(matchLargeCovers({url: new URL('https://covers.openlibrary.org/a/id/6257045-L.jpg')})).toBe(true);

    // Test for random dot images
    expect(matchLargeCovers({url: new URL('https://covers.openlibrary.org/a/olid/OL2838765A-L.jpg')})).toBe(true);

    // Test for book covers
    expect(matchLargeCovers({url: new URL('https://covers.openlibrary.org/b/id/1852327-L.jpg')})).toBe(true);

    // Test for redirects to Internet Archive with a 302
    // Note: This test assumes you have a way to simulate or check for a 302 redirect.
    // If not, you might need to adjust this test based on your testing environment's capabilities.
    expect(matchLargeCovers({url: new URL('https://covers.openlibrary.org/w/id/14348537-L.jpg')})).toBe(true);

    // Test localhost case (will also apply to Gitpod and other domains)
    expect(matchLargeCovers({url: new URL('http://localhost:7075/a/id/1-L.jpg')})).toBe(true);


    // Negative cases
    expect(matchLargeCovers({url: new URL('https://openlibrary.org')})).toBe(false);
    expect(matchLargeCovers({url: new URL('http://localhost:7075/a/id/1-S.jpg')})).toBe(false);
    expect(matchLargeCovers({url: new URL('http://localhost:7075/a/id/1-M.jpg')})).toBe(false);
    expect(matchLargeCovers({url: new URL('http://localhost:7075/a/id/1.jpg')})).toBe(false);
});


test('matchStaticImages', () => {
    expect(matchStaticImages({url: new URL('https://openlibrary.org/static/images/down-arrow.png')})).toBe(true);
    expect(matchStaticImages({url: new URL('https://testing.openlibrary.org/static/images/icons/barcode_scanner.svg')})).toBe(true);
    expect(matchStaticImages({url: new URL('https://openlibrary.org/images/menu.png')})).toBe(true);
    expect(matchStaticImages({url: new URL('http://localhost:8080/images/menu.png')})).toBe(true);


    // Negative cases
    expect(matchStaticImages({url: new URL('https://openlibrary.org')})).toBe(false);
    expect(matchStaticImages({url: new URL('https://openlibrary.org/stsaatic/images/down-arrow.png')})).toBe(false);
    expect(matchStaticImages({url: new URL('https://covers.openlibrary.org/w/id/14348537-L.jpg')})).toBe(false);
    expect(matchStaticImages({url: new URL('http://localhost:7075/a/id/1-M.jpg')})).toBe(false);
    expect(matchStaticImages({url: new URL('http://localhost:7075/a/id/1.jpg')})).toBe(false);
});


test('matchStaticBuild', () => {

    // Positive cases
    // It should work on js
    expect(matchStaticBuild({url: new URL('https://openlibrary.org/static/build/4290.a0ae80aacde14696d322.js')})).toBe(true);
    // It should work on js with versions
    expect(matchStaticBuild({url: new URL('https://openlibrary.org/static/build/all.js?v=e2544bd4947a7f4e8f5c34684df62659')})).toBe(true);
    // It should work on testing
    expect(matchStaticBuild({url: new URL('https://testing.openlibrary.org/static/build/page-book.css?v=097b69dc350c972d96da0c70cebe7b75')})).toBe(true);

    // Negative cases
    // We don't want it caching localhost or gitpod
    expect(matchStaticBuild({url: new URL('http://localhost:8080/static/build/4290.a0ae80aacde14696d322.js')})).toBe(false);
    expect(matchStaticBuild({url: new URL('https://8080-internetarc-openlibrary-feliyig0grl.ws-eu110.gitpod.io/static/build/4290.a0ae80aacde14696d322.js')})).toBe(false);
    expect(matchStaticBuild({url: new URL('https://openlibrary.org')})).toBe(false);
});
