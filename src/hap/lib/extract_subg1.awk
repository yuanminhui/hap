{
    if (FNR == NR) {
        # store node ids in memory
        if ($0 ~ /^P/) { 
            split($3, a, ",")
            for (i in a) {
                sid = substr(a[i], 1, length(a[i]) - 1)
                if (!(sid in sidarr)) {
                    sidarr[sid]
                }
            }
        }
        if ($0 ~ /^W/) { 
            split($7, a, "[<>]")
            for (i = 2; i in a; i++) {
                sid = a[i]
                if (!(sid in sidarr)) {
                    sidarr[sid]
                }
            }
        }
    }
    else {
        # extract header
        if ($0 ~ /^H/) {
            print $0
        }

        # extract node
        if ($0 ~ /^S/) { 
            if ($2 in sidarr) {
                print $0
            }
        }

        # extract edge
        if ($0 ~ /^L/) {
            if (($2 in sidarr) || ($4 in sidarr)) {
                print $0
            }
        }
    }
}