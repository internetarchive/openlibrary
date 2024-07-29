import '../static/css/components/buttonCta.less';
import '../static/css/components/buttonCta--js.less';

export default {
  title: 'Legacy/Button'
};

const ButtonTemplate = (buttonType, text, badgeCount=null) => `<div class="cta-btn${ButtonTypes[buttonType]}">${text}${badgeCount ? BadgeTemplate(badgeCount) : ''}</div>`;

const BadgeTemplate = (badgeCount) => ` <span class="cta-btn__badge">${badgeCount}</span>`

const ButtonTypes = {
  default: '',
  unavailable: ' cta-btn--unavailable',
  available: ' cta-btn--available',
  preview: ' cta-btn--shell cta-btn--preview'
}

export const CtaBtn = () => ButtonTemplate('default','Leave waitlist');
CtaBtn.parameters = {
  docs: {
    source: {
      code: ButtonTemplate('default', 'Leave waitlist')
    }
  }
}

export const CtaBtnUnavailable = () => ButtonTemplate('unavailable','Join waitlist');
CtaBtnUnavailable.parameters = {
  docs: {
    source: {
      code: ButtonTemplate('unavailable', 'Join waitlist')
    }
  }
}

export const CtaBtnAvailable = () => ButtonTemplate('available','Borrow');
CtaBtnAvailable.parameters = {
  docs: {
    source: {
      code: ButtonTemplate('available', 'Borrow')
    }
  }
}

export const CtaBtnPreview = () => ButtonTemplate('preview','Preview');
CtaBtnPreview.parameters = {
  docs: {
    source: {
      code: ButtonTemplate('preview', 'Preview')
    }
  }
}

export const CtaBtnWithBadge = () =>
  ButtonTemplate('unavailable','Join waiting list',4);
CtaBtnWithBadge.parameters = {
  docs: {
    source: {
      code: ButtonTemplate('unavailable', 'Join waiting list', 4)
    }
  }
}

export const CtaBtnGroup = () => `<div class="cta-button-group">
<a href="/borrow/ia/sevenhabitsofhi00cove?ref=ol" title="Borrow ebook from Internet Archive" id="borrow_ebook" data-ol-link-track="CTAClick|Borrow" class="cta-btn cta-btn--available">Borrow</a>
<a href="/borrow/ia/sevenhabitsofhi00cove?ref=ol&amp;_autoReadAloud=show" title="Borrow ebook from Internet Archive using Read Aloud" data-ol-link-track="CTAClick|BorrowListen" class="cta-btn cta-btn--available">
  <span class="btn-icon read-aloud"></span>
  <span class="btn-label">Listen</span>
</a>
</div>
`;
