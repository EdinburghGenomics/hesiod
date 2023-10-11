
join3() {
    # A general join function in Bash, with a prefix, delim and postfix
    local prefix="$1"  ; shift
    local delim="$1"   ; shift
    local postfix="$1" ; shift
    local res=""
    local i
    if [ $# -gt 0 ] ; then
        res="$1"
        shift
        for i in "$@" ; do
            res+="$delim""$i"
        done
    fi
    printf "%s%s%s" "$prefix" "$res" "$postfix"
}

printf "%s\n" "$(join3 - $',\n' $'-\n' a "b c")"
