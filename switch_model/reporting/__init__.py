# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
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
from __future__ import print_function
from switch_model.utilities import string_types, add_info
from switch_model.utilities.scaling import get_unscaled_var
dependencies = 'switch_model.financials'


import os
import csv
import itertools
try:
    # Python 2
    import cPickle as pickle
except ImportError:
    import pickle
from pyomo.environ import value, Var, Expression
from pyomo.core.base.set import UnknownSetDimen
from switch_model.utilities import make_iterable

csv.register_dialect(
    "switch-csv",
    delimiter=",",
    lineterminator="\n",
    doublequote=False, escapechar="\\",
    quotechar='"', quoting=csv.QUOTE_MINIMAL,
    skipinitialspace=False
)

def define_arguments(argparser):
    argparser.add_argument(
        "--save-expressions", "--save-expression", dest="save_expressions", nargs='+',
        default=[], action='extend',
        help="List of expressions to save in addition to variables; can also be 'all' or 'none'."
    )

def get_cell_formatter(sig_digits, zero_cutoff):
    sig_digits_formatter = "{0:." + str(sig_digits) + "g}"

    def format_cell(c):
        if not isinstance(c, float):
            return c
        if abs(c) < zero_cutoff:
            return 0
        else:
            return sig_digits_formatter.format(c)
    return format_cell


def format_row(row, cell_formatter):
    return tuple(cell_formatter(get_value(v)) for v in row)


def write_table(instance, *indexes, output_file=None, **kwargs):
    # there must be a way to accept specific named keyword arguments and
    # also an open-ended list of positional arguments (*indexes), but I
    # don't know what that is.
    if output_file is None:
        raise Exception("Must specify output_file in write_table()")
    cell_formatter = get_cell_formatter(instance.options.sig_figs_output, instance.options.zero_cutoff_output)

    if 'df' in kwargs:
        df = kwargs.pop('df')
        df.applymap(cell_formatter).to_csv(output_file, **kwargs)
        return

    headings = kwargs["headings"]
    values = kwargs["values"]

    with open(output_file, 'w') as f:
        w = csv.writer(f, dialect="switch-csv")
        # write header row
        w.writerow(list(headings))
        # write the data
        try:
            rows = (format_row(values(instance, *unpack_elements(x)), cell_formatter) for x in
                    itertools.product(*indexes))
            w.writerows(sorted(rows) if instance.options.sorted_output else rows)
        except TypeError: # lambda got wrong number of arguments
            # use old code, which doesn't unpack the indices
            w.writerows(
                # TODO: flatten x (unpack tuples) like Pyomo before calling values()
                # That may cause problems elsewhere though...
                format_row(values(instance, *x), cell_formatter)
                for x in itertools.product(*indexes)
            )
            print("DEPRECATION WARNING: switch_model.reporting.write_table() was called with a function")
            print("that expects multidimensional index values to be stored in tuples, but Switch now unpacks")
            print("these tuples automatically. Please update your code to work with unpacked index values.")
            print("Problem occured with {}.".format(values.__code__))

def unpack_elements(items):
    """Unpack any multi-element objects within items, to make a single flat list.
    Note: this is not recursive.
    This is used to flatten the product of a multi-dimensional index with anything else."""
    l=[]
    for x in items:
        if isinstance(x, string_types):
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


def save_generic_results(instance, outdir, sorted_output):
    cell_formatter = get_cell_formatter(instance.options.sig_figs_output, instance.options.zero_cutoff_output)

    components = list(instance.component_objects(Var))
    # add Expression objects that should be saved, if any
    if 'none' in instance.options.save_expressions:
        # drop everything up till the last 'none' (users may have added more after that)
        last_none = (
            len(instance.options.save_expressions)
            - instance.options.save_expressions[::-1].index('none')
        )
        instance.options.save_expressions = instance.options.save_expressions[last_none:]

    if 'all' in instance.options.save_expressions:
        components += list(instance.component_objects(Expression))
    else:
        components += [getattr(instance, c) for c in instance.options.save_expressions]

    for var in components:
        var = get_unscaled_var(instance, var)
        output_file = os.path.join(outdir, '%s.csv' % var.name)
        with open(output_file, 'w') as fh:
            writer = csv.writer(fh, dialect='switch-csv')
            if var.is_indexed():
                index_set = var.index_set()
                index_name = index_set.name
                if index_set.dimen == UnknownSetDimen:
                    raise Exception(f"Index {index_name} has unknown dimension. Specify dimen= during its creation.")
                # Write column headings
                writer.writerow(['%s_%d' % (index_name, i + 1)
                                 for i in range(index_set.dimen)] +
                                [var.name])
                # Results are saved in a random order by default for
                # increased speed. Sorting is available if wanted.
                items = sorted(var.items()) if sorted_output else list(var.items())
                for key, obj in items:
                    writer.writerow(format_row(tuple(make_iterable(key)) + (obj,), cell_formatter))
            else:
                # single-valued variable
                writer.writerow([var.name])
                writer.writerow(format_row([obj], cell_formatter))

def get_value(obj):
    """
    Retrieve value of one element of a Variable or Expression, converting
    division-by-zero to nan and uninitialized values to None.
    """
    try:
        val = value(obj)
    except ZeroDivisionError:
        # diagnostic expressions sometimes have 0 denominator,
        # e.g., AverageFuelCosts for unused fuels;
        val = float("nan")
    except ValueError:
        # If variables are not used in constraints or the
        # objective function, they will never get values, and
        # give a ValueError at this point.
        # Note: for variables this could instead use 0 if allowed, or
        # otherwise the closest bound.
        if getattr(obj, 'value', 0) is None:
            val = None
            # Pyomo will print an error before it raises the ValueError,
            # but we say more here to help users figure out what's going on.
            print (
                "WARNING: variable {} has not been assigned a value. This "
                "usually indicates a coding error: either the variable is "
                "not needed or it has accidentally been omitted from all "
                "constraints and the objective function.".format(obj.name)
            )
        else:
            # Caught some other ValueError
            raise
    return val


def save_total_cost_value(instance, outdir):
    total_cost = round(value(instance.SystemCost), ndigits=2)
    add_info("Total Cost", f"$ {total_cost}")
    with open(os.path.join(outdir, 'total_cost.txt'), 'w') as fh:
        fh.write(f'{total_cost}\n')


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
        list(cost_dict.keys()),
        output_file=os.path.join(outdir, "cost_components.csv"),
        headings=('component', 'npv_cost'),
        values=lambda m, c: (c, cost_dict[c])
    )
