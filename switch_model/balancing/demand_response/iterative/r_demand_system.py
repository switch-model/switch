"""
Bridge to demand system implemented in an R script.
"""

# Note that calibration data is stored in the R instance, and rpy2 only
# creates one instance. So this module can only be used with one model
# at a time (or at least only with models that use the same calibration data).

# An alternative approach would be to store calibration data in a particular
# environment or object in R, and return that to Python. Then that could be
# returned by the python calibrate_demand() function and attached to the model.


def define_arguments(argparser):
    argparser.add_argument(
        "--dr-r-script",
        default=None,
        help="Name of R script to use for preparing demand response bids. "
        "This script should provide calibrate() and bid() functions. ",
    )
    argparser.add_argument(
        "--dr-r-options",
        default="",
        help="String to pass to the R demand response script, usually "
        "used to identify input files or settings for this scenario, e.g., "
        """"inputs.dir <- 'inputs_special'; ces.file <- 'ces_low.csv'". """
        "Will be passed to the calibrate() function of the DR R script as is.",
    )


def define_components(m):
    # load modules for use later (import is delayed to avoid interfering with unit tests)
    try:
        global np
        import numpy as np
    except ImportError:
        print("=" * 80)
        print(
            "Unable to load numpy package, which is used by the r_demand_system module."
        )
        print("Please install this via 'conda install numpy' or 'pip install numpy'.")
        print("=" * 80)
        raise
    try:
        global rpy2  # not actually needed outside this function
        import rpy2.robjects
        import rpy2.robjects.numpy2ri
    except ImportError:
        print("=" * 80)
        print(
            "Unable to load rpy2 package, which is used by the r_demand_system module."
        )
        print("Please install this via 'conda install rpy2' or 'pip install rpy2'.")
        print("=" * 80)
        raise
    # initialize the R environment
    global r
    r = rpy2.robjects.r
    # turn on automatic numpy <-> r conversion
    rpy2.robjects.numpy2ri.activate()
    # alternatively, we could use numpy2ri(np.array(...)), but it's easier
    # to use the automatic conversions.
    # If we wanted to be more explicit about conversions, it would probably
    # be best to switch to using the rpy2.rinterface to build up the r objects
    # from a low level, e.g., rinterface.StrSexpVector(load_zones) to get a
    # string vector, other tools to get an array and add dimnames, etc.

    # load the R script specified by the user (must have calibrate() and bid() functions)
    if m.options.dr_r_script is None:
        raise RuntimeError(
            "No R script specified for use with the r_demand_system; unable to continue. "
            "Please use --dr-r-script <scriptname.R> in options.txt, scenarios.txt or on "
            "the command line."
        )
    if m.options.debug:
        # setup postmortem debugging in R
        r("options(error=browser)")
    r.source(m.options.dr_r_script)


def calibrate_demand(m, base_data):
    """
    Accept a list of tuples showing load_zone, time_series, [base hourly loads], [base
    hourly prices] for each load_zone and time_series (day). Perform any calibration
    needed in the demand system so that customized bids can later be generated for each
    load_zone and timeseries, using new prices.
    """
    # convert base_data to a format that can be passed to R
    # (string keys, vector data and no tuples)
    base_data_for_r = [
        [str(z), str(ts), np.array(base_loads), np.array(base_prices)]
        for (z, ts, base_loads, base_prices) in base_data
    ]
    # note: prior to Jan 2025, we constructed an R array with named dimensions
    # here and passed that to R, but that broke somewhere between rpy2 3.3.6
    # and rpy2 3.5.11. It would also have broken if we ever used a model with
    # mixed-length timeseries. So now we just pass the Switch calibration data
    # through with minimal adjustments.

    # prepare Switch options object to pass to R (this includes standard
    # settings such as inputs_dir and input_aliases, and also anything people
    # put in the dr_r_options flag; note that hyphens in the command line
    # flags will be translated to underscores like --inputs-dir -> inputs_dir
    null = r("NULL")
    switch_options = rpy2.robjects.ListVector(
        {k: null if v is None else v for (k, v) in vars(m.options).items()}
    )

    # calibrate the demand system within R
    r.calibrate(base_data_for_r, switch_options)


def bid_demand(m, load_zone, timeseries, prices):
    """
    Accept a vector of prices in a particular load_zone during a particular timeseries
    (usually a day). Return a tuple showing load levels for each timepoint and willingness
    to pay (avg. $/hr) for that load vector. Note that prices are in $/MWh and loads are
    in MW (MWh/h), so wtp should be in units of prices dot demand / len(demand).
    """

    bid = r.bid(
        str(load_zone),
        str(timeseries),
        m.ts_duration_of_tp[timeseries],
        np.array(prices["energy"]),
        np.array(prices["energy up"]),
        np.array(prices["energy down"]),
    )
    demand = {
        "energy": list(bid[0]),
        "energy up": list(bid[1]),
        "energy down": list(bid[2]),
    }
    # convert from numpy float64 array (everything is a vector in R)
    wtp = float(bid[3][0])

    if not demand["energy"]:
        raise ValueError("Empty bid received from R demand system.")

    return (demand, wtp)


def test_calib():
    """Test calibration routines with sample data. Results should match r.test_calib()."""
    base_data = [
        ("oahu", 100, [500, 1000, 1500], [0.35, 0.35, 0.35]),
        ("oahu", 200, [2000, 2500, 3000], [0.35, 0.35, 0.35]),
        ("maui", 100, [3500, 4000, 4500], [0.35, 0.35, 0.35]),
        ("maui", 200, [5000, 5500, 6000], [0.35, 0.35, 0.35]),
    ]
    calibrate_demand(base_data)
    r.print_calib()
