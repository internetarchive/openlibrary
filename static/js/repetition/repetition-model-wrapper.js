/*
 *  Wrapper for Web Forms 2.0 Repetition Model Cross-browser Implementation <http://code.google.com/p/repetitionmodel/>
 *  Copyright: 2007, Weston Ruter <http://weston.ruter.net/>
 *  License: http://creativecommons.org/licenses/LGPL/2.1/
 * 
 *  The comments contained in this code are largely quotations from the 
 *  WebForms 2.0 specification: <http://whatwg.org/specs/web-forms/current-work/#repeatingFormControls>
 *
 *  Usage: <script type="text/javascript" src="repetition-model-wrapper.js"></script>
 */

if(!window.RepetitionElement || (
     document.implementation && document.implementation.hasFeature && 
     !document.implementation.hasFeature("WebForms", "2.0")
  )){
	//get path to source directory
	var scripts = document.getElementsByTagName('head')[0].getElementsByTagName('script'), match, dirname = '';
	for(var i = 0; i < scripts.length; i++){
		if(match = scripts[i].src.match(/^(.*)repetition-model-wrapper\.js$/))
			dirname = match[1];
	}

	//load script
	if(document.write)
		document.write("<script type='text/javascript' src='" + dirname + "repetition-model-p.js'></script>");
	else {
		var script = document.createElement('script');
		script.setAttribute('type', 'text/javascript');
		script.setAttribute('src', dirname + 'repetition-model-p.js');
		script.setAttribute('language', 'JavaScript');
		document.getElementsByTagName('head')[0].appendChild(script);
	}
}
