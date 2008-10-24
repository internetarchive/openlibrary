<?php
/*
Copyright(c)2008 Internet Archive. Software license AGPL version 3.

This file is part of GnuBook.

    GnuBook is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    GnuBook is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with GnuBook.  If not, see <http://www.gnu.org/licenses/>.
*/

// FIXME: TODO: Change path above to production installation location of perl
// when we deploy, Brad Neuberg, bkn3@columbia.edu
//
// From:
//   search.cgi v0.4
//   by Ralf Muehlen
//
// slight alterations by Brad Neuberg, bkn3@columbia.edu
//
// ported from perl to php by tracey, Oct 2005

//fixxx require_once '/petabox/setup.inc';
$_SERVER['DOCUMENT_ROOT']='/petabox/www/sf'; 
require_once '/petabox/setup.inc';
ini_set("memory_limit","200M"); // XML can be big, esp. brittanica (100MB)

/////// SETUP /////////////////////////////////////////////////////////////

$debug_level = 0; // 0=least, 3=most debugging info

$num_pre  = 3; // context words before search term
$num_post = 9; // context words after  search term


// defaults for testing (when no args given)
$url ='http://ia300202.us.archive.org/0/items/englishbookbindings00davenuoft/englishbookbindings00davenuoft_djvuxml.xml';

$term = "history";
$format = "XML";
$callback = false;

/////// SETUP /////////////////////////////////////////////////////////////


// fixxx prolly should escapesystemcall() these...
if (isset($_GET['url']))
  $url =        $_GET['url'];
if (isset($_GET['term']))
  $term =       $_GET['term'];
if (isset($_GET['format']))
  $format =     $_GET['format'];
if (isset($_GET['callback']))
  $callback =     $_GET['callback'];

//$url='http://homeserver.hq.archive.org/metafetch/thespy00cooparch_djvu.xml';
//$url='http://homeserver.hq.archive.org/metafetch/oldchristmas00irviarch_djvu.xml';
//$url = 'http://homeserver.hq.archive.org/metafetch/intlepisode00jamearch_djvu.xml';
  

if ($format == "XML")
{
  // This is kinda weird (confession!) but allows existing calls to "fatal()"
  // to throw an exception instead of dumping HTML to stdout/browser!
  $GLOBALS['fatal-exceptions']=1;
}
try
{


// pageFiles was added to keep track of on what page each search match was
// found, Brad Neuberg, bkn3@columbia.edu
// pageHeights and pageWidths was added to track the size of each page so that
// we can send it over to the client; this is necessary for scaling the images
// for search, Brad Neuberg, bkn3@columbia.edu
$pages =       array();
$pageFiles =   array();
$pageHeights = array();
$pageWidths =  array();


$time0 = microtime(true);
$timestamp = date('Y-m-d H:i:s');
$pid = posix_getpid();
debug_msg("Invoked at ".$time0."=$timestamp under UID ".posix_getuid(),2);
 


//////////////////////////////////////

debug_msg("query: ".$_SERVER['QUERY_STRING'],3);


$term = preg_replace('/[^A-Za-z0-9 ]/', ' ', $term); // legal characters
$terms = explode(' ',$term);
debug_msg("url,term,format: $url,".var_export($terms,true).",$format",3);


if ($format == "HTML")
{
  echo "<html><head><title>Search</title></head> <body> Searching <p>";
  $tag_pre  = '<b style="color:black;background-color:#A0FFFF">';
  $tag_post = '</b>';
}
else if ($format == "XML")
{
  if (false === $callback) {
      header('Content-type: text/xml');
  } else {
      header('application/x-javascript');
  }
  $tag_pre  = '</CONTEXT>';
  $tag_post = '<CONTEXT>';
}
else
{
  fatal("Unknown format request. ");
}
 


if (!($document = file_get_contents($url)))
  fatal("could not load $url");



$time1 = microtime(true) - $time0;


//// Pass 1
$pagenumber=0;
foreach (explode('</OBJECT>', $document) as $page)
{
  $pagenumber++;
  if (matches_terms($page, $terms)  &&
      // 2nd clause here is to ensure that we aren't matching in the end
      // of the overall XML document -- thus we ensure that OBJECT tag starts
      // in the chunk we just were handed.  (traceyj)
      strstr($page, '<OBJECT '))
  {
    // extract the page value so that we know what page we are on,
    // Brad Neuberg, bkn3@columbia.edu
    if (!preg_match('|<PARAM name="PAGE" value="([^"]*)"\s*\/>|', $page, $match))
      fatal("page value not set on page number $pagenumber in $page!");
    $pageFile = $match[1];
    
    // extract the page width and height, Brad Neuberg, bkn3@columbia.edu
    if (!preg_match('/width="([^"]*)"/', $page, $match))
      fatal("page width not set!");
    $pageWidth = $match[1];

    if (!preg_match('/height="([^"]*)"/', $page, $match))
      fatal("page height not set!");
    $pageHeight = $match[1];
    
    $page_new='';
    foreach (explode('</WORD>',$page) as $token)
    {
      if (matches_terms($token, $terms))
      {
        list($junk, $keep) = explode('<WORD ',$token);
        $token = " $tag_pre<WORD $keep</WORD>$tag_post "; 
      }
      else
      {
        $token = preg_replace('/<[^<]*>/','', $token);     //mark-up
        $token = preg_replace('/[\&\#\d+;]/', ' ', $token);//non-ascii chars
        $token = preg_replace('/\s+/', ' ', $token);       //white space
      }

      $page_new .= $token;
    }

    
    
    $page_new =
      preg_replace('|.*((\W\w*){'.$num_pre.'}'.$tag_pre.')|',"$1",$page_new);
    $page_new =
      preg_replace('/('.$tag_post.'(\w*\W){'.$num_post.'}).*/',"$1",$page_new);
    
    
    // added to keep track of the page we are on
    // Brad Neuberg, bkn3@columbia.edu
    $pageFiles  [$pagenumber] = $pageFile;
    $pages      [$pagenumber] = $page_new;
    // added to keep track of page widths and heights
    $pageWidths [$pagenumber] = $pageWidth;
    $pageHeights[$pagenumber] = $pageHeight;
  }
}


$time2 =  microtime(true) - $time1;

//// Pass 2 


if ($format == "HTML")
{
  echo "Found ".count($pages)." pages containing $tag_pre";
  print_r($terms);
  echo "$tag_post.<br>\n";
  foreach ($pages as $index => $page)
  {
    echo "<h4>Page $page:</h4>\n";
    print_r($page);
    echo "<p><br><p>\n";
  }
  $time3 = microtime(true) - $time2;
  echo $tag_pre . "Fetched document in $time1 ms.$tag_post<p>\n";
  echo $tag_pre . "Processed document in $time2 ms.$tag_post<p>\n";
  echo $tag_pre . "Printed document in $time3 ms.$tag_post<p>\n";
  echo "</body></html>\n";
}
else if ($format == "XML")
{
  $xml = "";
  $xml .= '<?xml version="1.0" encoding="utf-8"?>'."\n";
  // Added to prevent Internet Explorer from adding default XML stylesheet,
  // which messes up processing, Brad Neuberg, bkn3@columbia.edu
  $xml .= '<?xml-stylesheet type="text/css" href="blank.css"?>'."\n";//fixxx
  $xml .= '<SEARCH>';

  foreach ($pages as $index => $page)
  {
    $xml .= "<PAGE file=\"{$pageFiles[$index]}\" width=\"{$pageWidths[$index]}\" height=\"{$pageHeights[$index]}\">\n";
    $xml .= "<CONTEXT>\n";
    $xml .= $page;
    $xml .= "</CONTEXT>\n";
    $xml .= "</PAGE>\n";
  }
  $xml .= "</SEARCH>\n";
  $fsm = FlipSearchMap::buildSearchMap($url);
  if (false === $callback) {
      echo $fsm->remapSearch($xml);
  } else {
      $patterns[0] = '/\n/';
      $patterns[1] = "/\'/";
      $replac[0]   = '';
      $replac[1]   = '&#39;';
      echo "$callback('". preg_replace($patterns, $replac, $fsm->remapSearch($xml))."');";
  }
  //echo $xml;
}

//////
debug_msg("Done and exiting!",2);
exit;
//////
}
catch (Exception $e)
{
  // an internal method call invoked "fatal()"...
  XML::resultMessage('error','internal_error', $e->getMessage());
}




function matches_terms(&$text, // search space
                       &$terms)// array of search terms
{
  foreach ($terms as $term)
  {
    if (preg_match("/$term/i", $text))
      return true;
  }
  return false;
}


function debug_msg($msg, $level)
{
  global $debug_level;
  global $pid;
  global $format;
  if ($level <= $debug_level)
  {
    if ($format == "XML")
      echo "<!-- FILL  ($pid):$level: $msg -->\n";
    else
      echo "FILL  ($pid):$level: $msg<br/>\n";
  }
}


?>
