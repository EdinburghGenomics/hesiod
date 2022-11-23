import configargparse
import os

# Set a single env var as config
os.environ['FOO'] = "configured_value"

# The first iteration works fine. The second not so much.
for f_nargs in [None, '?']:

    p = configargparse.ArgParser()
    p.add('--foo', '-f', nargs=f_nargs, env_var='FOO', required=False)
    p.add('bar', nargs='*')

    options = p.parse_args(['--', 'arg1', 'arg2'])
    print("when f_nargs is {!r}".format(f_nargs))
    print(options)
    print("----------")
