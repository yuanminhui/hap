{
    if (FNR == NR) {
        # store node ids in memory
        if ($0 ~ /^O/) { 
            split($3, a, " ")
            for (i in a) {
                sid = substr(a[i], 1, length(a[i]) - 1)
                if (!(sid in sidarr)) {
                    sidarr[sid]
                }
            }
        }
        if ($0 ~ /^U/) { 
            split($3, a, " ")
            for (i in a) {
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
        if ($0 ~ /^E/) {
            source = substr($3, 1, length($3) - 1);
            target = substr($4, 1, length($4) - 1);
            if ((source in sidarr) || (target in sidarr)) {
                print $0
            }
        }
    }
}