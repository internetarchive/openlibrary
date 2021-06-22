import { Toast } from '../Toast.js';
import '../../../../../static/css/components/metadata-form.less';
import '../../../../../static/css/components/toast.less';

/**
 * Initializes a collection of notes modals.
 * 
 * @param {JQuery} $modalLinks  A collection of notes modal links.
 */
export function initNotesModal($modalLinks) {
  addClickListeners($modalLinks);
  addNotesButtonListeners();
};

/**
 * Adds click listeners to buttons in all notes forms on a page.
 */
function addNotesButtonListeners() {
  let toast;

  $('.update-note-button').on('click', function(){
    // If button is inside of metadata form, set toast's parent element to the form:
    let $parent = $(this).closest('.metadata-form');

    // Get form data
    let formData = new FormData($(this).prop('form'));

    // Post data
    let workOlid = formData.get('work_id');
    formData.delete('work_id');

    $.ajax({
      url: `/works/${workOlid}/notes.json`,
      data: formData,
      type: 'POST',
      contentType: false,
      processData: false,
      success: function() {
          // Display success message
          if (toast) {
              toast.close();
          }
          toast = new Toast($parent, 'Update successful!');
          toast.show();
      }
    });
  });
}

/**
 * Initializes a collection of observations modals.
 * 
 * Adds on click listeners to all given modal links, and adds change listeners to
 * each modal's inputs.
 * 
 * @param {JQuery} $modalLinks  A collection of observations modal links.
 */
export function initObservationsModal($modalLinks) {
  addClickListeners($modalLinks);
  
  $modalLinks.each(function(_i, modalLinkElement) {
    const $element = $(modalLinkElement);
    const context = $element.data('context');

    addObservationChangeListeners($element.next(), context);
  })
}

/**
 * Add on click listeners to a collection of modal links.
 * 
 * When any of the links are clicked, it's corresponding modal
 * will be displayed.
 * 
 * @param {JQuery} $modalLinks  A collection of modal links.
 */
function addClickListeners($modalLinks) {
  $modalLinks.each(function(_i, modalLinkElement) {
    $(modalLinkElement).on('click', function() {
      const context = $(this).data('context');
      displayModal(context.id);
    })
  })
}

/**
 * Displays a model identified by the given identifier.
 * 
 * @param {String} modalId  A string that uniquely identifies a modal.
 */
function displayModal(modalId) {
  $.colorbox({
    inline: true,
    opacity: '0.5',
    href: `#${modalId}-metadata-form`,
    width: '60%',
  });
};

/**
 * Adds change listeners to each input in the observations section of the modal.
 *
 * For each checkbox and radio button in the observations form, a change listener
 * that triggers observation submissions is added.  On change, a payload containing
 * the username, action type ('add' when an input is checked, 'delete' when unchecked),
 * and observation type and value are sent to the back-end server.
 *
 * @param {JQuery}  $parent  Object that contains the observations form.
 * @param {Object}  context  An object containing the patron's username and the work's OLID.
 */
 function addObservationChangeListeners($parent, context) {
  const $questionSections = $parent.find('.aspect-section');
  const username = context.username;
  const workOlid = context.work.split('/')[2];

  $questionSections.each(function() {
      const $inputs = $(this).find('input')

      $inputs.each(function() {
          $(this).on('change', function() {
              const type = $(this).attr('name');
              const value = $(this).attr('value');
              const observation = {};
              observation[type] = value;

              const data = {
                  username: username,
                  action: `${$(this).prop('checked') ? 'add': 'delete'}`,
                  observation: observation
              }

              submitObservation($(this), workOlid, data, type);
          });
      })
  });
}

/**
 * Submits an observation to the server.
 *
 * @param {String}  workOlid    The OLID for the work being observed.
 * @param {Object}  data        Payload that will be sent to the back-end server.
 * @param {String}  sectionType Name of the input's section.
 */
 function submitObservation(workOlid, data, sectionType) {
  // Make AJAX call
  $.ajax({
      type: 'POST',
      url: `/works/${workOlid}/observations`,
      contentType: 'application/json',
      data: JSON.stringify(data)
  })
      .done(function() {
          // Show success message:
      })
      .fail(function() {
          // Show failure message:
      });
}
