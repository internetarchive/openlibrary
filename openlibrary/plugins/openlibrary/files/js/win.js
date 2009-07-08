function showWIN(thiswidth,thisheight,thisURL) {
   var theWIN
   var thisWIN
   var thisURL ;
   var thiswidth ;
   var thisheight ;

	thisWIN = self
	if (thisWIN.name == "theWIN") { theWIN = thisWIN }
   if (!theWIN || theWIN.closed) {
      theWIN = window.open(thisURL,"theWIN","toolbar=0,location=0,directories=0,status=0,scrollbars=1,resizable=1,copyhistory=0 ,width=" + thiswidth + ",height=" + thisheight + ",top=10,left=10,screeny=25,screenx=50");
   } else {
      theWIN.location.href = thisURL ;
      theWIN.resizeTo(thiswidth,thisheight) ;

   }
   theWIN.focus() ;
}
