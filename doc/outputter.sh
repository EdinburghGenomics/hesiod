#!/bin/sh

# This script prints the first arg to stdout, the second to stderr and then
# exits with the status given in arg 3. Useful for testing.

[ -z "${1:-}" ] || echo $1
[ -z "${2:-}" ] || echo $2 >&2
exit ${3:-0}
