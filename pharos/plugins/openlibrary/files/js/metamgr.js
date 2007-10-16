// -------------------------------------------------------------
// confirm submit
// -------------------------------------------------------------

function submitForm(f) {
  // if (confirm("are you sure you want to submit form:" + f + "?")) {
    document.forms[f].submit();
  // }
}


// -------------------------------------------------------------
// toggle the diplay property of any element (block|none)
// -------------------------------------------------------------

function toggle(id) {
  elm=document.getElementById(id);
  if (elm.style.display=='none') { elm.style.display='block'; }
  else                           { elm.style.display='none';  }
}


// -------------------------------------------------------------
// check or un-check all boxes
// -------------------------------------------------------------

function checkAllBoxes(FormName, FieldName, CheckValue, ToggleId)
{
  if(!document.forms[FormName])
    return;
  var objCheckBoxes = document.forms[FormName].elements[FieldName];
  if(!objCheckBoxes)
    return;
  var countCheckBoxes = objCheckBoxes.length;
  if(!countCheckBoxes)
    objCheckBoxes.checked = CheckValue;
  else {
    for(var i = 0; i < countCheckBoxes; i++)
      objCheckBoxes[i].checked = CheckValue;
  }

  // toggle display of on/off buttons

  toggle('checkOff');
  cb = document.getElementById('checkOff');
  cb.checked=false;

  toggle('checkOn');
  cb = document.getElementById('checkOn');
  cb.checked=true;

}


// -------------------------------------------------------------
//  add row to curateDetailsTable
// -------------------------------------------------------------

function addCurateDetailsRow(rowNum)
{
    var TABLE = document.getElementById('curateDetailsTable');
    var newTR = document.createElement('TR');
    newTR.id  = 'row_'+rowNum;

    var newTD1  = document.createElement('TD');
    var newTD2  = document.createElement('TD');
    var newTD3  = document.createElement('TD');
    var newTD4  = document.createElement('TD');
    var newTD5  = document.createElement('TD');

    // newTD1

    newTD1.appendChild(document.createTextNode('curatenote: '));

    // newTD2

    var noteTxtBx  = document.createElement('INPUT');
    noteTxtBx.type = 'text';
    noteTxtBx.name = 'qa[curatenote-code][]';

    var noteTxtBxStyle = document.createAttribute('STYLE');
    noteTxtBxStyle.value = 'width:3em';
    noteTxtBx.setAttributeNode(noteTxtBxStyle);

    newTD2.appendChild(noteTxtBx);

    // newTD3

    newTD3.appendChild(document.createTextNode('curatedetails: '));

    // newTD4

    var detailsTxtBx  = document.createElement('INPUT');
    detailsTxtBx.type = 'text';
    detailsTxtBx.name = 'qa[curatenote-details][]';

    var detailsTxtBxStyle = document.createAttribute('STYLE');
    detailsTxtBxStyle.value = 'width:12em';
    detailsTxtBx.setAttributeNode(detailsTxtBxStyle);

    newTD4.appendChild(detailsTxtBx);

    // newTD5 - set up button to remove row we're creating now

    var rmRowBtn  = document.createElement('INPUT');
    rmRowBtn.type = 'button';
    rmRowBtn.value = '-';
    rmRowBtn.setAttribute('onclick','rmRow('+rowNum+');');
    
    var rmRowBtnStyle = document.createAttribute('STYLE');
    rmRowBtnStyle.value = 'width:24px;';
    rmRowBtn.setAttributeNode(rmRowBtnStyle);

    newTD5.appendChild(rmRowBtn);

    // append new TDs to new TR and new TR to TABLE
    newTR.appendChild(newTD1);
    newTR.appendChild(newTD2);
    newTR.appendChild(newTD3);
    newTR.appendChild(newTD4);
    newTR.appendChild(newTD5);
    TABLE.appendChild(newTR);

    // increment the current field number
    document.getElementById('rowNum').value=Number(document.getElementById('rowNum').value)+1;
}


function rmRow(rowNum)
{
    var oldTR = document.getElementById('row_'+rowNum);
    oldTR.parentNode.removeChild(oldTR);
} 


// ----------------------------------------------------------------
// add new row to Modify XML table (almost verbatim copy of John's 
// technique in Edit Item. uses the EditItem classe's extra[] array
// trick ...
// ----------------------------------------------------------------

function addNewField(fieldNum)
{
    var table      = document.getElementById('extraFieldsTable');
    var newTR      = document.createElement('TR');
    newTR.id       = 'row_'+fieldNum;

    // set up the key field
    var newTD1     = document.createElement('TD');
    newTD1.appendChild(document.createTextNode('more ...'));

    // set up the value field
    var newTD2  = document.createElement('TD');
    var input2  = document.createElement('INPUT');
    input2.name = 'extra[]'
    input2.id   = 'extra[]'
    input2.type = 'text';
    var styleAttr = document.createAttribute('STYLE');
    styleAttr.value = 'width:100%';
    input2.setAttributeNode(styleAttr);
    newTD2.appendChild(input2);

    // set up the option to remove this field
    var newTD3     = document.createElement('TD');
    var rmLink     = document.createElement('A')
    rmLink.title   = 'Remove this field';
    rmLink.href    = "javascript:removeField("+fieldNum+");void(0);";
    rmLink.appendChild(document.createTextNode('remove'));
    newTD3.appendChild(rmLink);
    newTD3.align = 'right';

    // append all the junk
    newTR.appendChild(newTD1);
    newTR.appendChild(newTD2);
    newTR.appendChild(newTD3);
    table.appendChild(newTR);

    // increment the current field number
    document.getElementById('currentFieldNum').value=Number(document.getElementById('currentFieldNum').value)+1;
}

function removeField(fieldNum)
{
    var oldTR = document.getElementById('row_'+fieldNum);
    oldTR.parentNode.removeChild(oldTR);
} 



