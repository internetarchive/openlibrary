var Attacklab=Attacklab||{};
Attacklab.wmdPlus=function(){
this.symboltable;
var _1=top;
var _2=_1["Attacklab"];
var _3=_1["document"];
var _4=_1["RegExp"];
var _5=_1["navigator"];
var _6=_2.Util;
var _7=_2.Position;
var _8=_2.Command;
_8.doAutoindent=function(_9){
_9.before=_9.before.replace(/(\n|^)[ ]{0,3}([*+-]|\d+[.])[ \t]*\n$/,"\n\n");
_9.before=_9.before.replace(/(\n|^)[ ]{0,3}>[ \t]*\n$/,"\n\n");
_9.before=_9.before.replace(/(\n|^)[ \t]+\n$/,"\n\n");
if(/(\n|^)[ ]{0,3}([*+-]|\d+[.])[ \t]+.*\n$/.test(_9.before)){
if(_8.doList){
_8.doList(_9);
}
}
if(/(\n|^)[ ]{0,3}>[ \t]+.*\n$/.test(_9.before)){
if(_8.doBlockquote){
_8.doBlockquote(_9);
}
}
if(/(\n|^)(\t|[ ]{4,}).*\n$/.test(_9.before)){
if(_8.doCode){
_8.doCode(_9);
}
}
};
_8.doBlockquote=function(_a){
_a.selection=_a.selection.replace(/^(\n*)([^\r]+?)(\n*)$/,function(_b,_c,_d,_e){
_a.before+=_c;
_a.after=_e+_a.after;
return _d;
});
_a.before=_a.before.replace(/(>[ \t]*)$/,function(_f,_10){
_a.selection=_10+_a.selection;
return "";
});
_a.selection=_a.selection.replace(/^(\s|>)+$/,"");
_a.selection=_a.selection||"Blockquote";
if(_a.before){
_a.before=_a.before.replace(/\n?$/,"\n");
}
if(_a.after){
_a.after=_a.after.replace(/^\n?/,"\n");
}
_a.before=_a.before.replace(/(((\n|^)(\n[ \t]*)*>(.+\n)*.*)+(\n[ \t]*)*$)/,function(_11){
_a.startTag=_11;
return "";
});
_a.after=_a.after.replace(/^(((\n|^)(\n[ \t]*)*>(.+\n)*.*)+(\n[ \t]*)*)/,function(_12){
_a.endTag=_12;
return "";
});
var _13=function(_14){
var _15=_14?"> ":"";
if(_a.startTag){
_a.startTag=_a.startTag.replace(/\n((>|\s)*)\n$/,function(_16,_17){
return "\n"+_17.replace(/^[ ]{0,3}>?[ \t]*$/gm,_15)+"\n";
});
}
if(_a.endTag){
_a.endTag=_a.endTag.replace(/^\n((>|\s)*)\n/,function(_18,_19){
return "\n"+_19.replace(/^[ ]{0,3}>?[ \t]*$/gm,_15)+"\n";
});
}
};
if(/^(?![ ]{0,3}>)/m.test(_a.selection)){
_8.wrap(_a,_2.wmd_env.lineLength-2);
_a.selection=_a.selection.replace(/^/gm,"> ");
_13(true);
_a.skipLines();
}else{
_a.selection=_a.selection.replace(/^[ ]{0,3}> ?/gm,"");
_8.unwrap(_a);
_13(false);
if(!/^(\n|^)[ ]{0,3}>/.test(_a.selection)){
if(_a.startTag){
_a.startTag=_a.startTag.replace(/\n{0,2}$/,"\n\n");
}
}
if(!/(\n|^)[ ]{0,3}>.*$/.test(_a.selection)){
if(_a.endTag){
_a.endTag=_a.endTag.replace(/^\n{0,2}/,"\n\n");
}
}
}
if(!/\n/.test(_a.selection)){
_a.selection=_a.selection.replace(/^(> *)/,function(_1a,_1b){
_a.startTag+=_1b;
return "";
});
}
};
_8.doCode=function(_1c){
var _1d=/\S[ ]*$/.test(_1c.before);
var _1e=/^[ ]*\S/.test(_1c.after);
if((!_1e&&!_1d)||/\n/.test(_1c.selection)){
_1c.before=_1c.before.replace(/[ ]{4}$/,function(_1f){
_1c.selection=_1f+_1c.selection;
return "";
});
var _20=1;
var _21=1;
if(/\n(\t|[ ]{4,}).*\n$/.test(_1c.before)){
_20=0;
}
if(/^\n(\t|[ ]{4,})/.test(_1c.after)){
_21=0;
}
_1c.skipLines(_20,_21);
if(!_1c.selection){
_1c.startTag="    ";
_1c.selection="print(\"code sample\");";
return;
}
if(/^[ ]{0,3}\S/m.test(_1c.selection)){
_1c.selection=_1c.selection.replace(/^/gm,"    ");
}else{
_1c.selection=_1c.selection.replace(/^[ ]{4}/gm,"");
}
}else{
_1c.trimWhitespace();
_1c.findTags(/`/,/`/);
if(!_1c.startTag&&!_1c.endTag){
_1c.startTag=_1c.endTag="`";
if(!_1c.selection){
_1c.selection="print(\"code sample\");";
}
}else{
if(_1c.endTag&&!_1c.startTag){
_1c.before+=_1c.endTag;
_1c.endTag="";
}else{
_1c.startTag=_1c.endTag="";
}
}
}
};
_8.autoindent={};
_8.autoindent.textOp=_8.doAutoindent;
_8.blockquote={};
_8.blockquote.description="Blockquote <blockquote>";
_8.blockquote.image="/images/wmd/blockquote.png";
_8.blockquote.key=".";
_8.blockquote.keyCode=190;
_8.blockquote.textOp=function(_22){
return _8.doBlockquote(_22);
};
_8.code={};
_8.code.description="Code Sample <pre><code>";
_8.code.image="/images/wmd/code.png";
_8.code.key="k";
_8.code.textOp=_8.doCode;
_8.img={};
_8.img.description="Image <img>";
_8.img.image="/images/wmd/img.png";
_8.img.key="g";
_8.img.textOp=function(_23,_24){
return _8.doLinkOrImage(_23,true,_24);
};
_8.doList=function(_25,_26){
var _27=/(([ ]{0,3}([*+-]|\d+[.])[ \t]+.*)(\n.+|\n{2,}([*+-].*|\d+[.])[ \t]+.*|\n{2,}[ \t]+\S.*)*)\n*/;
var _28="";
var _29=1;
var _2a=function(){
if(_26){
var _2b=" "+_29+". ";
_29++;
return _2b;
}
var _2c=_28||"-";
return "  "+_2c+" ";
};
var _2d=function(_2e){
if(_26==undefined){
_26=/^\s*\d/.test(_2e);
}
_2e=_2e.replace(/^[ ]{0,3}([*+-]|\d+[.])\s/gm,function(_2f){
return _2a();
});
return _2e;
};
var _30=function(){
_31=_6.regexToString(_27);
_31.expression="^\n*"+_31.expression;
var _32=_6.stringToRegex(_31);
_25.after=_25.after.replace(_32,_2d);
};
_25.findTags(/(\n|^)*[ ]{0,3}([*+-]|\d+[.])\s+/,null);
var _33=/^\n/;
if(_25.before&&!/\n$/.test(_25.before)&&!_33.test(_25.startTag)){
_25.before+=_25.startTag;
_25.startTag="";
}
if(_25.startTag){
var _34=/\d+[.]/.test(_25.startTag);
_25.startTag="";
_25.selection=_25.selection.replace(/\n[ ]{4}/g,"\n");
_8.unwrap(_25);
_25.skipLines();
if(_34){
_30();
}
if(_26==_34){
return;
}
}
var _35=1;
var _31=_6.regexToString(_27);
_31.expression="(\\n|^)"+_31.expression+"$";
var _36=_6.stringToRegex(_31);
_25.before=_25.before.replace(_36,function(_37){
if(/^\s*([*+-])/.test(_37)){
_28=_4.$1;
}
_35=/[^\n]\n\n[^\n]/.test(_37)?1:0;
return _2d(_37);
});
if(!_25.selection){
_25.selection="List item";
}
var _38=_2a();
var _39=1;
_31=_6.regexToString(_27);
_31.expression="^\n*"+_31.expression;
_36=_6.stringToRegex(_31);
_25.after=_25.after.replace(_36,function(_3a){
_39=/[^\n]\n\n[^\n]/.test(_3a)?1:0;
return _2d(_3a);
});
_25.trimWhitespace(true);
_25.skipLines(_35,_39,true);
_25.startTag=_38;
var _3b=_38.replace(/./g," ");
_8.wrap(_25,_2.wmd_env.lineLength-_3b.length);
_25.selection=_25.selection.replace(/\n/g,"\n"+_3b);
};
_8.doHeading=function(_3c){
_3c.selection=_3c.selection.replace(/\s+/g," ");
_3c.selection=_3c.selection.replace(/(^\s+|\s+$)/g,"");
var _3d=0;
_3c.findTags(/#+[ ]*/,/[ ]*#+/);
if(/#+/.test(_3c.startTag)){
_3d=_4.lastMatch.length;
}
_3c.startTag=_3c.endTag="";
_3c.findTags(null,/\s?(-+|=+)/);
if(/=+/.test(_3c.endTag)){
_3d=1;
}
if(/-+/.test(_3c.endTag)){
_3d=2;
}
_3c.startTag=_3c.endTag="";
_3c.skipLines(1,1);
if(!_3c.selection){
_3c.startTag="## ";
_3c.selection="Heading";
_3c.endTag=" ##";
return;
}
var _3e=_3d==0?2:_3d-1;
if(_3e){
var _3f=_3e>=2?"-":"=";
var _40=_3c.selection.length;
if(_40>_2.wmd_env.lineLength){
_40=_2.wmd_env.lineLength;
}
_3c.endTag="\n";
while(_40--){
_3c.endTag+=_3f;
}
}
};
_8.ol={};
_8.ol.description="Numbered List <ol>";
_8.ol.image="/images/wmd/ol.png";
_8.ol.key="o";
_8.ol.textOp=function(_41){
_8.doList(_41,true);
};
_8.ul={};
_8.ul.description="Bulleted List <ul>";
_8.ul.image="/images/wmd/ul.png";
_8.ul.key="u";
_8.ul.textOp=function(_42){
_8.doList(_42,false);
};
_8.h1={};
_8.h1.description="Heading <h1>/<h2>";
_8.h1.image="/images/wmd/h1.png";
_8.h1.key="h";
_8.h1.textOp=_8.doHeading;
_8.hr={};
_8.hr.description="Horizontal Rule <hr>";
_8.hr.image="/images/wmd/hr.png";
_8.hr.key="r";
_8.hr.textOp=function(_43){
_43.startTag="----------\n";
_43.selection="";
_43.skipLines(2,1,true);
};
};
if(Attacklab.fileLoaded){
Attacklab.fileLoaded("wmd-plus.js");
}

