#!/usr/bin/gawk -f

# AWK is really fast, right? Let us see. Otherwise I'd just do this in Python...
# usage: cat in.fq | awk -v paf=in.paf -v lambda=lambda.fq -v nolambda=nolambda.fq splitter.awk

# in.fq is a fastq file you want to partition
# in.paf is an alignment file produced by minimap2. May also be BAM format as long as
#        --sam-hit-only was used
# lambda.fq  is where you want the mapped reads to go (in our case, those that map to lambda)
# nolambda.fq is where you want the unmapped reads to go (in our case the real stuff)

# If you miss out lambda or nolambda then those reads will just be discarded.

# In a one-shot:
# $ awk -f splitter.awk <test_fullsize.fq \
#     -v paf=<(minimap2 --secondary=no -x map-ont phage_lambda.mmi test_fullsize.fq) \
#     -v lambda=>(gzip -c > lambda_fullsize.fq.gz) \
#     -v nolambda=>(gzip -c > nolambda_fullsize.fq.gz)

BEGIN{ spool = 0 ; pafid = 0 }
{
    if(spool != 0) {
        spool--
    }
    else {
        while(pafid != 0 || (getline pafline <paf) > 0) {
            # We're still looking for the last pattern?
            if(pafid != 0) break
            # pafline is a SAM header?
            if(substr(pafline,1,1) == "@") continue
            # Or we just read a real new line...
            split(pafline, pafparts) ; pafid = "@"pafparts[1]
            # Is this a new pattern to look for or the same as the old one?
            if( pafid != lastpafid ) break
            # Nope, try again
            pafid = 0
        }

        # No more patterns? Spool forever!
        if(pafid == 0) {
            dest = nolambda
            spool = -1
        }
        # See if our pattern matches the FASTQ header
        else {
            if($1 == pafid) {
                dest = lambda
                lastpafid = pafid
                pafid = 0
            }
            else{
                dest = nolambda
            }
            spool = 3
        }
    }
    # Print to whatever dest file
    if(dest) print >>dest
}
# By the end, pafid should be empty
END{ if(pafid != 0){ print "Error: pafid="pafid ; exit 1 } }
