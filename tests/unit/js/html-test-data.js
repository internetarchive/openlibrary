export const editionIdentifiersSample = `<fieldset id="identifiers">
<table class="identifiers">
    <tbody><tr id="identifiers-form">
        <td align="right">
            <input type="hidden" name="select-id-json" class="repeat-ignore" value="[]"><select name="name" id="select-id">
                <option value="">Select one of many...</option>
                <option value="google">Google</option>
                <option value="goodreads">Goodreads</option>
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
            <td align="right"><strong>{{$("#select-id").find("option[value=" + name + "]").html()}}</strong></td>
            <td width="380">{{value}}
                <input type="hidden" name="{{prefix}}identifiers--{{index}}--name" value="{{name}}">
                <input type="hidden" name="{{prefix}}identifiers--{{index}}--value" value="{{value}}">
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
                <input type="hidden" name="edition--identifiers--0--value" value="harrypottersorce00rowl">
            </td>
            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this identifier">[x]</a></td>
        </tr>
        <tr id="identifiers--1" class="repeat-item">
            <td align="right"><strong>ISBN 10</strong></td>
            <td>059035342X
                <input type="hidden" name="edition--identifiers--1--name" value="isbn_10">
                <input type="hidden" name="edition--identifiers--1--value" value="059035342X">
            </td>
            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this identifier">[x]</a></td>
        </tr>
        <tr id="identifiers--2" class="repeat-item">
            <td align="right"><strong>ISBN 13</strong></td>
            <td>9780590353427
                <input type="hidden" name="edition--identifiers--2--name" value="isbn_13">
                <input type="hidden" name="edition--identifiers--2--value" value="9780590353427">
            </td>
            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this identifier">[x]</a></td>
        </tr>
        <tr id="identifiers--3" class="repeat-item">
            <td align="right"><strong>Goodreads</strong></td>
            <td>44415839
                <input type="hidden" name="edition--identifiers--3--name" value="goodreads">
                <input type="hidden" name="edition--identifiers--3--value" value="44415839">
            </td>

            <td><a href="javascript:;" class="repeat-remove red plain" title="Remove this identifier">[x]</a></td>
        </tr></tbody>
</table>
</div>`;

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

