import '../../../../../static/css/components/metadata-form.less';

export function initPatronMetadata() {
    function displayModal() {
        $.colorbox({
            inline: true,
            opacity: "0.5",
            href: "#metadata-form",
            width: "55%",
        });
    }

    function populateForm($form, aspects) {
        for(const aspect of aspects) {
            let className = aspect.multi_choice ? 'multi-choice' : 'single-choice';
            let $choices = $(`<div class="${className}"></div>`);
            let choiceIndex = aspect.schema.values.length;
    
            for(const value of aspect.schema.values) {
              let choiceId = `${aspect.label}Choice${choiceIndex--}`;
    
              $choices.prepend(`
                <label for="${choiceId}" class="${className}-label">
                            <input type=${aspect.multi_choice ? "checkbox": "radio"} name="${aspect.label}" id="${choiceId}" value="${value}">
                            ${value}
                        </label>`);
            }
    
            $form.append(`
              <div class="formElement" id="${aspect.label}-question">
                <h3>${aspect.description}</h3>
                ${$choices.prop('outerHTML')}
              </div>`);
          }
    
          $form.append(`
            <div class="formElement metadata-submit">
              <div class="input">
                <button type="submit">Submit</button>
                <a class="small dialog--close plain" href="javascript:;" id="cancel-submission">Cancel</a>
              </div>
            </div>`);
    }

    $('#modal-link').on('click', function() {
        if($('#user-metadata').children().length === 0) {
          $.ajax({
            type: 'GET',
            url: 'https://dev.thebestbookon.com/api/aspects',
            contentType: 'application/json',
            dataType: 'json'
          })
            .done(function(data) {
              populateForm($('#user-metadata'), data.aspects);
              $('#cancel-submission').click(function() {
                $.colorbox.close();
              })
              displayModal();
            })
            .fail(function() {
              // TODO: Handle failed API calls gracefully.
            })
        } else {
          displayModal();
        }
      });
  
      $("#user-metadata").on('submit', function(event) {
        event.preventDefault();

        let context = JSON.parse(document.querySelector('#modal-link').dataset.context);

        console.log(context);
  
        let result = {};
  
        result['username'] = context.username;
        result['work_id'] = context.work.split('/')[2];
  
        if(context.edition) {
          result['edition_id'] = context.edition.split('/')[2];
        }
  
        result['observations'] = [];
        
        $(this).find("input[type=radio]:checked").each(function() {
          let currentPair = {};
          currentPair[$(this).attr("name")] = $(this).val()
          result['observations'].push(currentPair);
        })
  
        $(this).find("input[type=checkbox]:checked").each(function() {
          let currentPair = {};
          currentPair[$(this).attr("name")] = $(this).val()
          result['observations'].push(currentPair);
        })
           
        if(result['observations'].length > 0) {
          $.ajax({
            type: 'POST',
            url: 'https://dev.thebestbookon.com/api/observations.json',
            data: JSON.stringify(result)
          });
          $.colorbox.close();
        } else {
          // TODO: Handle case where no data was submitted
        }
  
    });
}
