import {matchSmallMediumCovers, matchLargeCovers} from '../../../openlibrary/plugins/openlibrary/js/service-worker-matchers';

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
