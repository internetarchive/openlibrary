export const editionIdentifiersSample = `<fieldset id="identifiers" data-config="{&quot;Please select an identifier.&quot;: &quot;Please select an identifier.&quot;, &quot;You need to give a value to ID.&quot;: &quot;You need to give a value to ID.&quot;, &quot;ID ids cannot contain whitespace.&quot;: &quot;ID ids cannot contain whitespace.&quot;, &quot;ID must be exactly 10 characters [0-9] or X.&quot;: &quot;ID must be exactly 10 characters [0-9] or X.&quot;, &quot;That ISBN already exists for this edition.&quot;: &quot;That ISBN already exists for this edition.&quot;, &quot;ID must be exactly 13 digits [0-9]. For example: 978-1-56619-909-4&quot;: &quot;ID must be exactly 13 digits [0-9]. For example: 978-1-56619-909-4&quot;}">
<div id="id-errors" class="note" style="display: none"></div>
<table class="identifiers">
    <tbody><tr id="identifiers-form">
        <td align="right">
            <input type="hidden" name="select-id-json" class="repeat-ignore" value="[]"><select name="name" id="select-id">
                <option value="">Select one of many...</option>
                <option value="google">Google</option>
                <option value="goodreads">Goodreads</option>
                <option value="isbn_10">ISBN 10</option>
                <option value="isbn_13">ISBN 13</option>
            </select>
        </td>
        <td>
            <input type="text" name="value" id="id-value">
        </td>
        <td>
            <button type="button" name="add" class="repeat-add larger">Add</button>
        </td>
    </tr>
    </tbody><tbody id="identifiers-display">
        <tr id="identifiers-template" style="display: none;" class="repeat-item">
            <td align="right"><strong>{{$("#select-id").find("option[value='" + name + "']").html()}}</strong></td>
            <td>{{value}}
                <input type="hidden" name="{{prefix}}identifiers--{{index}}--name" value="{{name}}">
                <input type="hidden" name="{{prefix}}identifiers--{{index}}--value" value="{{value}}" class="{{name}}">
            </td>
            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this identifier">[x]</a></td>
        </tr>
        <tr>
            <td align="right">Open Library</td>
            <td>OL23278082M</td>
            <td></td>
        </tr>
        <tr id="identifiers--0" class="repeat-item">
            <td align="right"><strong>Internet Archive</strong></td>
            <td>harrypottersorce00rowl
                <input type="hidden" name="edition--identifiers--0--name" value="ocaid">
                <input type="hidden" name="edition--identifiers--0--value" value="harrypottersorce00rowl" class="ocaid">
            </td>
            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this identifier">[x]</a></td>
        </tr>
        <tr id="identifiers--1" class="repeat-item">
            <td align="right"><strong>ISBN 10</strong></td>
            <td>059035342X
                <input type="hidden" name="edition--identifiers--1--name" value="isbn_10">
                <input type="hidden" name="edition--identifiers--1--value" value="059035342X" class="isbn_10">
            </td>
            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this identifier">[x]</a></td>
        </tr>
        <tr id="identifiers--2" class="repeat-item">
            <td align="right"><strong>ISBN 13</strong></td>
            <td>9780590353427
                <input type="hidden" name="edition--identifiers--2--name" value="isbn_13">
                <input type="hidden" name="edition--identifiers--2--value" value="9780590353427" class="isbn_13">
            </td>
            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this identifier">[x]</a></td>
        </tr>
        <tr id="identifiers--3" class="repeat-item">
            <td align="right"><strong>Goodreads</strong></td>
            <td>44415839
                <input type="hidden" name="edition--identifiers--3--name" value="goodreads">
                <input type="hidden" name="edition--identifiers--3--value" value="44415839" class="goodreads">
            </td>
            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this identifier">[x]</a></td>
        </tr></tbody>
</table>
</fieldset>`;

/** Part/Simplification of the .widget-add element */
export const bookDropdownSample = `
    <a href="javascript:;" class="dropclick dropclick-unactivated">
        <div class="arrow arrow-unactivated"></div>
    </a>
`;

export const listCreationForm = `
    <form method="post" class="floatform" name="new-list" id="new-list">
    <div class="formElement">
        <div class="label">
            <label for="list_label">Name:</label>
        </div>
        <div class="input">
            <input type="text" name="list_label" id="list_label" class="text required" value="sample text" required="">
        </div>
    </div>
    <div class="formElement">
        <div class="label">
            <label for="list_desc">Description:</label>
        </div>
        <div class="input">
            <textarea name="list_desc" id="list_desc" rows="5" cols="30">Sample text</textarea>
        </div>
    </div>
    <div class="formElement">
        <div class="input">
            <button id="create-list-button" type="submit" class="larger">Create new list</button>
            &nbsp; &nbsp;
            <a class="small dialog--close plain red" href="javascript:;">Cancel</a>
        </div>
    </div>
    </form>`;

export const clamperSample = `
      <span class='clamp' data-before='▾  ' style='display: unset;'>
          <h6>Subjects</h6>
          <a>Ghosts</a>
          <a>Monsters</a>
          <a>Vampires</a>
          <a>Witches</a>
          <a>Challenges and Overcoming Obstacles</a>
          <a>Magic and Supernatural</a>
          <a>Cleverness</a>
          <a>School Life</a>
          <a>school stories</a>
          <a>Wizards</a>
          <a>Magic</a>
          <a>MAGIA</a>
          <a>MAGOS</a>
          <a>Juvenile fiction</a>
          <a>Fiction</a>
          <a>NOVELAS INGLESAS</a>
          <a>Schools</a>
          <a>orphans</a>
          <a>fantasy fiction</a>
          <a>England in fiction</a>
      </span>`;

export const checkInForm = `
<div class="check-in" data-modal-ref="dialog-OL53924W" data-event-type="1">
  <form method="dialog" class="check-in__form" action="/works/OL53924W/check-ins">
    <input type="hidden" id="edition-key" name="edition_key" value="/books/OL7037695M">
    <div>
      Add an optional check-in date.  Check-in dates are used to track yearly reading goals.
    </div>
    <div class="check-in__inputs">
      <label class="check-in__label">Start Date:</label>
      <span>
        <label>Year:</label>
        <select class="check-in__select" name="year">
          <option value="">Year</option>
          <option value="2022">2022</option>
          <option value="2021">2021</option>
          <option value="2020">2020</option>
          <option value="2019">2019</option>
          <option value="2018">2018</option>
        </select>
      </span>
      <span>
        <label>Month:</label>
        <select class="check-in__select" name="month" disabled>
          <option value="">Month</option>
          <option value="1">January</option>
          <option value="2">February</option>
          <option value="3">March</option>
          <option value="4">April</option>
          <option value="5">May</option>
          <option value="6">June</option>
          <option value="7">July</option>
          <option value="8">August</option>
          <option value="9">September</option>
          <option value="10">October</option>
          <option value="11">November</option>
          <option value="12">December</option>
        </select>
      </span>
      <span>
        <label>Day:</label>
        <select class="check-in__select" name="day" disabled>
          <option value="">Day</option>
          <option value="1">1</option>
          <option value="2">2</option>
          <option value="3">3</option>
          <option value="4">4</option>
          <option value="5">5</option>
          <option value="6">6</option>
          <option value="7">7</option>
          <option value="8">8</option>
          <option value="9">9</option>
          <option value="10">10</option>
          <option value="11">11</option>
          <option value="12">12</option>
          <option value="13">13</option>
          <option value="14">14</option>
          <option value="15">15</option>
          <option value="16">16</option>
          <option value="17">17</option>
          <option value="18">18</option>
          <option value="19">19</option>
          <option value="20">20</option>
          <option value="21">21</option>
          <option value="22">22</option>
          <option value="23">23</option>
          <option value="24">24</option>
          <option value="25">25</option>
          <option value="26">26</option>
          <option value="27">27</option>
          <option value="28">28</option>
          <option value="29">29</option>
          <option value="30">30</option>
          <option value="31">31</option>
        </select>
      </span>
    </div>
    <span class="check-in__actions">
      <button class="check-in__cancel-btn cta-btn cta-btn--cancel">Cancel</button>
      <button type="submit" class="check-in__submit-btn cta-btn cta-btn--shell" disabled>Submit</button>
    </span>
  </form>
</div>
`;

export const readingLogDropperForm = `
<div id="dropper">
    <form class="readingLog">
        <input type="hidden" name="bookshelf_id" value="1">
        <input type="hidden" name="action" value="">
    </form>
    <form id="remove-from-list">
        <input type="hidden" name="bookshelf_id">
        <button class="hidden">Remove From Shelf</button>
    </form>
</div>
`;
export const initRoleValidationHtml = `
<div class="formElement" id="roles" data-config="{&quot;Please select a role.&quot;: &quot;Please select a role.&quot;, &quot;You need to give this ROLE a name.&quot;: &quot;You need to give this ROLE a name.&quot;}">
<div class="label">
    <label for="select-role">List the people involved</label>
    <span class="tip"></span>
</div>
<div class="input">
    <div id="role-errors" class="note" style="display: none"></div>
    <table class="identifiers">
    <tbody>
        <tr id="roles-form">
            <td align="right">
                <input type="hidden" name="select-role-json" class="repeat-ignore" value="[]">
                <select name="role" id="select-role" class="sansserif large">
                    <option value="" selected="selected">Select role</option>
                    <option>Adapted from original work by</option>

                    <option>Additional Author (this edition)</option>

                    <option value="afterword">Afterword</option>

                    <option>Collected by</option>

                    <option>Commentary</option>

                    <option>Compiler</option>

                    <option>Consultant</option>

                    <option>Foreword</option>

                    <option>Editor</option>

                    <option>Illustrator</option>

                    <option>Introduction</option>

                    <option>Narrator/Reader</option>

                    <option>Notes by</option>

                    <option>Revised by</option>

                    <option>Selected by</option>

                    <option>Translator</option>

                    <option>---</option>

                    <option>Accountability</option>

                    <option>Acquisition Editor</option>

                    <option>Acquisitions Coordinator</option>

                    <option>Additional Research</option>

                    <option>Advisory Editor</option>

                    <option>Agent</option>

                    <option>Appendix</option>

                    <option>Archival photos</option>

                    <option>Art Director</option>

                    <option>Assistant Editor</option>

                    <option>Assisted by</option>

                    <option>Associate Editor</option>

                    <option>As told to</option>

                    <option>Author Photographer</option>

                    <option>Board of Consultants</option>

                    <option>Book Designer</option>

                    <option>Brand Manager</option>

                    <option>Cartographer</option>

                    <option>Chapter Author</option>

                    <option>Chef</option>

                    <option>Chief editor</option>

                    <option>Co-Author</option>

                    <option>Colorist</option>

                    <option>Colour Separations</option>

                    <option>Commissioning Editor</option>

                    <option>Composition</option>

                    <option>Computer Designer</option>

                    <option>Conductor</option>

                    <option>Consulting Editor</option>

                    <option>Contributing artist</option>

                    <option>Contributing Editor</option>

                    <option>Contributor</option>

                    <option>Coordinating author</option>

                    <option>Copy Editor</option>

                    <option>Copyright</option>

                    <option>Cover and Text Design</option>

                    <option>Cover Art</option>

                    <option>Cover Design</option>

                    <option>Cover Photographer</option>

                    <option>Cover Printer</option>

                    <option>Creator</option>

                    <option>Curator</option>

                    <option>Decorator</option>

                    <option>Dedicated to</option>

                    <option>Designer</option>

                    <option>Development Editor</option>

                    <option>Diffuseur</option>

                    <option>Director</option>

                    <option>Distributors</option>

                    <option>Drawings</option>

                    <option>Editor-in-Chief</option>

                    <option>Editorial</option>

                    <option>Editorial Assistant</option>

                    <option>Editorial Board Member</option>

                    <option>Editorial Director</option>

                    <option>Editorial Intern</option>

                    <option>Editorial Manager</option>

                    <option>Editorial Team Leader</option>

                    <option>Engraver</option>

                    <option>Epigraph</option>

                    <option>Epilogue</option>

                    <option>Essayist</option>

                    <option>Export Assistant</option>

                    <option>Food Photographer</option>

                    <option>Food Stylist</option>

                    <option>From the Library of</option>

                    <option>Frontispiece</option>

                    <option>General Editor</option>

                    <option>Glossary</option>

                    <option>Graphic Design</option>

                    <option>Graphic Layout</option>

                    <option>Home Economist</option>

                    <option>Image editor</option>

                    <option>Indexer</option>

                    <option>Information Director</option>

                    <option>Information Officer</option>

                    <option>Interior Design</option>

                    <option>Interior Photos</option>

                    <option>interviewee</option>

                    <option>Interviewer</option>

                    <option>Jacket Design</option>

                    <option>Jacket Photo</option>

                    <option>Jacket Printer</option>

                    <option>Language activities</option>

                    <option>Lettering</option>

                    <option>Librorum Censor</option>

                    <option>Lithography</option>

                    <option>Logo Designer</option>

                    <option>Lyricist</option>

                    <option>Managing Editor</option>

                    <option>Marketing Manager</option>

                    <option>Meterological tables</option>

                    <option>Musical Director</option>

                    <option>Orchestra</option>

                    <option>Photo Editor</option>

                    <option>Photographer</option>

                    <option>Photo Library</option>

                    <option>Photo Research</option>

                    <option>Photo Scanning Specialist</option>

                    <option>Poet</option>

                    <option>Portrait</option>

                    <option>Preface</option>

                    <option>Prepared by</option>

                    <option>Printer</option>

                    <option>Printmaker</option>

                    <option>Producer</option>

                    <option>Production Assistant</option>

                    <option>Production Controller</option>

                    <option>Production Coordinator</option>

                    <option>Production Editor</option>

                    <option>Project Coordinator</option>

                    <option>Project Editor</option>

                    <option>Project Team Leader</option>

                    <option>Prologue</option>

                    <option>Proofreader</option>

                    <option>Publishing Director</option>

                    <option>Reading Director</option>

                    <option>Recipe Tester</option>

                    <option>Recording Producer</option>

                    <option>Recording Studio</option>

                    <option>Redactor</option>

                    <option>Research Director</option>

                    <option>Researcher</option>

                    <option>Reviewer</option>

                    <option>Science Editor</option>

                    <option>Scientific advisor</option>

                    <option>Screenplay</option>

                    <option>Script</option>

                    <option>Senior Editor</option>

                    <option>Series Design</option>

                    <option>Series General Editor</option>

                    <option>Soloist</option>

                    <option>Songs translated by</option>

                    <option>Sponsor</option>

                    <option>Stylist</option>

                    <option>Technical draftsman</option>

                    <option>Technical Editor</option>

                    <option>Technical Reviewer</option>

                    <option>Tests and evaluations</option>

                    <option>Text Design</option>

                    <option>Thanks</option>

                    <option>Typesetter</option>

                    <option>Typography</option>

                    <option>Web Programming &amp; Design</option>



                </select>
            </td>
            <td>
                <input type="text" id="role-name" name="name">
            </td>
            <td>
                <button type="button" name="add" class="repeat-add larger">Add</button>
            </td>
        </tr>
    </tbody>
    </table>
    <table class="identifiers">
        <tbody id="roles-display">
            <tr id="roles-template" class="repeat-item" style="display: none;">
                <td align="right"><strong>{{role}}</strong></td>
                <td>{{name}}
                    <input type="hidden" name="{{prefix}}contributors--{{index}}--role" value="{{role}}">
                    <input type="hidden" name="{{prefix}}contributors--{{index}}--name" value="{{name}}">
                </td>
                <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this contributor">[x]</a></td>
            </tr>
            <tr class="repeat-item">
                <td align="right"><strong>Author</strong></td>
                <td>Arthur Conan Doyle</td>
                <td></td>
            </tr>
        </tbody>
    </table>
</div>
</div>
`;
