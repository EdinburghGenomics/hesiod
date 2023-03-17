"""YAML Utility funcs broken out from hesiod/__init__.py

   These use the ordered loader/saver (yamlloader) which is basically the
   same as my yaml_ordered hack. It should go away with Py3.7.
"""
import os
from collections import namedtuple
import yaml, yamlloader

class _MyYAMLDumper(yamlloader.ordereddict.CSafeDumper):
    """Subclass of the yamlloader dumper which dumps multi-line strings in the '|'
       style but short strings in the regular style. Why this is not default I have
       no idea.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_representer(str, self.my_representer)
        self.default_flow_style = False

    def my_representer(self, dumper, data):
        style = '|' if '\n' in data else None

        # Note that if the str contains unrepresentable chars or trailing whitespace
        # it will still be forced back to quoted style so this is robust.
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style=style)

def dump_yaml(foo, filename=None):
    """Return YAML string and optionally dump to a file (not a file handle).
    """
    ydoc = yaml.dump(foo, Dumper=_MyYAMLDumper)
    if filename:
        with open(filename, 'w') as yfh:
            print(ydoc, file=yfh, end='')
    return ydoc

def load_yaml(filename, relative_to=None, as_tuple=None):
    """Load YAML from a file (not a file handle).
       If specified, relative paths are resolved relative to os.path.dirname(relative_to)
    """
    filename = str(filename) # Allow for directly passing Snakemake inputs
    with open(abspath(filename, relative_to)) as yfh:
        res = yaml.load(yfh, Loader=yamlloader.ordereddict.CSafeLoader)

    if not as_tuple:
        return res

    else:
        # This is just to make the syntax a little cleaner in the Snakefile
        return namedtuple(as_tuple, res)(**res)

def abspath(filename, relative_to=None):
    """Version of abspath which can optionally be resolved relative to another file.
    """
    if relative_to and not filename.startswith('/'):
        return os.path.abspath(os.path.join(os.path.dirname(relative_to), filename))
    else:
        return os.path.abspath(filename)

