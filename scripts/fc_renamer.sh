#!/bin/bash
# Quickie script to rename files in the old runs to add the Checksum.

# Note - this is actully useless since the filenames end up in the count and md5sum
# files and the blobdb, and the only way to get them out is to start from scratch.
# Meh.

# First get all the old filenames, which I can do by looking for _fail.fastq.gz
# files (which seem the most likely to have).

bases=(`find | grep '_fail\.fastq\.gz$' | sed 's/_fail\.fastq\.gz$//' | sed 's,^\./,,'`)

#echo "${bases[@]}"

for b in "${bases[@]}" ; do

    new_end=`grep -o '_PAD....._......../'  <<<$b | sed 's,/$,,'`
    old_end=`grep -o '_PAD.....' <<<$new_end`

    echo sed "s/${old_end}\$/${new_end}/"
    new_name=`sed "s/${old_end}\$/${new_end}/" <<<$b`

    if [ "$b" == "$new_name" ] ; then
        echo FAIL "$b"
        exit 1
    fi

    echo 'FROM' $b
    echo 'TO  ' $new_name

    # Now I can simply rename the files
    # Note we need to remove lambdaqc first because here some filenames
    # have been copied into directory names.
    find | grep "$b" | xargs prename -n -v "s[(.*/.*)$old_end][\$1$new_end]"

done
