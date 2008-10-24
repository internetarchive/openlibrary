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

header('Content-type: image/jpeg');

$zipPath  = $_REQUEST['zip'];
$file     = $_REQUEST['file'];


if (isset($_REQUEST['height'])) {
    $ratio = floatval($_REQUEST['origHeight']) / floatval($_REQUEST['height']);

    if ($ratio <= 2) {
        $reduce = 1;    
    } else if ($ratio <= 4) {
        $reduce = 2;
    } else {
        //$reduce = 3; //too blurry!
        $reduce = 1;
    }

} else {
    $scale    = $_REQUEST['scale'];
    if (1 >= $scale) {
        $reduce = 0;
    } else if (2 == $scale) {
        $reduce = 1;
    } else if (4 == $scale) {
        $reduce = 2;
    } else {
        $reduce = 3;
    }
}

if (!file_exists('/tmp/stdout.ppm')) 
{  
  system('ln -s /dev/stdout /tmp/stdout.ppm');  
}


putenv('LD_LIBRARY_PATH=/petabox/sw/lib/kakadu');


$cmd  = 'unzip -p ' . 
        escapeshellarg($zipPath) .
        ' ' .
        escapeshellarg($file) .
        " | /petabox/sw/bin/kdu_expand -no_seek -quiet -reduce $reduce -i /dev/stdin -o /tmp/stdout.ppm ";
        
if (isset($_REQUEST['height'])) {
    $cmd .= " | pnmscale -height {$_REQUEST['height']} ";
}

$cmd .= ' | pnmtojpeg -quality 90';


passthru ($cmd);
#print $cmd;
?>

