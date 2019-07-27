// ADD FADE TOGGLE
// COURTESY: Karl Swedberg http://www.learningjquery.com/2006/09/slicker-show-and-hide
/**
 * @this {jQuery}
 */
export default function(speed, easing, callback) {
    return this.animate({opacity: 'toggle'}, speed, easing, callback);
}
