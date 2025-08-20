import io
from pathlib import Path
from hypothesis import given, strategies as st
from hap.lib import sequence as seqmod


_HDR_ALPHABET = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


@given(
    st.lists(
        st.tuples(
            st.text(alphabet=_HDR_ALPHABET, min_size=1, max_size=20),
            st.text(alphabet=list("ATCGN-"), min_size=0, max_size=100),
        ),
        min_size=1,
        max_size=10,
    )
)
def test_roundtrip_tsv_fasta(records):
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        tsv = os.path.join(d, "r.tsv")
        with open(tsv, "w") as fh:
            for hdr, seq in records:
                fh.write(f"{hdr}\t{seq}\n")
        fa = os.path.join(d, "r.fa")
        with open(fa, "w") as out:
            n = seqmod.write_tsv_to_fasta(Path(tsv), out)
        assert n == len(records)

