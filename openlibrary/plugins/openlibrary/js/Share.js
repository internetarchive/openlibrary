const viewBtn = document.querySelector(".view-modal"),
popup = document.querySelector(".popup"),
close = popup.querySelector(".close"),
field = popup.querySelector(".copy-field"),
input = field.querySelector("input"),
copy = field.querySelector("button");

viewBtn.onclick = ()=>{
popup.classList.toggle("show");
}
close.onclick = ()=>{
viewBtn.click();
}

  copy.onclick = ()=>{
    input.select(); //select input value
    if(document.execCommand("copy")){ //if the selected text copy
      field.classList.add("active");
      copy.innerText = "Copied";
      setTimeout(()=>{
        window.getSelection().removeAllRanges(); //remove selection from document
        field.classList.remove("active");
        copy.innerText = "Copy";
      }, 3000);
    }
  }