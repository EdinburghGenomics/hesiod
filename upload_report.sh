#!/bin/bash
set -euo pipefail

# If you just want to push existing reports to the server, see the RSYNC line below.
# Eg:
#  rsync -drvlOt all_reports web1.genepool.private:/var/runinfo/heasiod_reports/$(basename $(pwd))/

# See doc/how_to_display.txt for thoughts on how this should really work.
# Normal report destination is web1.genepool.private:/var/runinfo/hesiod_reports

# See where to get the report from (by default, right here)
# The run name could theoretically be different from the 'true' run name but we want the report
# location to match the direcotry name where the run is stored.
cd "${1:-.}"
runname="`basename $PWD`"

# Confirm we do have all_reports/report.html
if [ ! -L all_reports/report.html ] || [ ! -e all_reports/report.html ] ; then
    echo "No such file all_reports/report.html or it is not a link." >&2
    false
fi

# Check where (and if) we want to push reports on the server.
if [ "${REPORT_DESTINATION:-none}" == none ] ; then
    echo "Skipping report upload, as no \$REPORT_DESTINATION is set." >&2
    # This will go into RT in place of a link. It's not an error - you can legitimately
    # switch off uploading for testing etc.
    echo '[upload of report was skipped as no REPORT_DESTINATION was set]'
    exit 0
fi
dest="${REPORT_DESTINATION}"

# Note the proxy setting in my ~/.ssh/config which lets both ssh
# and rsync run through monitor transparently. Really we should have direct access to the
# DMZ machines.
echo "Uploading report for $runname to $dest/..." >&2
rsync -drvlOt all_reports $dest/$runname/ >&2
#rsync -drvLOt all_reports/img $dest/$runname/all_reports/ >&2

# Add the index. We now have to make this a PHP script but at least the content is totally fixed.
# This is very similar to what we have on Illuminatus (but not quite).
ssh -T ${dest%%:*} "cat > ${dest#*:}/$runname/index.php" <<'END'
<?php
    # Script added by upload_report.sh in Hesiod.
    # First resolve symlink. The subtlety here is that anyone saving the link will get a permalink,
    # and anyone just reloading the page in their browser will see the old one. I think that's
    # OK. It's easy to change in any case.
    $latest = readlink("all_reports/report.html");
    # Get my own url and slice off index.php and/or / if found. No, I'm not fluent in PHP!
    $myurl = strtok($_SERVER["REQUEST_URI"],'?');
    if( preg_match('/' . basename(__FILE__) . '$/', $myurl )){
        $myurl = substr( $myurl, 0, -(strlen(basename(__FILE__))) );
    }
    if( preg_match(',/$,', $myurl )){
        $myurl = substr( $myurl, 0, -1 );
    }
    header("Location: $myurl/all_reports/$latest", true, 302);
    exit;
?>
<html>
<head>
<title>Redirect</title>
<meta name="robots" content="none" />
</head>
<body>
   You should be redirected to <a href='all_reports/report.html'>all_reports/report.html</a>
</body>
</html>
END

echo "...done. Report uploaded and index.php written to ${dest#*:}/$runname/." >&2

# Say where to find it:
# eg. http://web1.genepool.private/runinfo/hesiod_reports/...
echo "${REPORT_LINK:-$REPORT_DESTINATION}/$runname"
