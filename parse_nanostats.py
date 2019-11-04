#!/usr/bin/env python3

import sys, re
import yaml
from pprint import pprint

def main():
    """Read lines from STDIN and make a YAML file, since NanoStats.txt
       is not properly structured text.
       I'm using a list output so no need to worry about the OrderedDict hack here.
    """
    res = []

    all_lines = [l.strip() for l in sys.stdin]

    # Possibly the stats are empty? This can happen if nothing passes.
    if all_lines:

        assert all_lines[0] == "General summary:"

        res.append( [ all_lines[0].split(':')[0], [] ] )
        summary_bits = res[-1][1]

        for l in all_lines[1:]:
            if ':' in l:
                summary_bits.append([v.strip() for v in l.split(':')])
            else:
                res.append( [ l, [] ] )
                summary_bits = res[-1][1]

        # Now see if we can parse out some numbers
        for cat, lines in res:
            for l in lines:
                for bit in l[1].split():
                    bit = bit.strip('();')
                    try:
                        if '.' in bit:
                            l.append( float(re.sub('[,Mb%]', '', bit)) )
                        else:
                            l.append( int(re.sub('[,Mb%]', '', bit)) )
                    except ValueError:
                        l.append(bit)

    #pprint(res)
    print(yaml.safe_dump(res), end='')

if __name__ == '__main__':
    main()
