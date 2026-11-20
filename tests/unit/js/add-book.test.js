import { initAddBookImport, isValidWebBookUrl } from '../../../openlibrary/plugins/openlibrary/js/add-book.js';

describe('isValidWebBookUrl', () => {
    it('returns true for a blank value (field is optional)', () => {
        expect(isValidWebBookUrl('')).toBe(true);
    });
    it('returns true for a whitespace-only value', () => {
        expect(isValidWebBookUrl('   ')).toBe(true);
    });
    it('returns true for a valid http URL', () => {
        expect(isValidWebBookUrl('http://example.com/book.epub')).toBe(true);
    });
    it('returns true for a valid https URL', () => {
        expect(isValidWebBookUrl('https://example.com/book.epub')).toBe(true);
    });

    it('returns false for an unparseable string', () => {
        expect(isValidWebBookUrl('not-a-url')).toBe(false);
    });
    it('returns false for a javascript: scheme URL', () => {
        expect(isValidWebBookUrl('javascript:alert(1)')).toBe(false);
    });
    it('returns false for a mailto: scheme URL', () => {
        expect(isValidWebBookUrl('mailto:a@b.com')).toBe(false);
    });
});

describe('initAddBookImport on the possible-matches page', () => {
    let form;

    function setup({ captcha }) {
        document.body.innerHTML = `
            <form id="addbook" name="edit">
                ${captcha ? '<p id="recaptcha-needed" hidden></p>' : ''}
                <input type="hidden" id="work" name="work" value="none-of-these">
            </form>
            <ul class="list-books"><li id="OL1W"><a href="javascript:;">Match</a></li></ul>
            <button id="bookAddCont">None of these</button>`;
        form = document.getElementById('addbook');
        form.scrollIntoView = vi.fn();
        vi.spyOn(form, 'requestSubmit').mockImplementation(() => {});
        initAddBookImport();
    }

    afterEach(() => {
        delete window.grecaptcha;
        document.body.innerHTML = '';
    });

    it('blocks picking a match until the captcha is solved', () => {
        setup({ captcha: true });
        window.grecaptcha = { getResponse: () => '' };
        document.querySelector('.list-books a').click();
        expect(form.requestSubmit).not.toHaveBeenCalled();
        expect(document.getElementById('recaptcha-needed').hidden).toBe(false);
    });

    it('blocks "none of these" until the captcha is solved', () => {
        setup({ captcha: true });
        window.grecaptcha = { getResponse: () => '' };
        document.getElementById('bookAddCont').click();
        expect(form.requestSubmit).not.toHaveBeenCalled();
    });

    it('blocks when the reCAPTCHA script has not loaded', () => {
        setup({ captcha: true });
        document.querySelector('.list-books a').click();
        expect(form.requestSubmit).not.toHaveBeenCalled();
    });

    it('shows the prompt while the script is half-loaded or the widget never rendered', () => {
        setup({ captcha: true });
        for (const stub of [
            { ready() {} },
            {
                getResponse: () => {
                    throw new Error('No reCAPTCHA clients exist.');
                }
            }
        ]) {
            window.grecaptcha = stub;
            document.getElementById('recaptcha-needed').hidden = true;
            document.querySelector('.list-books a').click();
            expect(form.requestSubmit).not.toHaveBeenCalled();
            expect(document.getElementById('recaptcha-needed').hidden).toBe(false);
        }
    });

    it('submits the picked work once the captcha is solved', () => {
        setup({ captcha: true });
        window.grecaptcha = { getResponse: () => 'token' };
        document.querySelector('.list-books a').click();
        expect(document.getElementById('work').value).toBe('/works/OL1W');
        expect(form.requestSubmit).toHaveBeenCalledOnce();
    });

    it('submits right away for users exempt from the captcha', () => {
        setup({ captcha: false });
        document.getElementById('bookAddCont').click();
        expect(document.getElementById('work').value).toBe('none-of-these');
        expect(form.requestSubmit).toHaveBeenCalledOnce();
    });
});
