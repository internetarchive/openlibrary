const editionIdentifiersSample = `<fieldset id="identifiers">
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

export default {
    editionIdentifiersSample
};
