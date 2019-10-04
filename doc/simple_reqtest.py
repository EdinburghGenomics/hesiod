# Test for the 'why do the frickin HTTPS certs not work?' issue.
# See /etc/pki/tls/certs/how_to_add_a_cert.txt

# Ok, so the default bundle is given by certifi:
#  python3 -m certifi
# But this bundle does not have the cert I need for RT??
# The package is up-to-date. Well, I guess I need to keep manually overriding things.
# At least I found a setting that fixes all cases:
# env REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt

import requests

r = requests.get('https://api.github.com/user')
r = requests.get('https://pypi.org/project/requests')
r = requests.get('https://rt.genomics.ed.ac.uk')
r = requests.get('https://clarity.genomics.ed.ac.uk')
r = requests.get('https://nextgenbug.org')
