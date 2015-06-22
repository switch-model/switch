import csv
import itertools
from pyomo.environ import value
import __main__ as main

# check whether this is an interactive session
# (if not, there will be no __main__.__file__)
interactive_session = not hasattr(main, '__file__')

csv.register_dialect("ampl-tab", 
    delimiter="\t", 
    lineterminator="\n",
    doublequote=False, escapechar="\\", 
    quotechar='"', quoting=csv.QUOTE_MINIMAL,
    skipinitialspace = False
)

def write_table(model, *indexes, **kwargs):
    # there must be a way to accept specific named keyword arguments and also an 
    # open-ended list of positional arguments (*indexes), but I don't know what that is.
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
        # rows=[value(v) for x in idx for v in values(model, *x)]
        # print(rows)
        w.writerows(
            tuple(value(v) for v in values(model, *x)) 
            for x in idx
        )

def test_table(model, *indexes, **kwargs):
    output_file = kwargs["output_file"]
    headings = kwargs["headings"]
    values = kwargs["values"]
    # create a master indexing set 
    # this is a list of lists, even if only one list was specified
    idx = itertools.product(*indexes)
    return (tuple(value(v) for v in values(model, *x)) for x in idx)
