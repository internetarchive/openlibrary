var Mint = new Object();
Mint.save = function() 
{
	var now		= new Date();
	var debug	= false; // this is set by php 
	if (window.location.hash == '#Mint:Debug') { debug = true; };
	var path	= 'http://shauninman.com/mint/?record&key=6569313635373239504f476b6f6b467a4b6b36554e6f4c303231';
	path 		= path.replace(/^https?:/, window.location.protocol);
	
	// Loop through the different plug-ins to assemble the query string
	for (var developer in this) 
	{
		for (var plugin in this[developer]) 
		{
			if (this[developer][plugin] && this[developer][plugin].onsave) 
			{
				path += this[developer][plugin].onsave();
			};
		};
	};
	// Slap the current time on there to prevent caching on subsequent page views in a few browsers
	path += '&'+now.getTime();
	
	// Redirect to the debug page
	if (debug) { window.open(path+'&debug&errors', 'MintLiveDebug'+now.getTime()); return; };
	
	var ie = /*@cc_on!@*/0;
	if (!ie && document.getElementsByTagName && (document.createElementNS || document.createElement))
	{
		var tag = (document.createElementNS) ? document.createElementNS('http://www.w3.org/1999/xhtml', 'script') : document.createElement('script');
		tag.type = 'text/javascript';
		tag.src = path + '&serve_js';
		document.getElementsByTagName('head')[0].appendChild(tag);
	}
	else if (document.write)
	{
		document.write('<' + 'script type="text/javascript" src="' + path + '&amp;serve_js"><' + '/script>');
	};
};
if (!Mint.SI) { Mint.SI = new Object(); }
Mint.SI.Referrer = 
{
	onsave	: function() 
	{
		var encoded = 0;
		if (typeof Mint_SI_DocumentTitle == 'undefined') { Mint_SI_DocumentTitle = document.title; }
		else { encoded = 1; };
		var referer		= (window.decodeURI)?window.decodeURI(document.referrer):document.referrer;
		var resource	= (window.decodeURI)?window.decodeURI(document.URL):document.URL;
		return '&referer=' + escape(referer) + '&resource=' + escape(resource) + '&resource_title=' + escape(Mint_SI_DocumentTitle) + '&resource_title_encoded=' + encoded;
	}
};
if (!Mint.SI) { Mint.SI = new Object(); }
Mint.SI.UserAgent007 = 
{
	versionHigh			: 16,
	flashVersion		: 0,
	resolution			: '0x0',
	detectFlashVersion	: function () 
	{
		var ua = navigator.userAgent.toLowerCase();
		if (navigator.plugins && navigator.plugins.length) 
		{
			var p = navigator.plugins['Shockwave Flash'];
			if (typeof p == 'object') 
			{
				for (var i=this.versionHigh; i>=3; i--) 
				{
					if (p.description && p.description.indexOf(' ' + i + '.') != -1) { this.flashVersion = i; break; }
				}
			}
		}
		else if (ua.indexOf("msie") != -1 && ua.indexOf("win")!=-1 && parseInt(navigator.appVersion) >= 4 && ua.indexOf("16bit")==-1) 
		{
			var vb = '<scr' + 'ipt language="VBScript"\> \nOn Error Resume Next \nDim obFlash \nFor i = ' + this.versionHigh + ' To 3 Step -1 \n   Set obFlash = CreateObject("ShockwaveFlash.ShockwaveFlash." & i) \n   If IsObject(obFlash) Then \n      Mint.SI.UserAgent007.flashVersion = i \n      Exit For \n   End If \nNext \n<'+'/scr' + 'ipt\> \n';
			document.write(vb);
		}
		else if (ua.indexOf("webtv/2.5") != -1) this.flashVersion = 3;
		else if (ua.indexOf("webtv") != -1) this.flashVersion = 2;
		return this.flashVersion;
	},
	onsave				: function() 
	{
		if (this.flashVersion == this.versionHigh) { this.flashVersion = 0; };
		this.resolution = screen.width+'x'+screen.height;
		return '&resolution=' + this.resolution + '&flash_version=' + this.flashVersion;
	}
};
Mint.SI.UserAgent007.detectFlashVersion();
if (!Mint.SI) { Mint.SI = new Object(); }
Mint.SI.RealEstate = 
{
	onsave	: function() 
	{
		var width = -1;
		var height = -1;
		
		if (typeof window.innerWidth != "undefined")
		{
			width = window.innerWidth;
			height = window.innerHeight;
		}
		else if (document.documentElement && typeof document.documentElement.offsetWidth != "undefined" && document.documentElement.offsetWidth != 0)
		{
			width = document.documentElement.offsetWidth;
			height = document.documentElement.offsetHeight;
		}
		else if (document.body && typeof document.body.offsetWidth != "undefined")
		{
			width = d.body.offsetWidth;
			height = d.body.offsetHeight;
		};
		
		return '&window_width=' + width + '&window_height=' + height;
	}
};
function Mint_SI_addEvent( obj, type, fn )
{
	if (obj.addEventListener)
	{
		obj.addEventListener( type, fn, false );
	}
	else if (obj.attachEvent)
	{
		obj["e"+type+fn] = fn;
		obj[type+fn] = function() { obj["e"+type+fn]( window.event ); }
		obj.attachEvent( "on"+type, obj[type+fn] );
	};
};
function Mint_SI_IO()
{
	if (document.getElementsByTagName)
	{
		var links = document.getElementsByTagName('a');
		for (var i=0; i<links.length; i++)
		{
			var link = links[i];
			if (link.href && !Mint_SI_IO_isLocal(link.href)  && link.href.indexOf('javascript:')==-1)
			{
				Mint_SI_addEvent(links[i], 'mousedown', Mint_SI_IO_save);
			};
		};
	};
};
function Mint_SI_IO_isLocal(url)
{
	return /^([^:]+):\/\/([a-z0-9]+[\._-])*(shauninman\.com)/i.test(url);
};
function Mint_SI_IO_save()
{
	var now		= new Date();
	var then	= now.getTime() + 300;
	var path	= 'http://shauninman.com/mint/pepper/shauninman/outbound/click.php?'+now.getTime();
	path 		= path.replace(/^https?:/, window.location.protocol);
	
	var encoded = 0;
	if (typeof Mint_SI_DocumentTitle == 'undefined') { Mint_SI_DocumentTitle = document.title; }
	else { encoded = 1; };
	var to			= (window.decodeURI)?window.decodeURI(this.href):this.href;
	var from		= (window.decodeURI)?window.decodeURI(document.URL):document.URL;
	var to_title 	= (this.title && this.title != '')?this.title:this.innerHTML;
	
	path += '&to=' + escape(to) + '&to_title=' + escape(to_title) + '&from=' + escape(from) + '&from_title=' + escape(Mint_SI_DocumentTitle) + '&from_title_encoded=' + encoded;
	var img = new Image();
	img.src = path;
	
	while (now.getTime() < then) { now = new Date(); };
};
Mint_SI_addEvent(window, 'load', Mint_SI_IO);
Mint.save();
