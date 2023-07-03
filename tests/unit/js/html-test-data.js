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
    <div class="dropper">
        <a href="javascript:;" class="dropclick dropclick-unactivated">
            <div class="arrow arrow-unactivated"></div>
        </a>
    </div>
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
    </form>`

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
      </span>`

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
`

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
`
export const readClassification = `
<fieldset class="major" id="classifications" data-config="{&quot;Please select a classification.&quot;: &quot;Please select a classification.&quot;, &quot;You need to give a value to CLASS.&quot;: &quot;You need to give a value to CLASS.&quot;}">
    <legend>Classifications</legend>
    <div class="formBack">

        <div id="classification-errors" class="note" style="display: none"></div>
        <div class="formElement">
            <div class="label">
                <label for="select-classification">Do you know any classifications of this edition?</label>
                <span class="tip">Like, Dewey Decimal?</span>
            </div>
            <div class="input">
                <table class="classifications identifiers">
                    <tr id="classifications-form">
                        <td align="right">
                            <select name="name" id="select-classification">
                                <option value="">Select one of many...</option>
                                <option value="dewey_decimal_class">Dewey Decimal Class</option>

                                <option value="lc_classifications">Library of Congress</option>

                                <option value="library_and_archives_canada_cataloguing_in_publication">Library and Archives Canada Cataloguing in Publication</option>

                                <option value="library_bibliographical_classification">Library-Bibliographical Classification</option>

                                <option value="rvk">Regensburger Verbundklassifikation</option>

                                <option value="finnish_public_libraries_classification_system">Finnish Public Libraries</option>

                                <option value="udc">Universal Decimal Classification</option>

                                <option value="ulrls_classmark">ULRLS Classmark</option>

                                <option value="goethe_university_library,_frankfurt">Goethe University Library, Frankfurt</option>

                                <option value="siso">SISO</option>

                                <option value="nur">NUR</option>

                                <option value="identificativo_sbn">Identificativo SBN</option>

                                <option>---</option>
                                <!-- <option value="__add__">Add a new classification type</option> -->
                            </select>
                        </td>
                        <td>
                            <input type="text" name="value" id="classification-value" size="20"/>
                        </td>
                        <td >
                            <button type="button" name="add" class="repeat-add larger">Add</button>
                        </td>
                    </tr>
                    <tbody id="classifications-display">
                        <tr id="classifications-template" style="display: none;" class="repeat-item">
                            <td align="right"><strong>{{$("#select-classification").find("option[value='" + name + "']").html()}}</strong></td>
                            <td>{{value}}
                                <input type="hidden" name="{{prefix}}classifications--{{index}}--name" value="{{name}}"/>
                                <input type="hidden" name="{{prefix}}classifications--{{index}}--value" value="{{value}}"/>
                            </td>
                            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this classification">[x]</a></td>
                        </tr>
                        <tr id="classifications--0" class="repeat-item">
                            <td align="right"><strong>Dewey Decimal Class</strong></td>
                            <td>530.1/1
                                <input type="hidden" name="edition--classifications--0--name" value="dewey_decimal_class"/>
                                <input type="hidden" name="edition--classifications--0--value" value="530.1/1"/>
                            </td>
                            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this classification">[x]</a></td>
                        </tr>
                        <tr id="classifications--1" class="repeat-item">
                            <td align="right"><strong>Library of Congress</strong></td>
                            <td>QA699 .A13 1991
                                <input type="hidden" name="edition--classifications--1--name" value="lc_classifications"/>
                                <input type="hidden" name="edition--classifications--1--value" value="QA699 .A13 1991"/>
                            </td>
                            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this classification">[x]</a></td>
                        </tr>
                        <tr id="classifications--2" class="repeat-item">
                            <td align="right"><strong>Library of Congress</strong></td>
                            <td>QA699.A13 1991
                                <input type="hidden" name="edition--classifications--2--name" value="lc_classifications"/>
                                <input type="hidden" name="edition--classifications--2--value" value="QA699.A13 1991"/>
                            </td>
                            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this classification">[x]</a></td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</fieldset>
`
