export default function Filevalidation (){
 var fi = document.getElementById('coverFile'); 
 if (fi.files.length > 0) {
  for (var i = 0; i <= fi.files.length - 1; i++) {
       var fsize = fi.files.item(i).size; 
       var filname=fi.files.item(i).type;
       var filtyp=filname.split('/')[0];
       var file = (fsize / 1024); 
       // The type of the file. 
       if(!filtyp.startsWith('image')){
         document.getElementById('imageUploadSize').innerHTML = 
         '<b>Max Size Upload: 30MB.</b>';
         document.getElementById("coverFile").value = "";
         alert("Please provide a valid image.");
       }
       // The size of the file. 
       else if (file > 30720) { 
         document.getElementById("coverFile").value = "";
         document.getElementById('imageUploadSize').innerHTML = 
         '<b>Max Size Upload: 30MB.</b>'; 
         alert("Please provide a file less than 30mb."); 
       } 
       else { 
         document.getElementById('imageUploadSize').innerHTML = '<b>'
           + file.toFixed(2) + 'KB</b>'; 
       } 
    } 
  } 
}