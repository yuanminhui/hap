# extract_subgraph_unified.awk
# Extract all GFA structural lines (H/S/L/E) for segments referenced in path records
# Works for ALL GFA versions (1.0, 1.1, 1.2, 2.0) - unified implementation
# Usage: awk -f extract_subgraph_unified.awk path_records.txt input.gfa > output_main.gfa
#
# Two-pass processing:
# Pass 1 (FNR==NR): Read path_records.txt, collect all segment IDs
# Pass 2 (FNR!=NR): Extract H/S/L/E lines that reference collected segments

BEGIN {
    FS = OFS = "\t"
}

{
    if (FNR == NR) {
        # ========== FIRST PASS: Collect segment IDs from path records ==========

        # P lines (GFA 1.0): P <path_name> <segment_names> <overlaps>
        # segment_names format: "s1+,s2-,s3+"
        if ($0 ~ /^P/) {
            split($3, segments, ",")
            for (i in segments) {
                seg = segments[i]
                if (seg == "") continue
                # Remove orientation (+/-)
                seg_id = substr(seg, 1, length(seg) - 1)
                if (!(seg_id in sidarr)) {
                    sidarr[seg_id]
                }
            }
        }

        # O lines (GFA 2.0): O <path_name> <segment_references>
        # segment_references format: "s1+ s2- s3+"
        if ($0 ~ /^O/) {
            split($3, segments, " ")
            for (i in segments) {
                seg = segments[i]
                if (seg == "") continue
                seg_id = substr(seg, 1, length(seg) - 1)
                if (!(seg_id in sidarr)) {
                    sidarr[seg_id]
                }
            }
        }

        # W lines (GFA 1.1/1.2): W <sample> <hap_index> <seq_name> <start> <end> <walk>
        # walk format: ">s1>s2<s3"
        if ($0 ~ /^W/) {
            walk_str = $7
            # Split by orientation markers (> or <)
            split(walk_str, segments, "[<>]")
            # segments[1] is empty, segments[2..n] are segment IDs
            for (i = 2; i in segments; i++) {
                seg_id = segments[i]
                if (seg_id != "" && !(seg_id in sidarr)) {
                    sidarr[seg_id]
                }
            }
        }

        # U lines (GFA 2.0): U <set_name> <id_list>
        # id_list format: "s1 s2 s3"
        if ($0 ~ /^U/) {
            split($3, segments, " ")
            for (i in segments) {
                seg_id = segments[i]
                if (seg_id != "" && !(seg_id in sidarr)) {
                    sidarr[seg_id]
                }
            }
        }
    }
    else {
        # ========== SECOND PASS: Extract structural lines from main GFA ==========

        # Always include header
        if ($0 ~ /^H/) {
            print $0
        }

        # Extract segments that are in our collected segment ID set
        if ($0 ~ /^S/) {
            if ($2 in sidarr) {
                print $0
            }
        }

        # Extract links (GFA 1.x): L <from> <from_orient> <to> <to_orient> <overlap>
        if ($0 ~ /^L/) {
            if (($2 in sidarr) || ($4 in sidarr)) {
                print $0
            }
        }

        # Extract edges (GFA 2.0): E <eid> <sid1><orient1> <sid2><orient2> <beg1> <end1> <beg2> <end2> <alignment>
        if ($0 ~ /^E/) {
            # Extract segment IDs from oriented references (remove last char which is orientation)
            source = substr($3, 1, length($3) - 1)
            target = substr($4, 1, length($4) - 1)
            if ((source in sidarr) || (target in sidarr)) {
                print $0
            }
        }
    }
}
