import configargparse
from configargparse import YAMLConfigFileParser

from tempfile import NamedTemporaryFile

# Emit a simple config file
tf = NamedTemporaryFile(mode="w")
print("foo: configured_value", file=tf)
tf.flush()

# The first works fine. The second breaks.
for f_nargs in [None, '?']:

    p = configargparse.ArgParser(
            default_config_files = [tf.name],
            config_file_parser_class = YAMLConfigFileParser )
    p.add('--foo', '-f', nargs=f_nargs, required=False, help='optional argument')
    p.add('bar', nargs='*', help='positional arguments')

    options = p.parse_args(['--', 'arg1', 'arg2'])
    print(options)
    print("----------")
