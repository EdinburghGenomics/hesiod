#!/bin/bash

# I want to capture the output of outputter.sh into variable 'foo'
# I want any stderr to go to stdout and if the script returns a non-zero
# value then I want to sub a different string.

# This fails because STDERR goes to STDERR
try1(){
    foo="$(doc/outputter.sh STDOUT STDERR || echo Alt string)"

    echo "\$foo is *$foo*"
}

# This doesn't work
try2(){
    foo="$(doc/outputter.sh STDOUT STDERR 1 2>&1 || echo Alt string)"

    echo "\$foo is *$foo*"
}

# This has the same problem
try3(){
    foo="$(doc/outputter.sh STDOUT STDERR 0 2>&1)" || foo="Alt string"

    echo "\$foo is *$foo*"
}

# Here the redirection has no effect
try3(){
    foo="$(doc/outputter.sh STDOUT STDERR 0)" 2>&1 || foo="Alt string"

    echo "\$foo is *$foo*"
}

try4(){
    { foo="$(doc/outputter.sh STDOUT STDERR 2>&3 0)" || foo="Alt string" ;
      echo "REAL_STDERR" >&2
    } 3>&1

    echo "\$foo is *$foo*"
}

try4 | nl
