"""marc"""
import re

re_leader = re.compile('^\d{5}.{19}$')
re_control = re.compile('\d{3} ')
re_data = re.compile(r'\d{3} (..) \$')

def is_display_marc(data):
    if data.startswith('(Length implementation at offset 22 should hold a digit. Assuming 0)'):
        return True
    try:
        lines = data.split('\n')
        leader = lines[0]
        assert re_leader.match(leader)
        for line in lines[1:]:
            if line.startswith('00'):
                assert re_control.match(line)
            else:
                assert re_data.match(line)
        return True
    except AssertionError:
        return False

def test_is_display_marc():
    samples = [
        ('melbaysdeluxehar00dunc', "00628nam  2200157 a 4500\n008\n020    $a 0871663821\n100 1  $a Duncan, Phil.\n245 10 $a Mel Bay's deluxe harmonica method $b a thorough study for the individual or group/ $c Phil Duncan.\n260    $a Pacific, MO : $b Mel Bay, $c 1981.\n300    $a 108 p. : $b ill.\n650  0 $a Harmonica $v Methods $v Self-instruction.\n650  0 $a Harmonica music.\n907    $a .b14612021 $b 02-17-04 $c 02-17-04\n998    $a 3cw $b 02-17-04 $c m $d a $e - $f eng $g us  $h 0 $i 1\n945    $a 788.82193 Dun $g 0 $i 36431100583926 $l 3cwan $o   $p $8.00 $q   $r   $s - $t 201 $u 0 $v 0 $w 0 $x 0 $y .i18341184 $z 02-17-04"),
        ('howtodeal00dess', '00760nam  2200205   4500\n008\n020    $a 0142501034\n100 1  $a Dessen, Sarah.\n245 10 $a How to deal / $c Sarah Dessen.\n260    $a New York : $c 2003.\n300    $a 486 p.\n650  0 $a Pregnancy $v Fiction.\n650  0 $a Unmarried moters $v Fiction.\n605  0 $a Friendship $v Fiction.\n907    $a .b14124932 $b 08-13-04 $c 07-08-03\n998    $a 3cw $a 4gc $b 07-08-03 $c m $d a $e   $f eng $g us  $h 0 $i 1\n946    $a cw $b jaj $c 2003-07-08\n947    $a gc $b cm $c 2003-09-04\n945    $a PAP Y Fic Des $g 0 $i 36431100561534 $l 3cwjp $o   $p $7.00 $q   $r   $s - $t 206 $u 17 $v 2 $w 2 $x 3 $y .i17522845 $z 07-08-03\n945    $a Fic $b Dessen $g 0 $i 39562100662679 $l 4gc   $o   $p $7.99 $q   $r   $s - $t 130 $u 7 $v 0 $w 0 $x 2 $y .i18029565 $z 09-04-03'),
    ]

