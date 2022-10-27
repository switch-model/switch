from __future__ import print_function

import time, sys, collections, os, itertools
from textwrap import dedent
from switch_model import __version__ as switch_version
from switch_model.utilities import iteritems

# use database settings from operating environment
# (this code isn't really needed at all, but gives us a chance to override later)
# note: password for this user should be specified in ~/.pgpass
pghost = os.getenv("PGHOST", "")
pgdatabase = os.getenv("PGDATABASE", "")
pguser = os.getenv("PGUSER", "")

# TODO: switch over to Google BigQuery database

# TODO: make this get data from the redr server via an HTTP api instead of psycopg2, as follows:

# create a .rpy script on the redr server that can accept form data (the args dict) via POST
# and then return a .zip file containing all the files created by write_tables (most of the
# code in this module would go into that script). This can create the files as text blobs and
# then collect them into a single .zip file using the zip module
# Info on zipping multiple files together in memory: https://stackoverflow.com/a/25194850/3830997
# See here for info on .rpy files:
# https://twistedmatrix.com/documents/15.0.0/web/howto/using-twistedweb.html#web-howto-using-twistedweb-rpys
# See here for info on receiving POST requests:
# https://www.saltycrane.com/blog/2010/08/twisted-web-post-example-json/

# client side will then just send a POST request with the args dictionary (probably using the
# requests module), receive back a zip file with all the relevant CSVs (probably with a whole
# relative directory structure). Client may also need to convert line endings (or unzip may do
# it automatically).
# See here for info on sending a Python dict as the body in a
# POST request: https://stackoverflow.com/a/14804320/3830997
# https://stackoverflow.com/questions/15694120/why-does-http-post-request-body-need-to-be-json-enconded-in-python
# https://stackoverflow.com/questions/35212279/python-request-post-not-accepting-dictionary
# (the latter two are interesting edge cases but may be doing it wrong)
# Unzipping files in Python: https://stackoverflow.com/questions/3451111/unzipping-files-in-python
# some random info on converting line endings with Python zip/unzip:
# https://bytes.com/topic/python/answers/692751-module-zipfile-writestr-line-endings-issue
# https://stackoverflow.com/questions/2613800/how-to-convert-dos-windows-newline-crlf-to-unix-newline-n-in-a-bash-script

# NOTE: instead of using the python csv writer, this directly writes tables to
# file in a customized, pyomo-friendly .csv format. This uses commas between columns
# and the standard line break for the system it is run on. This does the following
# translations (only):
# - If a value contains double quotes, they get doubled.
# - If a value contains a single quote, comma, tab or space character, the value gets
#   enclosed in double quotes.
#   (Note that pyomo doesn't allow quoting (and therefore spaces) in column headers
#   (and maybe not even in values) in tab files; we haven't tested
#   whether it's possible with .csv files.)
# - null values are converted to . (the pyomo/ampl standard for missing data)
# - any other values are simply passed to str().

# NOTE: this does not use the python csv writer because it doesn't support the quoting
# or null behaviors described above.

# NOTE: ANSI SQL specifies single quotes for literal strings, and postgres conforms
# to this, so all the queries below should use single quotes around strings.

# NOTE: write_table() will automatically convert null values to '.',
# so pyomo will recognize them as missing data


def write_tables(*pos_args, **kw_args):
    if pos_args or "args" in kw_args:
        # pass arguments through
        return write_tables_implementation(*pos_args, **kw_args)
    else:
        # called with **args (obsolete)
        print(
            "WARNING: write_tables should now be called with a dict of "
            "arguments, not key-value pairs."
        )
        # gather the arguments back into a dictionary and call correctly
        return write_tables_implementation(kw_args)


def write_tables_implementation(args, alt_args={}, scenarios=[]):
    """
    Save base tables, alternative tables and scenarios.txt

    Settings in `args` (dict) are used to define the base tables.

    Settings in `alt_args` (list of dicts) are used to define alternative
    tables. Each dict in `alt_args` is used to update `args`. Then, any queries
    that are altered by this adjustment are re-run, and the resulting csv files
    are saved with modified names. The names are modified by adding the `tag`
    specified in the alt_args dict before the  .csv extension, e.g.,
    fuels_low_cost.csv instead of fuels.csv.

    Finally, scenarios.txt is written, based on the `scenarios` list. Each item
    in `scenarios` should be a tuple of command line arguments (as a string) and
    a list or tuple of tags to apply to this scenario. The tags must match tags
    specified in `alt_args`. For each scenario in `scenarios`, a line is written
    in scenarios.txt, consisting of the command line string followed by
    '--input-alias[es]' and the file substitutions corresponding to the
    specified data tags. A warning is issued if two tags cause conflicting file
    substitutions.
    """
    # Note: this works by comparing the final queries used to generate each
    # table, so it will reuse tables from the base model if they are identical
    # to an alternative scenario. This may be confusing, but it is simple and
    # effective and avoids problems that would crop up if we tried to identify
    # which tables are affected by each argument by analyzing the placeholders
    # in the query. That method would fail to catch situations where the
    # get_query() code uses arguments directly, either to inject values into the
    # query or to control which tables are defined or add or remove clauses from
    # the query.

    # The code below could be streamlined a little by retrieving the query list
    # from write_base_tables and then passing it to write_alternative_tables,
    # but it works pretty well as is.

    # write version marker file
    with open(make_file_path("switch_inputs_version.txt", args), "w") as f:
        f.write(switch_version)

    # write base tables
    write_base_tables(args)

    # write alternative tables
    data_aliases = {}
    for a in alt_args:
        data_aliases[a["tag"]] = write_alternative_tables(args, a)

    # write scenarios.txt
    scenario_args = []
    for cmds, data_tags in scenarios:
        active_aliases = []
        for t in data_tags:
            for orig, alias in data_aliases.get(t, []):
                if any(a[0] == orig for a in active_aliases):
                    print(
                        "WARNING: multiple aliases specified for {} in scenario {}.".format(
                            orig, scenario_args.split(" ")[1]
                        )
                    )
                active_aliases.append((orig, alias))

        if active_aliases:
            cmds += (
                " --input-alias " if len(active_aliases) == 1 else " --input-aliases "
            )
            cmds += " ".join("=".join(pair) for pair in active_aliases)
        scenario_args.append(cmds)

    if scenarios:
        with open("scenarios.txt", "w") as f:
            f.writelines(s + "\n" for s in scenario_args)


def write_base_tables(args):
    queries = get_queries(args)
    for table, query in queries:
        write_table(make_file_path(table, args), query)


def write_alternative_tables(base_args, alt_args):
    # add alt_args to base_args, then check for queries that are
    # added, modified or dropped
    base_queries = dict(get_queries(base_args))
    full_alt_args = dict(itertools.chain(base_args.items(), alt_args.items()))
    alt_queries = dict(get_queries(full_alt_args))
    # get location for files created by alt_args, relative to files created by base_args
    alt_relative_path = os.path.relpath(
        make_file_path(".", full_alt_args), start=make_file_path(".", base_args)
    )
    # find differences and run alt queries
    aliases = []
    for table, query in alt_queries.items():
        if table not in base_queries or query != base_queries[table]:
            # new or altered table
            # specify name and location relative to base_args inputs directory
            if alt_relative_path == ".":
                # file going in same directory as base file; give it a new name
                table_base, table_ext = os.path.splitext(table)
                new_table = table_base + "." + full_alt_args["tag"] + table_ext
            else:
                new_table = os.path.join(alt_relative_path, table)
            write_table(make_file_path(new_table, base_args), query)
            # note: if regular files are in inputs and alternative files are in
            # inputs_alt, then this will set file.csv=../inputs_alt/file.csv,
            # and then --input-alias will just do a simple translation of
            # file.csv, resulting in inputs/../inputs_alt/file.csv
            aliases.append((table, new_table))
    # exclude tables that are omitted in the alternative case
    aliases.extend((t, "none") for t, q in base_queries.items() if t not in alt_queries)
    return aliases


def get_queries(args):
    """
    Return a list of queries based on `args`.

    Each entry in the list is a tuple of (table name, sql query code).
    """

    # print(
    #     "WARNING: need a more general way to identify non-fuel energy sources "
    #     "in scenario_data. See references to MSW, WND, etc."
    # )

    queries = []

    # TODO: any arguments that are defined with default values below (args.get()) could
    # have those default values assigned here. Then they can be used directly in queries
    # instead of using them to create snippets that are used in the queries. This would
    # also document the available arguments a little better.

    args = args.copy()

    # catch obsolete arguments (otherwise they would be silently ignored)
    updated_args = [
        ("fuel_scen_id", "fuel_scenario"),
        ("cap_cost_scen_id", "tech_scenario"),
        ("tech_scen_id", "tech_scenario"),
        ("load_scen_id", "load_scenario"),
        ("ev_scen_id", "ev_scenario"),
    ]
    for old, new in updated_args:
        if old in args:
            if new in args:
                raise ValueError(
                    "{} and {} arguments are redundant and ambiguous.".format(old, new)
                )
            else:
                print(
                    'DEPRECATION WARNING: The "{}" argument has been '
                    'renamed to "{}". Please update your code.'.format(old, new)
                )
            args[new] = args.pop(old)

    if "ev_charge_profile" not in args:
        print("No ev_charge_profile specified; using das_2015")
        args["ev_charge_profile"] = "das_2015"

    if "enable_must_run" in args and "enable_must_run_before" in args:
        raise ValueError(
            "You may specify enable_must_run or enable_must_run_before, but not both."
        )
    elif "enable_must_run" in args:
        args["enable_must_run_before"] = 999999 if args["enable_must_run"] else 0
    else:
        args["enable_must_run_before"] = args.get("enable_must_run_before", 0)

    # fill in default arguments (use a dummy entry '-' if none supplied)
    args["exclude_technologies"] = args.get("exclude_technologies", ("-",))
    args["exclude_land_classes"] = args.get("exclude_land_classes", ("-",))
    args["exclude_slope_classes"] = args.get("exclude_slope_classes", ("-",))
    for a in ["exclude_technologies", "exclude_land_classes", "exclude_slope_classes"]:
        if not isinstance(args[a], tuple):
            raise ValueError(f"Argument {a} must be a tuple or omitted.")

    #########################
    # timescales

    # reusable clause to calculate the length of each period
    # If this is within 1% of an integer number of years, it rounds to the integer,
    # to allow for weights that add up to 365 or 365.25 days per year
    period_length = """
        period_length_raw AS (
            SELECT
                period,
                -- make a decent guess about number of years
                SUM(ts_scale_to_period)/365.25 AS period_length
                FROM timeseries WHERE time_sample = %(time_sample)s
                GROUP BY 1
        ),
        period_length AS (
            SELECT
                period,
                CASE WHEN
                    period_length > 0.9 AND
                    period_length - ROUND(period_length) BETWEEN -0.01 and 0.01
                    THEN ROUND(period_length) ELSE period_length
                END as period_length
                FROM period_length_raw
        )
    """

    # note: in contrast to earlier versions, this makes period_end
    # point to the exact moment when the period finishes
    # (switch_model.timescales can handle that now),
    # and it lets period_end be a floating point number
    # (postgresql will export it with a .0 in this case)
    # note: despite the comments above, this rounded period_end to
    # the nearest whole number until 2018-02-17. This was removed to
    # support fractional years for monthly batches in production-cost models.

    add_query(
        queries,
        "periods.csv",
        "WITH "
        + period_length
        + """
        SELECT p.period AS "INVESTMENT_PERIOD",
                p.period as period_start,
                p.period + period_length as period_end
            FROM periods p JOIN period_length l USING (period)
            WHERE time_sample = %(time_sample)s
            ORDER by 1;
    """,
        args,
    )

    add_query(
        queries,
        "timeseries.csv",
        """
        SELECT timeseries as "TIMESERIES", period as ts_period,
            ts_duration_of_tp, ts_num_tps, ts_scale_to_period
        FROM timeseries
        WHERE time_sample = %(time_sample)s
        ORDER BY 1;
    """,
        args,
    )

    # note: query below needs dash instead of space in date format if creating
    # .tab files, but this works well for .csv files (8/2019 and later)
    add_query(
        queries,
        "timepoints.csv",
        """
        SELECT h.timepoint as timepoint_id,
                to_char(date_time + (period - extract(year from date_time)) * interval '1 year',
                    'YYYY-MM-DD HH24:MI') as timestamp,
                h.timeseries
            FROM timepoints h JOIN timeseries d USING (timeseries, time_sample)
            WHERE h.time_sample = %(time_sample)s
            ORDER BY period, extract(doy from date), timepoint;
    """,
        args,
    )

    #########################
    # clauses that identify available projects and technologies
    study_info = (
        period_length
        + ","
        + """
        study_length AS (
            SELECT min(period)::real as study_start, max(period+period_length)::real AS study_end
            FROM period_length
        ),
        study_projects AS (
            SELECT DISTINCT
                CONCAT_WS('_', load_zone, p.technology, nullif(site, 'na'), nullif(orientation, 'na'))
                    AS "GENERATION_PROJECT",
                p.*,
                g.tech_scenario
            FROM projects p
                JOIN generator_info g USING (technology)
                CROSS JOIN study_length
                -- existing projects still in use during the study
                LEFT JOIN gen_build_predetermined e ON (
                    e.project_id = p.project_id
                    AND e.build_year + g.gen_max_age > study_start
                    AND e.build_year < study_end
                )
                -- projects that could be built during the study
                LEFT JOIN gen_build_costs c ON (
                    c.tech_scenario = g.tech_scenario
                    AND c.technology = g.technology
                    AND (g.min_vintage_year IS NULL OR c.year >= g.min_vintage_year)
                    AND c.year >= study_start
                    AND c.year < study_end
                )
            WHERE (e.project_id IS NOT NULL OR c.technology IS NOT NULL)
                AND p.load_zone in %(load_zones)s
                AND p.technology NOT IN %(exclude_technologies)s
                -- exclude some land_class and slope_class values, but allow nulls through
                AND (p.land_class IS NULL OR p.land_class NOT IN %(exclude_land_classes)s)
                AND (p.slope_class IS NULL OR p.slope_class NOT IN %(exclude_slope_classes)s)
                AND g.tech_scenario IN ('all', %(tech_scenario)s)
        ),
        study_generator_info AS (
            SELECT DISTINCT g.*
            FROM generator_info g JOIN study_projects p USING (tech_scenario, technology)
        )"""
    )

    #########################
    # financials
    # (values are not in a database for now)
    add_one_row_literal(
        queries,
        "financials.csv",
        ["base_financial_year", "interest_rate", "discount_rate"],
        args,
    )

    #########################
    # load_zones

    # note: we don't provide the following fields in this version:
    # zone_cost_multipliers, zone_ccs_distance_km, zone_dbid,
    # existing_local_td, local_td_annual_cost_per_mw
    add_query(
        queries,
        "load_zones.csv",
        """
        SELECT load_zone as "LOAD_ZONE"
        FROM load_zones
        WHERE load_zone in %(load_zones)s
        ORDER BY 1;
    """,
        args,
    )

    # NOTE: we don't provide zone_peak_loads.csv (sometimes used by local_td.py) in this version.

    # get system loads, scaled from the historical years to the model years
    # note: 'offset' is a keyword in postgresql, so we use double-quotes to specify the column name
    add_query(
        queries,
        "loads.csv",
        """
        SELECT
            l.load_zone AS "LOAD_ZONE",
            timepoint AS "TIMEPOINT",
            GREATEST(0, system_load * scale + "offset") AS zone_demand_mw
        FROM timeseries d
            JOIN timepoints h USING (time_sample, timeseries)
            JOIN loads l USING (date_time)
            JOIN load_scale s ON (
                s.load_zone = l.load_zone
                AND s.year_hist = extract(year from l.date_time)
                AND s.year_fore = d.period)
        WHERE l.load_zone in %(load_zones)s
            AND d.time_sample = %(time_sample)s
            AND load_scenario = %(load_scenario)s
        ORDER BY 1, 2;
    """,
        args,
    )

    #########################
    # fuels

    add_query(
        queries,
        "non_fuel_energy_sources.csv",
        "WITH "
        + study_info
        + """
        SELECT DISTINCT gen_energy_source AS "NON_FUEL_ENERGY_SOURCES"
            FROM study_generator_info
            WHERE gen_energy_source NOT IN (SELECT fuel FROM fuel_costs)
            ORDER by 1;
    """,
        args,
    )

    # gather info on fuels
    add_query(
        queries,
        "fuels.csv",
        """
        SELECT DISTINCT
            replace(c.fuel, ' ', '_') AS fuel,
            co2_intensity, 0.0 AS upstream_co2_intensity,
            rps_eligible
        FROM fuel_costs c
            JOIN energy_sources p on (p.energy_source = c.fuel)
        WHERE load_zone in %(load_zones)s
            AND fuel_scenario=%(fuel_scenario)s
        ORDER BY 1;
    """,
        args,
    )

    #########################
    # rps targets

    add_literal_table(
        queries,
        "rps_targets.csv",
        headers=("year", "rps_target"),
        data=[(y, args["rps_targets"][y]) for y in sorted(args["rps_targets"].keys())],
        arguments=args,
    )

    #########################
    # fuel_markets

    # deflate HECO fuel scenarios to base year, and inflate EIA-based scenarios
    # from 2013 (forecast base year) to model base year. (ugh)
    # TODO: add a flag to fuel_costs indicating whether forecasts are real or nominal,
    # and base year, and possibly inflation rate.
    if args["fuel_scenario"] in ("1", "2", "3"):
        raise ValueError(
            "fuel_scenarios '1', '2' and '3' (specified in nominal dollars) are "
            "no longer supported."
        )

    per_timepoint_fuel_costs = args.get("use_per_timepoint_fuel_costs", False)
    simple_fuel_costs = args.get("use_simple_fuel_costs", False)

    if per_timepoint_fuel_costs and not simple_fuel_costs:
        raise NotImplementedError(
            "The use_per_timepoint_fuel_costs flag currently can only be used "
            "with the use_simple_fuel_costs option."
        )

    if simple_fuel_costs:
        # simple fuel markets with no bulk LNG expansion option (use fuel_cost module)
        if "use_bulk_lng_for_simple_fuel_costs" in args:
            raise ValueError(
                "use_bulk_lng_for_simple_fuel_costs argument is no longer supported; "
                "use simple_fuel_costs_lng_tier instead (or omit to prevent use of LNG)."
            )
        if args.get("simple_fuel_costs_lng_tier", None):
            # note: this will let the model use this tier, but it will not force it to
            # pay the full fixed cost for all _available_ LNG, so results will be wrong
            # if fixed_cost > 0
            lng_selector = "tier = %(simple_fuel_costs_lng_tier)s"
        else:
            lng_selector = "false"

        if per_timepoint_fuel_costs:
            # month column in fuel_cost table can optionally be filled in;
            # when getting per-timepoint costs, we link this month to
            # timeseries.month_of_year and average across all the years in each
            # period.
            add_query(
                queries,
                "fuel_cost_per_timepoint.csv",
                "WITH "
                + period_length
                + """
                SELECT load_zone, replace(fuel, ' ', '_') as fuel, h.timepoint,
                    avg(price_mmbtu
                        * power(1.0+%(inflation_rate)s, %(base_financial_year)s-c.base_year)
                        + COALESCE(fixed_cost, 0.00)
                    ) as timepoint_fuel_cost
                FROM fuel_costs c
                    CROSS JOIN timepoints h
                    JOIN timeseries d USING (timeseries, time_sample)
                    JOIN periods p USING (period, time_sample)
                    JOIN period_length l USING (period)
                WHERE load_zone in %(load_zones)s
                    AND fuel_scenario = %(fuel_scenario)s
                    AND p.time_sample = %(time_sample)s
                    AND c.month = d.month_of_year
                    AND (fuel != 'LNG' OR {lng_selector})
                    AND c.year >= p.period AND c.year < p.period + l.period_length
                GROUP BY 1, 2, 3
                ORDER BY 1, 2, 3;
                """.format(
                    lng_selector=lng_selector
                ),
                args,
            )
        else:
            # Note: if monthly prices have been specified for this fuel_scenario
            # in the fuel_cost table, they get averaged together with equal
            # weight as part of the general averaging across all the years of
            # the period (which is good).
            add_query(
                queries,
                "fuel_cost.csv",
                "WITH "
                + period_length
                + """
                SELECT load_zone, replace(fuel, ' ', '_') as fuel, p.period,
                    avg(
                        price_mmbtu
                        * power(1.0+%(inflation_rate)s, %(base_financial_year)s-c.base_year)
                        + COALESCE(fixed_cost, 0.00)
                    ) as fuel_cost
                FROM fuel_costs c, periods p JOIN period_length l USING (period)
                WHERE load_zone in %(load_zones)s
                    AND fuel_scenario = %(fuel_scenario)s
                    AND p.time_sample = %(time_sample)s
                    AND (fuel != 'LNG' OR {lng_selector})
                    AND c.year >= p.period AND c.year < p.period + l.period_length
                GROUP BY 1, 2, 3
                ORDER BY 1, 2, 3;
            """.format(
                    lng_selector=lng_selector
                ),
                args,
            )
    else:  # not simple_fuel_costs
        # advanced fuel markets with LNG expansion options (used by forward-looking models)
        # (use fuel_markets module)
        add_query(
            queries,
            "regional_fuel_markets.csv",
            """
            SELECT DISTINCT
                concat('Hawaii_', replace(fuel, ' ', '_')) AS regional_fuel_market,
                replace(fuel, ' ', '_') AS fuel
            FROM fuel_costs
            WHERE load_zone in %(load_zones)s AND fuel_scenario = %(fuel_scenario)s
            ORDER BY 1, 2;
        """,
            args,
        )

        add_query(
            queries,
            "fuel_supply_curves.csv",
            "WITH "
            + period_length
            + """
            SELECT concat('Hawaii_', replace(fuel, ' ', '_')) as regional_fuel_market,
                replace(fuel, ' ', '_') as fuel,
                tier,
                p.period,
                avg(price_mmbtu * power(1.0+%(inflation_rate)s, %(base_financial_year)s-c.base_year)) as unit_cost,
                avg(max_avail_at_cost) as max_avail_at_cost,
                avg(fixed_cost) as fixed_cost,
                avg(max_age) as max_age
            FROM fuel_costs c, periods p JOIN period_length l USING (period)
            WHERE load_zone in %(load_zones)s
                AND fuel_scenario = %(fuel_scenario)s
                AND p.time_sample = %(time_sample)s
                AND (c.year >= p.period AND c.year < p.period + l.period_length)
            GROUP BY 1, 2, 3, 4
            ORDER BY 1, 2, 3, 4;
        """,
            args,
        )

        add_query(
            queries,
            "zone_to_regional_fuel_market.csv",
            """
            SELECT DISTINCT load_zone, concat('Hawaii_', replace(fuel, ' ', '_')) AS regional_fuel_market
            FROM fuel_costs
            WHERE load_zone in %(load_zones)s AND fuel_scenario = %(fuel_scenario)s
            ORDER BY 1, 2;
        """,
            args,
        )

    # TODO: (when multi-island) add fuel_cost_adders for each zone

    #########################
    # investment.gen_build and part of operation.unitcommit.commit

    # NOTE: this converts variable o&m from $/kWh to $/MWh
    # and heat rate from Btu/kWh to MBtu/MWh

    # NOTE: for all energy sources other than 'SUN' and 'WND' (i.e., all fuels),
    # we report the fuel as 'multiple' and then provide data in a multi-fuel table.
    # Some of these are actually single-fuel, but this approach is simpler than sorting
    # them out within each query, and it doesn't add any complexity to the model.

    if args.get("wind_capital_cost_escalator", 0.0) or args.get(
        "pv_capital_cost_escalator", 0.0
    ):
        # user supplied a non-zero escalator
        raise ValueError(
            "wind_capital_cost_escalator and pv_capital_cost_escalator arguments are "
            "no longer supported by scenario_data.write_tables(); "
            "assign time-varying costs in the gen_build_costs table instead."
        )
    if args.get("generator_costs_base_year", 0):
        # user supplied a generator_costs_base_year
        raise ValueError(
            "generator_costs_base_year is no longer supported by scenario_data.write_tables(); "
            "assign base_year in the gen_build_costs table instead."
        )

    # TODO: make sure the heat rates are null for non-fuel projects in the upstream database,
    # and remove the correction code from here

    # TODO: maybe replace "fuel IN ('SUN', 'WND', 'MSW')" with "fuel not in (SELECT fuel FROM fuel_cost)"
    # TODO: convert 'MSW' to a proper fuel, possibly with a negative cost, instead of ignoring it

    # Omit full load heat rates if we are providing heat rate curves instead
    if args.get("use_incremental_heat_rates", False):
        full_load_heat_rate = "null"
    else:
        full_load_heat_rate = "0.001*gen_full_load_heat_rate"

    if args.get("report_forced_outage_rates", False):
        forced_outage_rate = "gen_forced_outage_rate"
    else:
        forced_outage_rate = "0"

    # if needed, follow the query below with another one that specifies
    # COALESCE(gen_connect_cost_per_mw, 0.0) AS gen_connect_cost_per_mw
    add_query(
        queries,
        "gen_info.csv",
        "WITH "
        + study_info
        + """
        SELECT
            "GENERATION_PROJECT",
            load_zone AS gen_load_zone,
            technology AS gen_tech,
            (spur_line_cost_per_mw + 1000.0 * substation_cost_per_kw)
                * power(1.0+%(inflation_rate)s, %(base_financial_year)s-base_year)
                AS gen_connect_cost_per_mw,
            gen_capacity_limit_mw,
            gen_unit_size,
            gen_min_build_capacity,
            gen_max_age,
            gen_scheduled_outage_rate,
            {fo} as gen_forced_outage_rate,
            gen_is_variable,
            gen_is_baseload,
            -- 0 as gen_is_flexible_baseload,
            gen_is_cogen,
            -- non_cycling as gen_non_cycling,
            (1000.0 * variable_o_m)
                * power(1.0+%(inflation_rate)s, %(base_financial_year)s-base_year)
                AS gen_variable_om,
            CASE
                WHEN gen_energy_source IN ('SUN', 'WND', 'MSW', 'Battery', 'Hydro')
                THEN gen_energy_source
                ELSE 'multiple'
            END AS gen_energy_source,
            CASE
                WHEN gen_energy_source IN ('SUN', 'WND', 'MSW', 'Battery', 'Hydro')
                THEN null
                ELSE {flhr}
            END AS gen_full_load_heat_rate,
            gen_min_uptime,
            gen_min_downtime,
            gen_startup_fuel,
            gen_storage_efficiency,
            gen_storage_energy_to_power_ratio,
            gen_storage_max_cycles_per_year,
            land_class as gen_land_class,
            land_area as gen_land_area,
            slope_class as gen_slope_class
        FROM study_projects JOIN study_generator_info USING (technology)
        ORDER BY 2, 3, 1;
    """.format(
            fo=forced_outage_rate, flhr=full_load_heat_rate
        ),
        args,
    )

    add_query(
        queries,
        "gen_build_predetermined.csv",
        "WITH "
        + study_info
        + """
        SELECT
            "GENERATION_PROJECT",
            build_year,
            SUM(gen_predetermined_cap) as build_gen_predetermined,
            SUM(gen_predetermined_storage_energy_mwh) as build_gen_energy_predetermined
        FROM study_projects JOIN gen_build_predetermined USING (project_id)
        GROUP BY 1, 2
        ORDER BY 1, 2;
    """,
        args,
    )

    def adjust_cost(cost_term, cost_adjustment_table=None):
        """
        Generate cost expression including the following adjustments:
        - multiply by 1000.0 to convert from cost per kW or kWh to cost per MW or MWh
        - adjust for inflation between project base year and study base year
        - optionally apply project-specific cost adjustment terms

        Assumes base_year exists in the table referenced by cost_term.
        Applies cost_multiplier and cost_offset terms from cost_adjustment_table if
        specified.
        """
        cost_table = cost_term.split(".")[0] + "." if "." in cost_term else ""

        if cost_adjustment_table:
            cat = cost_adjustment_table
            cost_term = f"({cost_term}*{cat}.cost_multiplier + {cat}.cost_offset)"

        return (
            f"("
            f"{cost_term}"
            f" * 1000.0"
            f" * power(1.0+%(inflation_rate)s, %(base_financial_year)s-{cost_table}base_year)"
            f")"
        )

    add_query(
        queries,
        "gen_build_costs.csv",
        "WITH "
        + study_info
        + """
        -- For projects in gen_build_predetermined, apply average cost of all
        -- projects built in the same year (looking up generic costs if needed)
        SELECT
            "GENERATION_PROJECT",
            b.build_year,
            SUM(
                COALESCE({b_capital_cost_per_mw}, {c_capital_cost_per_mw})
                * gen_predetermined_cap
            ) / SUM(gen_predetermined_cap)
                AS gen_overnight_cost,
            SUM(
                COALESCE({b_capital_cost_per_mwh}, {c_capital_cost_per_mwh})
                * gen_predetermined_storage_energy_mwh
            ) / SUM(gen_predetermined_storage_energy_mwh)
                AS gen_storage_energy_overnight_cost,
            SUM(
                COALESCE({b_fixed_o_m}, {c_fixed_o_m})
                * gen_predetermined_cap
            ) / SUM(gen_predetermined_cap)
                AS gen_fixed_om
        FROM gen_build_predetermined b
            JOIN study_projects p USING (project_id)
            JOIN study_generator_info i USING (technology)
            LEFT JOIN gen_build_costs c
                ON c.technology=i.technology AND c.year=b.build_year AND c.tech_scenario=i.tech_scenario
        GROUP BY 1, 2
        UNION
        -- For each project in each period after the min vintage year, if no
        -- predetermined build is specified (above), use generic prices if
        -- available. If no prices are found, it means the project can't
        -- be expanded.
        SELECT
            "GENERATION_PROJECT",
            c.year AS build_year,
            {c_capital_cost_per_mw} AS gen_overnight_cost,
            {c_capital_cost_per_mwh} AS gen_storage_energy_overnight_cost,
            {c_fixed_o_m} AS gen_fixed_o_m
        FROM study_projects p
            JOIN study_generator_info i USING (technology)
            JOIN gen_build_costs c ON c.technology=i.technology AND c.tech_scenario=i.tech_scenario
            JOIN periods per ON (per.time_sample = %(time_sample)s AND c.year = per.period)
            LEFT JOIN gen_build_predetermined e
                ON e.project_id = p.project_id AND e.build_year = c.year
        WHERE
            e.project_id IS NULL -- no existing projects
            AND (i.min_vintage_year IS NULL OR c.year >= i.min_vintage_year)
        ORDER BY 1, 2;
    """.format(
            b_capital_cost_per_mw=adjust_cost("b.capital_cost_per_kw"),
            b_capital_cost_per_mwh=adjust_cost("b.capital_cost_per_kwh"),
            c_capital_cost_per_mw=adjust_cost(
                "c.capital_cost_per_kw", cost_adjustment_table="p"
            ),
            c_capital_cost_per_mwh=adjust_cost("c.capital_cost_per_kwh"),
            b_fixed_o_m=adjust_cost("b.fixed_o_m"),
            c_fixed_o_m=adjust_cost("c.fixed_o_m"),
        ),
        args,
    )

    #########################
    # spinning_reserves_advanced (if wanted; otherwise defaults to just "spinning"
    if "max_reserve_capability" in args or args.get(
        "write_generation_projects_reserve_capability", False
    ):
        # args['max_reserve_capability'] is a list of tuples of (technology,
        # reserve_type) (assumed equivalent to 'regulation' if not specified)
        # We unzip it to use with the unnest function (psycopg2 passes lists of
        # tuples as arrays of tuples, and unnest would keep those as tuples)
        try:
            reserve_technologies = [r[0] for r in args["max_reserve_capability"]]
            reserve_types = [r[1] for r in args["max_reserve_capability"]]
        except KeyError:
            reserve_technologies = []
            reserve_types = []
        res_args = args.copy()
        res_args["reserve_technologies"] = reserve_technologies
        res_args["reserve_types"] = reserve_types

        # note: casting is needed if the lists are empty; see https://stackoverflow.com/a/41893576/3830997
        add_query(
            queries,
            "generation_projects_reserve_capability.csv",
            "WITH "
            + study_info
            + ", "
            + """
            reserve_capability (technology, reserve_type) as (
                SELECT
                    UNNEST(%(reserve_technologies)s::varchar(40)[]) AS technology,
                    UNNEST(%(reserve_types)s::varchar(20)[]) AS reserve_type
            ),
            reserve_types (rank, reserve_type) as (
                VALUES
                (0, 'none'),
                (1, 'contingency'),
                (2, 'regulation')
            )
            SELECT
                p."GENERATION_PROJECT",
                t2.reserve_type AS "SPINNING_RESERVE_TYPE"
            FROM
                study_projects p
                LEFT JOIN reserve_capability c USING (technology)
                LEFT JOIN reserve_types t1 USING (reserve_type)
                JOIN reserve_types t2 on t2.rank <= COALESCE(t1.rank, 100)
            WHERE t2.rank > 0
            ORDER BY 1, t2.rank;
        """,
            res_args,
        )

    #########################
    # operation.unitcommit.fuel_use

    # get part load heat rate curves if requested
    # note: we sort lexicographically by power output and fuel consumption, in case
    # there are segments where power or fuel consumption steps up while the other stays constant
    # That is nonconvex and not currently supported by Switch, but could potentially be used
    # in the future by assigning binary variables for activating each segment.
    # note: for sqlite, you could use "CONCAT(technology, ' ', output_mw, ' ', fuel_consumption_mmbtu_per_h) AS key"
    # TODO: rename fuel_consumption_mmbtu_per_h to fuel_use_mmbtu_per_h here and in import_data.py

    if args.get("use_incremental_heat_rates", False):
        add_query(
            queries,
            "gen_inc_heat_rates.csv",
            "WITH "
            + study_info
            + ", "
            + """
            part_load AS (
                SELECT
                    row_number() OVER (ORDER BY technology, output_mw, fuel_consumption_mmbtu_per_h) AS key,
                    technology,
                    output_mw,
                    fuel_consumption_mmbtu_per_h
                FROM gen_part_load_fuel JOIN study_generator_info USING (technology)
            ), prior AS (
                SELECT a.key, MAX(b.key) AS prior_key
                FROM part_load a JOIN part_load b ON b.technology=a.technology AND b.key < a.key
                GROUP BY 1
            ), curves AS (
                SELECT -- first step in each curve
                    key, technology,
                    output_mw AS power_start_mw,
                    NULL::real AS power_end_mw,
                    NULL::real AS incremental_heat_rate_mbtu_per_mwhr,
                    fuel_consumption_mmbtu_per_h AS fuel_use_rate_mmbtu_per_h
                FROM part_load LEFT JOIN prior USING (key) WHERE prior_key IS NULL
                UNION
                SELECT -- additional steps
                    high.key AS key, high.technology,
                    low.output_mw AS power_start_mw,
                    high.output_mw AS power_end_mw,
                    (high.fuel_consumption_mmbtu_per_h - low.fuel_consumption_mmbtu_per_h)
                        / (high.output_mw - low.output_mw) AS incremental_heat_rate_mbtu_per_mwhr,
                    NULL::real AS fuel_use_rate_mmbtu_per_h
                FROM part_load high JOIN prior USING (key) JOIN part_load low ON (low.key = prior.prior_key)
                ORDER BY 1
            )
            SELECT
                "GENERATION_PROJECT",
                power_start_mw, power_end_mw,
                incremental_heat_rate_mbtu_per_mwhr, fuel_use_rate_mmbtu_per_h
            FROM curves c JOIN study_projects p using (technology)
            ORDER BY c.technology, c.key, p."GENERATION_PROJECT";
        """,
            args,
        )

    # This gets a list of all the fueled projects (listed as "multiple" energy sources above),
    # and lists them as accepting any equivalent or lighter fuel. (However, plants
    # using fuels with rank 0 are not changed.) Fuels are also filtered against the list of fuels with
    # costs reported for the current scenario, so this can end up re-mapping one fuel in the database
    # (e.g., LSFO) to a similar fuel in the scenario (e.g., LSFO-Diesel-Blend), even if the original fuel
    # doesn't exist in the fuel_costs table. This can also be used to remap different names for the same
    # fuel (e.g., "COL" in the plant definition and "Coal" in the fuel_costs table, both with the same
    # fuel_rank).
    add_query(
        queries,
        "gen_multiple_fuels.csv",
        "WITH "
        + study_info
        + ", "
        + """
        all_techs AS (
            SELECT
                technology,
                gen_energy_source as orig_fuel
            FROM study_generator_info
        ), all_fueled_techs AS (
            SELECT * from all_techs WHERE orig_fuel NOT IN ('SUN', 'WND', 'MSW', 'Battery', 'Hydro')
        ), gen_multiple_fuels AS (
            SELECT DISTINCT technology, b.energy_source as fuel
            FROM all_fueled_techs t
                JOIN energy_sources a ON a.energy_source = t.orig_fuel
                JOIN energy_sources b ON b.fuel_rank >= a.fuel_rank AND
                    (a.fuel_rank > 0 OR a.energy_source = b.energy_source)    -- 0-rank can't change fuels
                    AND (b.rps_eligible >= a.rps_eligible)   -- if rps-eligible fuel specified, only use rps-eligible fuels
                WHERE b.energy_source IN (SELECT fuel FROM fuel_costs WHERE fuel_scenario = %(fuel_scenario)s)
        )
        SELECT "GENERATION_PROJECT", fuel
            FROM gen_multiple_fuels g JOIN study_projects p USING (technology)
            ORDER BY p.technology, p."GENERATION_PROJECT", g.fuel
    """,
        args,
    )

    #########################
    # operation.gen_dispatch

    # skip this step if the user specifies "skip_cf" in the arguments (to speed up execution)
    if args.get("skip_cf", False):
        print("SKIPPING variable_capacity_factors.csv")
    else:
        add_query(
            queries,
            "variable_capacity_factors.csv",
            "WITH "
            + study_info
            + """
            SELECT
                "GENERATION_PROJECT",
                timepoint,
                cap_factor as gen_max_capacity_factor
            FROM study_generator_info g
                JOIN study_projects p USING (technology)
                JOIN variable_capacity_factors c USING (project_id)
                JOIN timepoints h using (date_time)
            WHERE time_sample = %(time_sample)s
            ORDER BY 1, 2
        """,
            args,
        )

    #########################
    # project.discrete_build

    # include this module, but it doesn't need any additional data.

    #########################
    # operation.unitcommit.commit

    # minimum commitment levels for existing projects

    # TODO: set gen_max_commit_fraction based on maintenance outage schedules
    # (needed for comparing switch marginal costs to FERC 715 data in 2007-08)

    # TODO: create data files showing reserve rules

    add_query(
        queries,
        "gen_timepoint_commit_bounds.csv",
        "WITH "
        + study_info
        + """
        SELECT * FROM (
            SELECT "GENERATION_PROJECT",
                timepoint AS "TIMEPOINT",
                CASE WHEN period < %(enable_must_run_before)s AND must_run = 1 THEN 1.0 ELSE null END
                    AS gen_min_commit_fraction,
                null AS gen_max_commit_fraction,
                null AS gen_min_load_fraction_TP
            FROM study_projects JOIN study_generator_info USING (technology)
                CROSS JOIN timepoints NATURAL JOIN timeseries NATURAL JOIN periods
            WHERE time_sample = %(time_sample)s
        ) AS the_data
        WHERE gen_min_commit_fraction IS NOT NULL
            OR gen_max_commit_fraction IS NOT NULL
            OR gen_min_load_fraction_TP IS NOT NULL
        ORDER BY 1, 2;
    """,
        args,
    )

    #########################
    # project.unitcommit.discrete

    # include this module, but it doesn't need any additional data.

    #########################
    # trans_build
    # --- Not used ---

    #
    # add_query(queries, 'trans_lines.csv', """
    #     SELECT load_area_start AS load_zone_start, load_area_end AS load_zone_end,
    #         tid, length_km AS transmission_length_km, efficiency AS transmission_efficiency,
    #         existing_mw_from AS existing_transmission_from,
    #         existing_mw_to AS existing_transmission_to
    #     FROM trans_line
    #     WHERE load_area_start IN %(load_zones)s OR load_area_end IN %(load_zones)s
    #     ORDER BY 1, 2;
    # """, args)
    #
    #
    #

    #########################
    # trans_dispatch
    # --- Not used ---

    #########################
    # batteries
    # (now included as standard storage projects, but kept here
    # to support older projects that haven't upgraded yet)
    bat_years = "BATTERY_CAPITAL_COST_YEARS"
    bat_cost = "battery_capital_cost_per_mwh_capacity_by_year"
    non_cost_bat_vars = sorted(
        [k for k in args if k.startswith("battery_") and k not in [bat_years, bat_cost]]
    )
    if non_cost_bat_vars:
        add_one_row_literal(queries, "batteries.csv", non_cost_bat_vars, args)
    if bat_years in args and bat_cost in args:
        # annual costs were provided -- write those to a tab file
        add_literal_table(
            queries,
            "battery_capital_cost.csv",
            headers=[bat_years, bat_cost],
            data=list(zip(args[bat_years], args[bat_cost])),
            arguments=args,
        )

    #########################
    # Total land in each class in each load zone
    add_query(
        queries,
        "load_zone_land_class_area.csv",
        """
        SELECT load_zone, land_class, area as load_zone_land_class_area
        FROM load_zone_land_class_area
        WHERE load_zone in %(load_zones)s;
    """,
        args,
    )

    #########################
    # EV annual energy consumption (original, basic version)
    # print "ev_scenario:", args.get('ev_scenario', None)
    if args.get("ev_scenario", None) is not None:
        add_query(
            queries,
            "ev_fleet_info.csv",
            """
            SELECT load_zone as "LOAD_ZONE", period as "PERIOD",
                ev_share, ice_miles_per_gallon, ev_miles_per_kwh, ev_extra_cost_per_vehicle_year,
                n_all_vehicles, vmt_per_vehicle
            FROM ev_adoption a JOIN periods p on a.year = p.period
            WHERE load_zone in %(load_zones)s
                AND time_sample = %(time_sample)s
                AND ev_scenario = %(ev_scenario)s
            ORDER BY 1, 2;
        """,
            args,
        )
        # power consumption for each hour of the day under business-as-usual charging
        # note: the charge weights have a mean value of 1.0, but go up and down in different hours
        # NOTE: This may not average out to exactly 1.0 if time sampling is not every hour.
        # We could get mean charging during each time sample by calculating avg(ev_bau_mw)
        # and changing the hour_of_day join to
        # (p.hour_of_day - h.hour_of_day + 24) % 24 < ts_duration_of_tp
        # but that would be inconsistent with how we handle loads and weather
        # (generally point sample at start of timepoint or avg. value over first
        # hour of timepoint; not whole timepoint)
        add_query(
            queries,
            "ev_bau_load.csv",
            """
            SELECT
                load_zone AS "LOAD_ZONE",
                timepoint AS "TIMEPOINT",
                charge_weight * ev_share * n_all_vehicles * vmt_per_vehicle
                    / (1000.0 * ev_miles_per_kwh) / 8760 as ev_bau_mw
            FROM ev_adoption e
                JOIN timeseries d ON d.period = e.year
                JOIN timepoints h USING (timeseries, time_sample)
                JOIN ev_hourly_charge_profiles p
                    ON p.charge_profile = %(ev_charge_profile)s
                        AND p.hour_of_day = h.hour_of_day
            WHERE load_zone in %(load_zones)s
                AND time_sample = %(time_sample)s
                AND ev_scenario = %(ev_scenario)s
            ORDER BY 1, 2;
        """,
            args,
        )

    #########################
    # EV annual energy consumption (advanced, frozen Dantzig-Wolfe version)
    if args.get("ev_scenario", None) is not None:
        add_query(
            queries,
            "ev_share.csv",
            """
            SELECT
                load_zone as "LOAD_ZONE", period as "PERIOD",
                ev_share
            FROM ev_adoption a JOIN periods p on a.year = p.period
            WHERE load_zone in %(load_zones)s
                AND time_sample = %(time_sample)s
                AND ev_scenario = %(ev_scenario)s
            ORDER BY 1, 2;
        """,
            args,
        )
        add_query(
            queries,
            "ev_fleet_info_advanced.csv",
            """
            WITH detailed_fleet AS (
                SELECT
                    a.load_zone AS "LOAD_ZONE",
                    replace(f."vehicle type", ' ', '_') AS "VEHICLE_TYPE",
                    p.period AS "PERIOD",
                    f."number of vehicles" AS "n_vehicles", -- for whole fleet, not current adoption level
                    CASE
                    WHEN period <= 2020 THEN "gals fuel per year 2020"
                    WHEN period >= 2045 THEN "gals fuel per year 2045"
                    ELSE
                        (period-2020)/25.0 * "gals fuel per year 2045"
                        + (2045-period)/25.0 * "gals fuel per year 2020"
                    END AS "ice_gals_per_year",
                    CONCAT_WS('_', 'Motor', "ICE fuel") AS "ice_fuel",
                    "kWh per year" AS "ev_kwh_per_year",
                    CASE
                    WHEN period <= 2020 THEN "EV extra capital cost per year 2020"
                    WHEN period >= 2045 THEN "EV extra capital cost per year 2045"
                    ELSE
                        (period-2020)/25.0 * "EV extra capital cost per year 2045"
                        + (2045-period)/25.0 * "EV extra capital cost per year 2020"
                    END AS "ev_extra_cost_per_vehicle_year"
                 FROM ev_adoption a
                    JOIN periods p ON a.year = p.period
                    JOIN ev_fleet f ON f.load_zone = a.load_zone
                WHERE a.load_zone in %(load_zones)s
                    AND time_sample = %(time_sample)s
                    AND ev_scenario = %(ev_scenario)s
            )
            SELECT "LOAD_ZONE",
                CONCAT_WS('_', 'All', replace(ice_fuel, 'Motor_', ''), 'Vehicles') AS "VEHICLE_TYPE",
                "PERIOD",
                SUM(n_vehicles) AS n_vehicles,
                SUM(ice_gals_per_year*n_vehicles)/SUM(n_vehicles) AS ice_gals_per_year,
                ice_fuel,
                SUM(ev_kwh_per_year*n_vehicles)/SUM(n_vehicles) AS ev_kwh_per_year,
                SUM(ev_extra_cost_per_vehicle_year*n_vehicles)/SUM(n_vehicles)
                    AS ev_extra_cost_per_vehicle_year
            FROM detailed_fleet
            GROUP BY 1, 2, 3, 6
            ORDER BY 1, 2, 3;
        """,
            args,
        )
        # power consumption bids for each hour of the day
        # (consolidate to one vehicle class to accelerate data retrieval and
        # reduce model memory requirements) (note that there are 6 classes of
        # vehicle and 25 bids for for 24-hour models, which makes 150 entries
        # per load zone and timestep, which is larger than the renewable
        # capacity factor data)
        if args.get("skip_ev_bids", False):
            print("SKIPPING ev_charging_bids.csv")
        else:
            add_query(
                queries,
                "ev_charging_bids.csv",
                """
                SELECT
                    b.load_zone AS "LOAD_ZONE",
                    CONCAT_WS('_', 'All', "ICE fuel", 'Vehicles') AS "VEHICLE_TYPE",
                    bid_number AS "BID_NUM",
                    timepoint AS "TIMEPOINT",
                    sum(charge_mw) AS ev_bid_by_type
                FROM timeseries d
                    JOIN timepoints h USING (timeseries, time_sample)
                    JOIN ev_charging_bids b
                        ON b.hour = h.hour_of_day AND b.hours_per_step = d.ts_duration_of_tp
                    JOIN ev_fleet f ON b.vehicle_type=f."vehicle type" AND b.load_zone=f.load_zone
                WHERE b.load_zone in %(load_zones)s
                    AND d.time_sample = %(time_sample)s
                GROUP BY 1, 2, 3, 4
                ORDER BY 1, 2, 3, 4;
            """,
                args,
            )

    #########################
    # pumped hydro
    # TODO: put these data in a database with hydro_scenario's and pull them from there

    if "pumped_hydro_headers" in args:
        add_literal_table(
            queries,
            "pumped_hydro.csv",
            headers=args["pumped_hydro_headers"],
            data=args["pumped_hydro_projects"],
            arguments=args,
        )

    #########################
    # hydrogen
    # TODO: put these data in a database and pull from there
    add_one_row_literal(
        queries,
        "hydrogen.csv",
        sorted(
            [
                k
                for k in args
                if k.startswith("hydrogen_") or k.startswith("liquid_hydrogen_")
            ]
        ),
        args,
    )

    #########################
    # PHA data
    pha_params = sorted([k for k in args if k.startswith("pha_")])
    if pha_params:
        add_one_row_literal(queries, "pha.csv", pha_params, args)

    return queries


def make_file_path(file, args):
    """Create any directories and subdirectories needed to store data in the specified file,
    based on inputs_dir and inputs_subdir arguments. Return a pathname to the file."""
    # extract extra path information from args (if available)
    # and build a path to the specified file.
    path = os.path.join(args.get("inputs_dir", ""), args.get("inputs_subdir", ""))
    if path != "" and not os.path.exists(path):
        os.makedirs(path)
    path = os.path.join(path, file)
    return path


con = None


def db_cursor():
    global con
    if con is None:
        try:
            # note: we don't import until here to avoid interfering with unit tests on systems that don't have
            # (or need) psycopg2
            global psycopg2, sql
            import psycopg2, psycopg2.sql as sql
        except ImportError:
            print(
                dedent(
                    """
                ############################################################################################
                Unable to import psycopg2 module to access database server.
                Please install this module via 'conda install psycopg2' or 'pip install psycopg2'.
                ############################################################################################
                """
                )
            )
            raise
        try:
            # note: the connection gets created when the module loads and never gets closed (until presumably python exits)
            con = psycopg2.connect(database=pgdatabase, host=pghost, user=pguser)
            # use read-only session, because that's enough for this script and it's possible something
            # weird could come through in the configuration info that gets passed to postgresql
            con.set_session(readonly=True, autocommit=True)
            print(
                "Reading data from database {} on server {}".format(pgdatabase, pghost)
            )

        except psycopg2.OperationalError:
            print(
                dedent(
                    """
                ############################################################################################
                Error while connecting to database '{db}' on postgres server '{server}' as user '{user}'.
                Please ensure that the following environment variables are set:
                PGUSER = your postgres username
                PGHOST = hostname or IP address of postgres server
                PGDATABASE = name of switch database on this server.
                There should also be a line like "*:*:*:<user>:<password>" in ~/.pgpass (which should be chmod 0600)
                or in %APPDATA%\postgresql\pgpass.conf (Windows).
                See http://www.postgresql.org/docs/9.1/static/libpq-pgpass.html for more details.
                ############################################################################################
                """.format(
                        server=pghost, db=pgdatabase, user=pguser
                    )
                )
            )
            raise
    return con.cursor()


def prepare_query(query, arguments):
    return db_cursor().mogrify(query, arguments)


def add_query(queries, file, query, arguments):
    queries.append((file, prepare_query(query, arguments)))


def add_literal_table(queries, table, headers, data, arguments={}):
    # Create an SQL query that returns the  values defined by the headers and data
    if data:
        query = sql.SQL("SELECT * FROM (VALUES {}) AS t ({})").format(
            sql.SQL(", ").join(sql.Literal(tuple(row)) for row in data),
            sql.SQL(", ").join(sql.Identifier(h) for h in headers),
        )
    else:
        # create a zero-row table with the right headers
        query = sql.SQL("SELECT * FROM (VALUES {}) AS t ({}) WHERE FALSE").format(
            sql.Literal(tuple("" for h in headers)),
            sql.SQL(", ").join(sql.Identifier(h) for h in headers),
        )
    add_query(queries, table, query, arguments)


def add_one_row_literal(queries, table, arg_names, args):
    add_literal_table(
        queries, table, arg_names, [tuple(args[n] for n in arg_names)], args
    )


def write_table(output_file, query):
    print("Writing {file} ...".format(file=output_file), end=" ")
    sys.stdout.flush()  # display the part line to the user

    start = time.time()
    cur = db_cursor()
    try:
        cur.execute(query)
    except:
        print("\nError running the following query:\n{}\n".format(query.decode()))
        raise
    with open(output_file, "w") as f:
        writerow(f, [d[0] for d in cur.description])  # header
        writerows(f, cur)  # data
    print("time taken: {dur:.2f}s".format(dur=time.time() - start))


def stringify(val):
    if val is None:
        out = "."
    elif type(val) is str:
        out = val.replace('"', '""')
        if any(char in out for char in [" ", "\t", '"', "'", ","]):
            out = '"' + out + '"'
    else:
        out = str(val)
    return out


def writerow(f, row):
    f.write(",".join(stringify(c) for c in row) + "\n")


def writerows(f, rows):
    for r in rows:
        writerow(f, r)
