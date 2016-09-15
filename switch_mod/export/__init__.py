# Copyright 2015 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

"""

Functions to help export results.

Modules within this directory may implement custom exports that
depend on multiple Switch modules. Each individual Switch module
that defines components should only access model components that
it defined or that were defined upstream in Switch modules that 
it depends on. For example, the load_zone module cannot assume whether users
will be including project.no_commit or project.unitcommit, so it cannot
reference model components defined in either of those files. However,
both project.no_commit and project.unitcommit can assume that components
defined in load_zones will be available because they have an explicit
dependency on load_zones.


"""

import os
import csv
import itertools
from pyomo.environ import value, Var

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
        w.writerows(
            tuple(value(v) for v in values(instance, *x))
            for x in idx
        )


def make_iterable(item):
    """Return an iterable for the one or more items passed."""
    if isinstance(item, basestring):
        i = iter([item])
    else:
        try:
            # check if it's iterable
            i = iter(item)
        except TypeError:
            i = iter([item])
    return i


def _save_generic_results(instance, outdir, deterministic_order=False):
    for var in instance.component_objects():
        if not isinstance(var, Var):
            continue

        index_name = var.index_set().name
        output_file = os.path.join(outdir, '%s.tab' % var.name)
        with open(output_file, 'wb') as fh:
            writer = csv.writer(fh, dialect='ampl-tab')
            # Write column headings
            writer.writerow(['%s_%d' % (index_name, i + 1)
                             for i in xrange(var.index_set().dimen)] +
                            [var.name])
            # Results are saved in a random order by default for
            # increased speed. Sorting is available if wanted.
            for key, obj in (sorted(var.items())
                            if deterministic_order
                            else var.items()):
                writer.writerow(tuple(make_iterable(key)) + (obj.value,))


def _save_total_cost_value(instance, outdir):
    values = instance.Minimize_System_Cost.values()
    assert len(values) == 1
    total_cost = values[0].expr()
    with open(os.path.join(outdir, 'total_cost.txt'), 'w') as fh:
        fh.write('%s\n' % total_cost)


def post_solve(instance, outdir):
    """
    Minimum output generation for all model runs.
    
    """
    _save_generic_results(instance, outdir)
    _save_total_cost_value(instance, outdir)
