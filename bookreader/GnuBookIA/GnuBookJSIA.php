<?
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

$id = $_REQUEST['id'];
$itemPath = $_REQUEST['itemPath'];
$server = $_REQUEST['server'];

if ("" == $id) {
    GBFatal("No identifier specified!");
}

if ("" == $itemPath) {
    GBFatal("No itemPath specified!");
}

if ("" == $server) {
    GBFatal("No server specified!");
}


if (!preg_match("|^/[0-3]/items/{$id}$|", $itemPath)) {
    GBFatal("Bad id!");
}

$zipFile = "$itemPath/{$id}_jp2.zip";
if (!file_exists($zipFile)) {
    GBFatal("JP2 zip file not found!");
}

$scanDataFile = "$itemPath/{$id}_scandata.xml";
$scanDataZip  = "$itemPath/scandata.zip";
if (file_exists($scanDataFile)) {
    $scanData = simplexml_load_file($scanDataFile);    
} else if (file_exists($scanDataZip)) {
    $cmd  = 'unzip -p ' . escapeshellarg($scanDataZip) . ' scandata.xml';
    exec($cmd, $output, $retval);
    if ($retval != 0) GBFatal("Could not unzip ScanData!");
    
    $dump = join("\n", $output);
    $scanData = simplexml_load_string($dump);    
} else {
    GBFatal("ScanData file not found!");
}

$metaDataFile = "$itemPath/{$id}_meta.xml";
if (!file_exists($metaDataFile)) {
    GBFatal("MetaData file not found!");
}


$metaData = simplexml_load_file($metaDataFile);

//$firstLeaf = $scanData->pageData->page[0]['leafNum'];
?>

gb = new GnuBook();

gb.getPageWidth = function(index) {
    //return parseInt(this.pageW[index]/this.reduce);
    return this.pageW[index];
}

gb.getPageHeight = function(index) {
    //return parseInt(this.pageH[index]/this.reduce);
    return this.pageH[index];
}

gb.getPageURI = function(index) {
    var leafStr = '0000';            
    var imgStr = this.leafMap[index].toString();
    var re = new RegExp("0{"+imgStr.length+"}$");

    if (1==this.mode) {
        var url = 'http://'+this.server+'/GnuBook/GnuBookJP2.php?zip='+this.zip+'&file='+this.bookId+'_jp2/'+this.bookId+'_'+leafStr.replace(re, imgStr) + '.jp2&scale='+this.reduce;
    } else {
        var url = 'http://'+this.server+'/GnuBook/GnuBookJP2.php?zip='+this.zip+'&file='+this.bookId+'_jp2/'+this.bookId+'_'+leafStr.replace(re, imgStr) + '.jp2&height='+this.twoPageH+'&origHeight='+this.getPageHeight(index);
    }
    return url;
}

gb.getPageSide = function(index) {
    //assume the book starts with a cover (right-hand leaf)
    //we should really get handside from scandata.xml
    if (0 == (index & 0x1)) {
        return 'R';
    } else {
        return 'L';
    }
}

gb.getPageNum = function(index) {
    return this.pageNums[index];
}

gb.leafNumToIndex = function(leafNum) {
    var index = jQuery.inArray(leafNum, this.leafMap);
    if (-1 == index) {
        return null;
    } else {
        return index;
    }
}



gb.pageW =		[
            <?
            $i=0;
            foreach ($scanData->pageData->page as $page) {
                if ("true" == $page->addToAccessFormats) {
                    if(0 != $i) echo ",";   //stupid IE
                    echo "{$page->cropBox->w}";
                    $i++;
                }
            }
            ?>
            ];

gb.pageH =		[
            <?
            $totalHeight = 0;
            $i=0;            
            foreach ($scanData->pageData->page as $page) {
                if ("true" == $page->addToAccessFormats) {
                    if(0 != $i) echo ",";   //stupid IE                
                    echo "{$page->cropBox->h}";
                    $totalHeight += intval($page->cropBox->h/4) + 10;
                    $i++;
                }
            }
            ?>
            ];
gb.leafMap = [
            <?
            $i=0;
            foreach ($scanData->pageData->page as $page) {
                if ("true" == $page->addToAccessFormats) {
                    if(0 != $i) echo ",";   //stupid IE
                    echo "{$page['leafNum']}";
                    $i++;
                }
            }
            ?>    
            ];

gb.pageNums = [
            <?
            $i=0;
            foreach ($scanData->pageData->page as $page) {
                if ("true" == $page->addToAccessFormats) {
                    if(0 != $i) echo ",";   //stupid IE                
                    if (array_key_exists('pageNumber', $page) && ('' != $page->pageNumber)) {
                        echo "{$page->pageNumber}";
                    } else {
                        echo "null";
                    }
                    $i++;
                }
            }
            ?>    
            ];
        
gb.numLeafs = gb.pageW.length;

gb.bookId   = '<?echo $id;?>';
gb.zip      = '<?echo $zipFile;?>';
gb.server   = '<?echo $server;?>';
gb.bookTitle= '<?echo preg_replace("/\'/", "&#039;", $metaData->title);?>';
gb.bookPath = '<?echo $itemPath;?>';
gb.bookUrl  = '<?echo "http://www.archive.org/details/$id";?>';
<?
if ('bandersnatchhsye00scarrich' == $id) {
    echo "gb.mode     = 2;\n";
    echo "gb.auto     = true;\n";
}
?>
gb.init();

<?


function GBFatal($string) {
    echo "alert('$string')\n";
    die(-1);
}
?>