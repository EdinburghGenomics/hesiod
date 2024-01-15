#!/usr/bin/env python3
import os, sys, re
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import configparser
from rt import Rt, AuthorizationError
import logging as L

from hesiod import dump_yaml

"""This will translate a project number to a project name by connecting to RT and
   looking for a ticket in the eg-projects queue.

   It's not ideal, but it should be useful.
"""

# Project links can be set by an environment var, presumably in environ.sh
# Note that we also respect GENOLOGICSRC and PROJECT_NAME_LIST
PROJECT_PAGE_URL = os.environ.get('PROJECT_PAGE_URL', "http://foo.example.com/")
try:
    if PROJECT_PAGE_URL.format('test') == PROJECT_PAGE_URL:
        PROJECT_PAGE_URL += '{}'
except Exception:
    print("The environment variable PROJECT_PAGE_URL={} is not a valid format string.".format(
                PROJECT_PAGE_URL), file=sys.stderr)
    raise

def main(args):

    L.basicConfig(level=(L.DEBUG if args.debug else L.INFO), stream=sys.stderr)

    if args.take5:
        projects = set([ s[:5] for s in args.projects ])
    else:
        projects = args.projects

    name_list = os.environ.get('PROJECT_NAME_LIST')
    if name_list:
        res = projects_from_fixed_list(projects, name_list.split(","))
    else:
        rt_config_name = os.environ.get('RT_SYSTEM', 'test-rt' if args.test else 'production-rt')
        res = project_real_name( projects, rt_config = rt_config_name,
                                           queue = args.queue )

    # Assuming no exception occurred...
    print(dump_yaml(res, args.out), end='')


def project_real_name(projects, rt_config, queue):

    res = dict()

    with RTManager( config_name = rt_config,
                    queue_setting = queue ) as rtm:

        for p in projects:

            ticket_id, ticket_dict = rtm.search_project_ticket(p)
            if ticket_id:
                ticket_subject = ticket_dict['Subject']
            else:
                L.warning(f"No ticket found for {p!r}")
                ticket_subject = ""

            #L.info(f"Ticket #{ticket_id} for '{p}' has subject: {ticket_dict.get('Subject')}")
            mo = re.search(rf" ({p}_\w+)", ticket_subject)

            if mo:
                res[p] = dict( name = mo.group(1),
                               url = PROJECT_PAGE_URL.format(mo.group(1)) )
            elif p.startswith("Contr"):
                res[p] = dict( name = "Control" )
            else:
                res[p] = dict( name = p + "_UNKNOWN" )

    return res

def projects_from_fixed_list(projects, pnl):
    """Allows bypassing RT, normally for testing.
        Note that if you want to disable RT look-up without supplying an actual
        list of names you can just say "--project_names dummy" or some such thing.
    """
    res = dict()

    for p in projects:
        name_match = [ n for n in pnl if n.startswith(p) ]
        if len(name_match) == 1:
            res[p] = dict( name = name_match[0],
                           url  = PROJECT_PAGE_URL.format(name_match[0]) )
        elif p.startswith("Contr"):
            res[p] = dict( name = "Control" )
        else:
            res[p] = dict( name = p + "_UNKNOWN" )

    return res

class RTManager():
    def __init__(self, config_name, queue_setting):
        """Communication with RT is managed via the RT module.
           This wrapper picks up connection params from an .ini file,
           which must exist before you can even instatiate the object.

           To actually connect, either call connect() explicitly or say:
             with RTManager('test-rt') as rt_conn:
                ...
           to connect implicitly.
        """
        self._config_name = config_name
        self._queue_setting = queue_setting # eg. pbrun, run
        if config_name.lower() == 'none':
            # Special case for short-circuiting RT entirely, whatever the .ini
            # file says.
            self._config = None
        else:
            self._config = self._get_config_from_ini(config_name)

        self.tracker = None

    def connect(self, timeout=60):

        if not self._config:
            L.warning("Making dummy connection - all operations will be no-ops.")
            return self

        self.server_path = self._config['server']
        self.username, self.password = self._config['user'], self._config['pass']
        self._queue = self._config.get(f"{self._queue_setting}_queue", self._queue_setting)

        self.tracker = Rt( '/'.join([self.server_path, 'REST', '1.0']),
                           self.username,
                           self.password,
                           default_queue = self._queue )

        if not self.tracker.login():
            raise AuthorizationError(f'login() failed on {self._config_name} ({self.tracker.url})')

        # Here comes the big monkey-patch-o-doom!
        # It will force a 60-second timeout on the Rt session, assuming the internal implementation
        # of session is not changed in the requests library.
        from types import MethodType
        foo = self.tracker.session
        foo._merge_environment_settings = foo.merge_environment_settings
        foo.merge_environment_settings = MethodType(
                lambda s, *a: dict([*s._merge_environment_settings(*a).items(), ('timeout', s.timeout)]),
                foo )
        foo.timeout = timeout
        # End of monkey business

        return self

    # Allow us to use this in a 'with' clause.
    def __enter__(self):
        return self.connect()
    def __exit__(self, *exc):
        # Can you logout of RT? Do you want to?
        pass

    def _get_config_from_ini(self, section_name):

        # Either read the config pointed to by RT_SETTINGS or else the default.
        # Don't attempt to read both, even though ConfigParser supports it.
        file_name = os.environ.get('RT_SETTINGS')
        file_name = file_name or os.path.join(os.path.expanduser('~'), '.rt_settings')

        cp = configparser.ConfigParser()
        if not cp.read(file_name):
            raise AuthorizationError(f'unable to read configuration file {file_name}')

        # A little validation
        if section_name not in cp:
            raise AuthorizationError(f'file {file_name} contains no configuration section {section_name}')

        conf_section = cp[section_name]

        # A little more validation
        for x in ['server', 'user', 'pass']:
            if not conf_section.get(x):
                raise AuthorizationError(f"file {file_name} did not contain setting {x} needed for RT authentication")

        return conf_section


    # The actual methods
    def search_project_ticket(self, project_number):
        """Search for a ticket referencing this project, and return the ticket number,
           as an integer, along with the ticket metadata as a dict,
           or return (None, None) if there is no such ticket.
        """
        tickets = list(self.tracker.search( Queue = self._queue,
                                            Subject__like = f'% {project_number}_%',
                                          ))

        if not tickets:
            return (None, None)

        # Order the tickets by tid and get the highest one
        def get_id(t): return int(t['id'].strip('ticket/'))
        tickets.sort(key=get_id, reverse=True)
        tid = get_id(tickets[0])

        if len(tickets) > 1:
            L.warning(f"Warning: We have {len(tickets)} tickets matching {project_number}."
                      f" Using the latest, {tid}")

        #Failing that...
        return (tid, tickets[0]) if tid > 0 else (None, None)

def parse_args(*args):
    description = """This script allows you to look up a project name by searching
                     the tickets in the eg-projects queue on RT.
                  """
    argparser = ArgumentParser( description=description,
                                formatter_class = ArgumentDefaultsHelpFormatter )
    argparser.add_argument("projects", nargs="+",
                            help="The project(s) to look up.")
    argparser.add_argument("-Q", "--queue", default="eg-projects",
                            help="The queue to use. A name defined in rt_settings.ini as FOO_queue,"
                                 " or a literal queue name.")
    argparser.add_argument("--test", action="store_true",
                            help="Set the script to connect to test-rt (as defined in rt_settings.ini)")

    argparser.add_argument("-o", "--out",
                            help="Where to save the report. If there is an error nothing will be written. Report is always printed.")
    argparser.add_argument("-t", "--take5", action="store_true",
                            help="Just use the first five chars of the project names given. Allows me to pass a list of library/cell names.")
    argparser.add_argument("-d", "--debug", action="store_true",
                            help="Print more verbose debugging messages.")

    return argparser.parse_args(*args)


if __name__ == "__main__":
    main(parse_args())
