import '../static/css/components/buttonCta.less';
import '../static/css/components/buttonCta--js.less';

export default {
    title: 'Legacy/Button'
};

const ButtonTemplate = (classes,innerHtml) => `<div class="${classes}">${innerHtml}</div>`;

export const CtaBtn = () => ButtonTemplate('cta-btn','Leave waitlist');

export const CtaBtnUnavailable = () => ButtonTemplate('cta-btn cta-btn--unavailable','Join waitlist');

export const CtaBtnAvailable = () => ButtonTemplate('cta-btn cta-btn--available','Borrow');

export const CtaBtnPreview = () => ButtonTemplate('cta-btn cta-btn--preview','Preview');

export const CtaBtnWithBadge = () =>
    ButtonTemplate('cta-btn cta-btn--unavailable',
        `Join waiting list
    <span class="cta-btn__badge">4</span>`)
;

export const CtaBtnGroup = () => `<div class="cta-button-group">
<a href="/borrow/ia/sevenhabitsofhi00cove?ref=ol" title="Borrow ebook from Internet Archive" id="borrow_ebook" data-ol-link-track="CTAClick|Borrow" class="cta-btn cta-btn--available">Borrow</a>
<a href="/borrow/ia/sevenhabitsofhi00cove?ref=ol&amp;_autoReadAloud=show" title="Borrow ebook from Internet Archive using Read Aloud" data-ol-link-track="CTAClick|BorrowListen" class="cta-btn cta-btn--available">
  <span class="btn-icon read-aloud"></span>
  <span class="btn-label">Listen</span>
</a>
</div>
`;
