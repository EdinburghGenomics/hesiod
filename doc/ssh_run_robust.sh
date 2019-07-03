#!/bin/bash

# How to robustly run a command via SSH?

# It's nigh-on impossible!!

_nl=0 ; _p=0 ; _f=0
function assertEqual(){
#    if [ "$(eval "cat <<<"$1"")" != "$(eval "cat <<<"$2"")" ] ; then
    if [ "$(eval printf %s "$1")" != "$(eval printf %s "$2")" ] ; then
        #echo "FAIL - '$(eval "cat <<<"$1"")' != '$(eval "cat <<<"$2"")'"
        echo "FAIL - '$(eval printf %s \"$1\")' != '$(eval printf %s \"$2\")'"
        _nl=0
        _f=$(( $_f + 1 ))
    else
        echo -n .
        _nl=1
        _p=$(( $_p + 1 ))
    fi
}

function end(){
    [[ _nl == 0 ]] || echo
    echo $_p PASS, $_f FAIL
}

foo=`ssh localhost echo 123`
assertEqual \$foo 123

# This works but the <<< happens locally
foo=`ssh localhost cat <<<456`
assertEqual \$foo 456

# This is fine as the whole command is quoted
foo=`ssh localhost 'eep=789 ; echo $eep'`
assertEqual \$foo 789

# The problem is when you need to quote a filename then put it in a command
silly_file="A file with \$\$   spaces"
foo=`ssh localhost "echo $silly_file"`
assertEqual \$foo \$silly_file

# The problem is when you need to quote a filename then put it in a command
silly_file="A file with \$\$   spaces"
silly_file_q=$(printf '%q' "$silly_file")
foo=`ssh localhost "echo $silly_file_q"`
assertEqual \$foo \$silly_file

end
