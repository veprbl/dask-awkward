import dask_awkward.utils as daku


def test_normalize_single_outer_inner_index():
    divisions = [0, 12, 14, 20, 22]
    indices = [0, 1, 2, 8, 12, 13, 14, 15, 17, 20, 21, 22]
    results = [
        (0, 0),
        (0, 1),
        (0, 2),
        (0, 8),
        (1, 0),
        (1, 1),
        (2, 0),
        (2, 1),
        (2, 3),
        (3, 0),
        (3, 1),
        (3, -1),
    ]
    for i, r in zip(indices, results):
        res = daku.normalize_single_outer_inner_index(divisions, i)
        assert r == res