<?php
header('Content-type: application/xml');
$handle = fopen($_REQUEST['url'], "r");

if ($handle) {
    while (!feof($handle)) {
        $buffer = fgets($handle, 4096);
        echo $buffer;
    }
    fclose($handle);
}
?>
