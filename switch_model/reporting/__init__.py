# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

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
dependencies = 'switch_model.financials'


import os
import csv
import itertools
import cPickle as pickle
from pyomo.environ import value, Var
from switch_model.utilities import make_iterable

csv.register_dialect(
    "ampl-tab",
    delimiter="\t",
    lineterminator="\n",
    doublequote=False, escapechar="\\",
    quotechar='"', quoting=csv.QUOTE_MINIMAL,
    skipinitialspace=False
)

def define_arguments(argparser):
    argparser.add_argument(
        "--sorted-output", default=False, action='store_true',
        dest='sorted_output',
        help='Write generic variable result values in sorted order')

def write_table(instance, *indexes, **kwargs):
    # there must be a way to accept specific named keyword arguments and
    # also an open-ended list of positional arguments (*indexes), but I
    # don't know what that is.
    output_file = kwargs["output_file"]
    headings = kwargs["headings"]
    values = kwargs["values"]
    digits = kwargs.get('digits', 6)

    with open(output_file, 'wb') as f:
        w = csv.writer(f, dialect="ampl-tab")
        # write header row
        w.writerow(list(headings))
        # write the data
        def format_row(row):
            row = [value(v) for v in row]
            sig_digits = "{0:." + str(digits) + "g}"
            for (i, v) in enumerate(row):
                if isinstance(v, float):
                    if abs(v) < 1e-10:
                        row[i] = 0
                    else:
                        row[i] = sig_digits.format(v)
            return tuple(row)

        try:
            w.writerows(
                format_row(row=values(instance, *unpack_elements(x)))
                for x in itertools.product(*indexes)
            )
        except TypeError: # lambda got wrong number of arguments
            # use old code, which doesn't unpack the indices
            w.writerows(
                # TODO: flatten x (unpack tuples) like Pyomo before calling values()
                # That may cause problems elsewhere though...
                format_row(row=values(instance, *x))
                for x in itertools.product(*indexes)
            )
            print "DEPRECATION WARNING: switch_model.reporting.write_table() was called with a function"
            print "that expects multidimensional index values to be stored in tuples, but Switch now unpacks"
            print "these tuples automatically. Please update your code to work with unpacked index values."
            print "Problem occured with {}.".format(values.func_code)

def unpack_elements(items):
    """Unpack any multi-element objects within items, to make a single flat list.
    Note: this is not recursive.
    This is used to flatten the product of a multi-dimensional index with anything else."""
    l=[]
    for x in items:
        if isinstance(x, basestring):
            l.append(x)
        else:
            try:
                l.extend(x)
            except TypeError: # x isn't iterable
                l.append(x)
    return l


def post_solve(instance, outdir):
    """
    Minimum output generation for all model runs.
    """
    save_generic_results(instance, outdir, instance.options.sorted_output)
    save_total_cost_value(instance, outdir)
    save_cost_components(instance, outdir)
    save_results(instance, outdir)


def save_generic_results(instance, outdir, sorted_output):
    for var in instance.component_objects(Var):
        output_file = os.path.join(outdir, '%s.tab' % var.name)
        with open(output_file, 'wb') as fh:
            writer = csv.writer(fh, dialect='ampl-tab')
            if var.is_indexed():
                index_name = var.index_set().name
                # Write column headings
                writer.writerow(['%s_%d' % (index_name, i + 1)
                                 for i in xrange(var.index_set().dimen)] +
                                [var.name])
                # Results are saved in a random order by default for
                # increased speed. Sorting is available if wanted.
                for key, obj in (sorted(var.items())
                                if sorted_output
                                else var.items()):
                    writer.writerow(tuple(make_iterable(key)) + (obj.value,))
            else:
                # single-valued variable
                writer.writerow([var.name])
                writer.writerow([value(obj)])


def save_total_cost_value(instance, outdir):
    with open(os.path.join(outdir, 'total_cost.txt'), 'w') as fh:
        fh.write('{}\n'.format(value(instance.SystemCost)))


def save_cost_components(m, outdir):
    """
    Save values for all individual components of total system cost on NPV basis.
    """
    cost_dict = dict()
    for annual_cost in m.Cost_Components_Per_Period:
        cost = getattr(m, annual_cost)
        # note: storing value() instead of the expression may save
        # some memory while this function runs
        cost_dict[annual_cost] = value(sum(
            cost[p] * m.bring_annual_costs_to_base_year[p]
            for p in m.PERIODS
        ))
    for tp_cost in m.Cost_Components_Per_TP:
        cost = getattr(m, tp_cost)
        cost_dict[tp_cost] = value(sum(
            cost[t] * m.tp_weight_in_year[t]
            * m.bring_annual_costs_to_base_year[m.tp_period[t]]
            for t in m.TIMEPOINTS
        ))
    write_table(
        m,
        cost_dict.keys(),
        output_file=os.path.join(outdir, "cost_components.tab"),
        headings=('component', 'npv_cost'),
        values=lambda m, c: (c, cost_dict[c]),
        digits=16
    )


def save_results(instance, outdir):
    """
    Save model solution for later reuse.

    Note that this pickles a solver results object because the instance itself
    cannot be pickled -- see
    https://stackoverflow.com/questions/39941520/pyomo-ipopt-does-not-return-solution
    """
    # First, save the full solution data to the results object, because recent
    # versions of Pyomo only store execution metadata there by default.
    instance.solutions.store_to(instance.last_results)
    with open(os.path.join(outdir, 'results.pickle'), 'wb') as fh:
        pickle.dump(instance.last_results, fh, protocol=-1)
    # remove the solution from the results object, to minimize long-term memory use
    instance.last_results.solution.clear()
