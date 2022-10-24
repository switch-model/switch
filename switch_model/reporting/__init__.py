# Copyright (c) 2015-2022 The Switch Authors. All rights reserved.
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
from switch_model.utilities import string_types, UnknownSetDimen

dependencies = "switch_model.financials"


import os
import csv
import itertools

try:
    # Python 2
    import cPickle as pickle
except ImportError:
    import pickle
from pyomo.environ import value, Var, Expression
from switch_model.utilities import make_iterable

csv.register_dialect(
    "switch-csv",
    delimiter=",",
    lineterminator="\n",
    doublequote=False,
    escapechar="\\",
    quotechar='"',
    quoting=csv.QUOTE_MINIMAL,
    skipinitialspace=False,
)


def define_arguments(argparser):
    argparser.add_argument(
        "--skip-generic-output",
        default=False,
        action="store_true",
        dest="skip_generic_output",
        help="Skip exporting generic variable results",
    )
    argparser.add_argument(
        "--save-expressions",
        "--save-expression",
        dest="save_expressions",
        nargs="+",
        default=[],
        action="extend",
        help="List of expressions to save in addition to variables; can also be 'all' or 'none'.",
    )


def write_table(instance, *indexes, **kwargs):
    # there must be a way to accept specific named keyword arguments and
    # also an open-ended list of positional arguments (*indexes), but I
    # don't know what that is.
    output_file = kwargs["output_file"]
    headings = kwargs["headings"]
    values = kwargs["values"]
    digits = kwargs.get("digits", 6)

    with open(output_file, "w") as f:
        w = csv.writer(f, dialect="switch-csv")
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

        idx = list(itertools.product(*indexes))
        if instance.options.sorted_output:
            idx.sort()

        try:
            w.writerows(
                format_row(row=values(instance, *unpack_elements(x))) for x in idx
            )
        except TypeError:  # lambda got wrong number of arguments
            # use old code, which doesn't unpack the indices
            w.writerows(
                # TODO: flatten x (unpack tuples) like Pyomo before calling values()
                # That may cause problems elsewhere though...
                format_row(row=values(instance, *x))
                for x in idx
            )
            print(
                "DEPRECATION WARNING: switch_model.reporting.write_table() was called with a function"
            )
            print(
                "that expects multidimensional index values to be stored in tuples, but Switch now unpacks"
            )
            print(
                "these tuples automatically. Please update your code to work with unpacked index values."
            )
            print("Problem occured with {}.".format(values.__code__))


def unpack_elements(items):
    """Unpack any multi-element objects within items, to make a single flat list.
    Note: this is not recursive.
    This is used to flatten the product of a multi-dimensional index with anything else."""
    l = []
    for x in items:
        if isinstance(x, string_types):
            l.append(x)
        else:
            try:
                l.extend(x)
            except TypeError:  # x isn't iterable
                l.append(x)
    return l


def post_solve(instance, outdir):
    """
    Minimum output generation for all model runs.
    """
    if not instance.options.skip_generic_output:
        save_generic_results(instance, outdir, instance.options.sorted_output)
    save_total_cost_value(instance, outdir)
    save_cost_components(instance, outdir)


def save_generic_results(instance, outdir, sorted_output):
    components = list(instance.component_objects(Var))
    # add Expression objects that should be saved, if any
    if "none" in instance.options.save_expressions:
        # drop everything up till the last 'none' (users may have added more after that)
        last_none = len(
            instance.options.save_expressions
        ) - instance.options.save_expressions[::-1].index("none")
        instance.options.save_expressions = instance.options.save_expressions[
            last_none:
        ]

    if "all" in instance.options.save_expressions:
        components += list(instance.component_objects(Expression))
    else:
        components += [getattr(instance, c) for c in instance.options.save_expressions]

    missing_val_list = []
    for var in components:
        output_file = os.path.join(outdir, "%s.csv" % var.name)
        with open(output_file, "w") as fh:
            writer = csv.writer(fh, dialect="switch-csv")
            if var.is_indexed():
                index_name = var.index_set().name
                index_dimen = var.index_set().dimen
                if index_dimen is UnknownSetDimen:
                    # Need to specify dimen even if it's 1 in Pyomo 5.7+. We
                    # could potentially use
                    # pyomo.dataportal.process_data._guess_set_dimen() but it is
                    # undocumented and not needed if all the sets have dimen
                    # specified, which they do now.
                    raise ValueError(
                        f"Set {index_name} has unknown dimen; unable to infer "
                        f"number of index columns to write to {var.name}.csv."
                    )
                # Write column headings
                writer.writerow(
                    [f"{index_name}_{i+1}" for i in range(index_dimen)] + [var.name]
                )
                # Results are saved in the order of the index set by default.
                # Lexicographic sorting is available if wanted.
                items = sorted(var.items()) if sorted_output else list(var.items())
                for key, obj in items:
                    writer.writerow(tuple(make_iterable(key)) + (get_value(obj),))
            else:
                # single-valued variable
                writer.writerow([var.name])
                writer.writerow([get_value(obj)])
    if missing_val_list:
        msg = (
            "WARNING: {} {}. This "
            "usually indicates a coding error: either the variable is "
            "not needed or it has accidentally been omitted from all "
            "constraints and the objective function. These variables include "
            "{}.".format(
                len(missing_val_list),
                (
                    "variable has not been assigned a value"
                    if len(missing_val_list) == 1
                    else "variables have not been assigned values"
                ),
                missing_val_list[:10],
            )
        )
        try:
            logger = obj.model().logger.warn(msg)
            logger.warn(msg)
        except AttributeError:
            print(msg)


def get_value(obj, missing_val_list=[]):
    """
    Retrieve value of one element of a Variable or Expression, converting
    division-by-zero to nan and uninitialized values to None.
    """
    if not hasattr(obj, "expr") and getattr(obj, "value", 0) is None:
        # If variables are not used in constraints or the objective function,
        # they will never get values, and give a ValueError if accessed.
        # Accessing obj.value may be undocumented, but avoids using value(obj),
        # which emits a lot of unsuppressable text if the value is unassigned.
        # Note: for variables we could use 0 if allowed or otherwise the closest
        # bound. But using None makes it more clear that something weird
        # happened.
        val = None
        missing_val_list.append(obj.name)
    else:
        try:
            val = value(obj)
        except ZeroDivisionError:
            # diagnostic expressions sometimes have 0 denominator,
            # e.g., AverageFuelCosts for unused fuels;
            val = float("nan")
    return val


def save_total_cost_value(instance, outdir):
    with open(os.path.join(outdir, "total_cost.txt"), "w") as fh:
        fh.write("{}\n".format(value(instance.SystemCost)))


def save_cost_components(m, outdir):
    """
    Save values for all individual components of total system cost on NPV basis.
    """
    cost_dict = dict()
    for annual_cost in m.Cost_Components_Per_Period:
        cost = getattr(m, annual_cost)
        # note: storing value() instead of the expression may save
        # some memory while this function runs
        cost_dict[annual_cost] = value(
            sum(cost[p] * m.bring_annual_costs_to_base_year[p] for p in m.PERIODS)
        )
    for tp_cost in m.Cost_Components_Per_TP:
        cost = getattr(m, tp_cost)
        cost_dict[tp_cost] = value(
            sum(
                cost[t]
                * m.tp_weight_in_year[t]
                * m.bring_annual_costs_to_base_year[m.tp_period[t]]
                for t in m.TIMEPOINTS
            )
        )
    write_table(
        m,
        list(cost_dict.keys()),
        output_file=os.path.join(outdir, "cost_components.csv"),
        headings=("component", "npv_cost"),
        values=lambda m, c: (c, cost_dict[c]),
        digits=16,
    )

