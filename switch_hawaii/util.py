import csv, sys, time, itertools
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

def create_table(**kwargs):
    """Create an empty output table and write the headings."""
    output_file = kwargs["output_file"]
    headings = kwargs["headings"]

    with open(output_file, 'wb') as f:
        w = csv.writer(f, dialect="ampl-tab")
        # write header row
        w.writerow(list(headings))

def append_table(model, *indexes, **kwargs):
    """Add rows to an output table, iterating over the indexes specified, 
    and getting row data from the values function specified."""
    output_file = kwargs["output_file"]
    values = kwargs["values"]

    # create a master indexing set 
    # this is a list of lists, even if only one list was specified
    idx = itertools.product(*indexes)
    with open(output_file, 'ab') as f:
        w = csv.writer(f, dialect="ampl-tab")
        # write the data
        # import pdb
        # if 'rfm' in output_file:
        #     pdb.set_trace()
        w.writerows(
            tuple(value(v) for v in values(model, *unpack_elements(x))) 
            for x in idx
        )

def unpack_elements(tup):
    """Unpack any multi-element objects within tup, to make a single flat tuple.
    Note: this is not recursive.
    This is used to flatten the product of a multi-dimensional index with anything else."""
    l=[]
    for t in tup:
        if isinstance(t, basestring):
            l.append(t)
        else:
            try:
                # check if it's iterable
                iterator = iter(t)
                for i in iterator:
                    l.append(i)
            except TypeError:
                l.append(t)
    return tuple(l)

def write_table(model, *indexes, **kwargs):
    """Write an output table in one shot - headers and body."""
    output_file = kwargs["output_file"]

    print "Writing {file} ...".format(file=output_file),
    sys.stdout.flush()  # display the part line to the user
    start=time.time()

    create_table(**kwargs)
    append_table(model, *indexes, **kwargs)

    print "time taken: {dur:.2f}s".format(dur=time.time()-start)

def get(component, index, default=None):
    """Return an element from an indexed component, or the default value if the index is invalid."""
    return component[index] if index in component else default
    
def log(msg):
    sys.stdout.write(msg)
    sys.stdout.flush()  # display output to the user, even a partial line
    
def tic():
    tic.start_time = time.time()

def toc():
    log("time taken: {dur:.2f}s\n".format(dur=time.time()-tic.start_time))


