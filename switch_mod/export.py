# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Functions to help export results.


"""

import csv
import itertools
from pyomo.environ import value

csv.register_dialect(
    "ampl-tab",
    delimiter="\t",
    lineterminator="\n",
    doublequote=False, escapechar="\\",
    quotechar='"', quoting=csv.QUOTE_MINIMAL,
    skipinitialspace=False
)


def write_table(instance, *indexes, **kwargs):
    # there must be a way to accept specific named keyword arguments and
    # also an  open-ended list of positional arguments (*indexes), but I
    # don't know what that is.
    output_file = kwargs["output_file"]
    headings = kwargs["headings"]
    values = kwargs["values"]
    # create a master indexing set
    # this is a list of lists, even if only one list was specified
    idx = itertools.product(*indexes)
    with open(output_file, 'wb') as f:
        w = csv.writer(f, dialect="ampl-tab")
        # write header row
        w.writerow(list(headings))
        # write the data
        # global rows
        # rows=[value(v) for x in idx for v in values(instance, *x)]
        # print(rows)
        w.writerows(
            tuple(value(v) for v in values(instance, *x))
            for x in idx
        )
