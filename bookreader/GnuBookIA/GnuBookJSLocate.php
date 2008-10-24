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

require_once '/petabox/setup.inc';

$id = $_REQUEST['id'];

if ("" == $id) {
    echo "No identifier specified!";
    die(-1);
}

$locator      = new Locator();

$results = $locator->locateUDP($id, 1, true);

$url = "http://{$results[0][0]}/GnuBook/GnuBookJSIA.php?id={$id}&itemPath={$results[0][1]}&server={$results[0][0]}";


if (("" != $results[0][0]) && ("" != $results[0][1])) {
    header("Location: $url");
}

?>