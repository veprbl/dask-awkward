from __future__ import annotations

try:
    import ujson as json
except ImportError:
    import json  # type: ignore

import os
import tempfile
from typing import Any

import awkward._v2.highlevel as ak
import fsspec
import pytest
from awkward._v2.operations.convert import from_iter
from dask.base import is_dask_collection

from ..core import Array, Scalar, from_awkward
from ..io import from_json

# fmt: off
MANY_RECORDS = \
    """{"analysis":{"x1":[1,2,3],"y1":[2,3,4],"z1":[2,6,6],"t1":[7,8,9],"x2":[],"y2":[],"z2":[],"t2":[]}}
{"analysis":{"x1":[1,2],"y1":[2,3],"z1":[3,4],"t1":[4,5],"x2":[2,9],"y2":[2,8],"z2":[2,7],"t2":[0,6]}}
{"analysis":{"x1":[],"y1":[],"z1":[],"t1":[],"x2":[3,2,1],"y2":[4,3,2],"z2":[5,4,3],"t2":[6,5,4]}}
{"analysis":{"x1":[],"y1":[],"z1":[],"t1":[],"x2":[1,2,3],"y2":[2,3,4],"z2":[2,6,6],"t2":[7,8,9]}}
{"analysis":{"x1":[3,2,1],"y1":[4,3,2],"z1":[5,4,3],"t1":[6,5,4],"x2":[],"y2":[],"z2":[],"t2":[]}}
{"analysis":{"x1":[],"y1":[],"z1":[],"t1":[],"x2":[1,2],"y2":[2,3],"z2":[2,6],"t2":[7,8]}}
{"analysis":{"x1":[3,2,1,4],"y1":[4,3,2,5],"z1":[5,4,3,6],"t1":[6,5,4,7],"x2":[1,2],"y2":[3,4],"z2":[5,6],"t2":[7,8]}}
{"analysis":{"x1":[1,2,3],"y1":[2,3,4],"z1":[2,6,6],"t1":[7,8,9],"x2":[],"y2":[],"z2":[],"t2":[]}}
{"analysis":{"x1":[1,2],"y1":[2,3],"z1":[3,4],"t1":[4,5],"x2":[2,9],"y2":[2,8],"z2":[2,7],"t2":[0,6]}}
{"analysis":{"x1":[],"y1":[],"z1":[],"t1":[],"x2":[3,2,1],"y2":[4,3,2],"z2":[5,4,3],"t2":[6,5,4]}}
{"analysis":{"x1":[],"y1":[],"z1":[],"t1":[],"x2":[1,2,3],"y2":[2,3,4],"z2":[2,6,6],"t2":[7,8,9]}}
{"analysis":{"x1":[3,2,1],"y1":[4,3,2],"z1":[5,4,3],"t1":[6,5,4],"x2":[],"y2":[],"z2":[],"t2":[]}}
{"analysis":{"x1":[2,9],"y1":[2,8],"z1":[2,7],"t1":[0,6],"x2":[1,2],"y2":[2,3],"z2":[3,4],"t2":[4,5]}}
{"analysis":{"x1":[],"y1":[],"z1":[],"t1":[],"x2":[3,2,1],"y2":[4,3,2],"z2":[5,4,3],"t2":[6,5,4]}}
{"analysis":{"x1":[3,2,1],"y1":[4,3,2],"z1":[5,4,3],"t1":[6,5,4],"x2":[],"y2":[],"z2":[],"t2":[]}}
{"analysis":{"x1":[2,9],"y1":[2,8],"z1":[2,7],"t1":[0,6],"x2":[1,2],"y2":[2,3],"z2":[3,4],"t2":[4,5]}}
{"analysis":{"x1":[1,9,1],"y1":[1,8,2],"z1":[1,7,3],"t1":[1,6,4],"x2":[3,2,5],"y2":[3,3,6],"z2":[3,4,7],"t2":[3,5,8]}}
{"analysis":{"x1":[],"y1":[],"z1":[],"t1":[],"x2":[1,2],"y2":[2,3],"z2":[2,6],"t2":[7,8]}}
{"analysis":{"x1":[3,2,1,4],"y1":[4,3,2,5],"z1":[5,4,3,6],"t1":[6,5,4,7],"x2":[1,2],"y2":[3,4],"z2":[5,6],"t2":[7,8]}}
{"analysis":{"x1":[1,2,3],"y1":[2,3,4],"z1":[2,6,6],"t1":[7,8,9],"x2":[],"y2":[],"z2":[],"t2":[]}}"""


SINGLE_RECORD = """{"a":[1,2,3]}"""
# fmt: on


def assert_eq(a: Any, b: Any) -> None:
    if is_dask_collection(a) and not is_dask_collection(b):
        if isinstance(a, Scalar):
            assert a.compute() == b
        else:
            assert a.compute().to_list() == b.to_list()
    elif is_dask_collection(b) and not is_dask_collection(a):
        if isinstance(b, Scalar):
            assert a == b.compute()
        else:
            assert a.to_list() == b.compute().to_list()
    else:
        if isinstance(a, Scalar) and isinstance(b, Scalar):
            assert a.compute() == b.compute()
        else:
            assert a.compute().to_list() == b.compute().to_list()


@pytest.fixture(scope="session")
def line_delim_records_file(tmpdir_factory):
    """Fixture providing a file name pointing to line deliminted JSON records."""
    fn = tmpdir_factory.mktemp("data").join("records.json")
    with open(fn, "w") as f:
        f.write(MANY_RECORDS)
    return str(fn)


@pytest.fixture(scope="session")
def single_record_file(tmpdir_factory):
    """Fixture providing file name pointing to a single JSON record."""
    fn = tmpdir_factory.mktemp("data").join("single-record.json")
    with open(fn, "w") as f:
        f.write(SINGLE_RECORD)
    return str(fn)


def records_from_temp_file(n_times: int = 1) -> ak.Array:
    """Get a concrete Array of records from a temporary file.

    Parameters
    ----------
    n_times : int
        Number of times to parse the file file of records.

    Returns
    -------
    Array
        Resulting concrete Awkward Array.

    """
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(MANY_RECORDS)
        name = f.name
    x = load_records_eager(name, n_times=n_times)
    os.remove(name)
    return x


def single_record_from_temp_file() -> ak.Array:
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write(SINGLE_RECORD)
        name = f.name
    x = load_single_record_eager(name)
    os.remove(name)
    return x


def load_records_lazy(
    fn: str,
    blocksize: int | str = 700,
    by_file: bool = False,
    n_times: int = 1,
) -> Array:
    """Load a record array Dask Awkward Array collection.

    Parameters
    ----------
    fn : str
        File name.
    blocksize : int | str
        Blocksize in bytes for lazy reading.
    by_file : bool
        Read by file instead of by bytes.
    n_times : int
        Number of times to read the file.

    Returns
    -------
    Array
        Resulting Dask Awkward Array collection.

    """
    if by_file:
        return from_json([fn] * n_times)
    return from_json(fn, blocksize=blocksize)


def load_records_eager(fn: str, n_times: int = 1) -> ak.Array:
    """Load a concrete Awkward record array.

    Parameters
    ----------
    fn : str
        File name.
    n_times : int
        Number of times to read the file.

    Returns
    -------
    Array
        Resulting concrete Awkward Array.

    """
    files = [fn] * n_times
    loaded = []
    for ff in files:
        with fsspec.open(ff) as f:
            loaded += list(json.loads(line) for line in f)
    return from_iter(loaded)


def load_single_record_lazy(fn: str) -> Array:
    return from_json(
        fn,
        delimiter=None,
        blocksize=None,
        one_obj_per_file=True,
    )


def load_single_record_eager(fn: str) -> ak.Array:
    with fsspec.open(fn) as f:
        d = json.load(f)
    return ak.Array([d])


# def lazy_records_from_awkward(n_times: int = 1, npartitions: int = 5):
#     return from_awkward(records_from_temp_file(n_times), npartitions=npartitions)


# def lazy_record_from_awkward():
#     return from_awkward(single_record_from_temp_file(), npartitions=1)

LAZY_RECORDS = from_awkward(records_from_temp_file(), npartitions=5)
LAZY_RECORD = from_awkward(single_record_from_temp_file(), npartitions=1)