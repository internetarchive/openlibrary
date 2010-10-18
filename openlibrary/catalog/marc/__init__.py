"""marc"""
import re

re_leader = re.compile('^\d{5}.{19}$')
re_control = re.compile('\d{3} ')
re_data = re.compile(r'\d{3} (..) \$')

def is_display_marc(data):
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
