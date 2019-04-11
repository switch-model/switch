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

import time, sys, collections, os
from textwrap import dedent
from switch_model import __version__ as switch_version

# NOTE: instead of using the python csv writer, this directly writes tables to
# file in the pyomo .tab format. This uses tabs between columns and the standard
# line break for the system it is run on. This does the following translations (only):
# - If a value contains double quotes, they get doubled.
# - If a value contains a single quote, tab or space character, the value gets enclosed in double quotes.
#   (Note that pyomo doesn't allow quoting (and therefore spaces) in column headers.)
# - null values are converted to . (the pyomo/ampl standard for missing data)
# - any other values are simply passed to str().

# NOTE: this does not use the python csv writer because it doesn't support the quoting
# or null behaviors described above.


# NOTE: ANSI SQL specifies single quotes for literal strings, and postgres conforms
# to this, so all the queries below should use single quotes around strings.

# NOTE: write_table() will automatically convert null values to '.',
# so pyomo will recognize them as missing data

# NOTE: the code below could be made more generic, e.g., a list of
# table names and queries, which are then processed at the end.
# But that would be harder to debug, and wouldn't allow for ad hoc
# calculations or writing .dat files (which are used for a few parameters)

def write_tables(**args):

    # TODO: any arguments that are defined with default values below (args.get()) could
    # have those default values assigned here. Then they can be used directly in queries
    # instead of using them to create snippets that are used in the queries. This would
    # also document the available arguments a little better.

    # catch obsolete arguments (otherwise they would be silently ignored)
    if 'ev_scen_id' in args:
        raise ValueError("ev_scen_id argument is no longer supported; use ev_scenario instead.")

    # write version marker file
    with open(make_file_path('switch_inputs_version.txt', args), 'w') as f:
        f.write(switch_version)

    #########################
    # timescales

    # reusable clause to calculate the length of each period
    # If this is within 1% of an integer number of years, it rounds to the integer,
    # to allow for weights that add up to 365 or 365.25 days per year
    with_period_length = """
        WITH period_length as (
            SELECT
                period,
                -- note: for some reason modulo doesn't work on real values in postgresql
                CASE WHEN mod((sum(ts_scale_to_period)/365.25)::numeric, 1) BETWEEN -0.01 and 0.01
                    THEN
                        -- integer number of years
                        round(sum(ts_scale_to_period)/365.25)
                    ELSE
                        -- make a decent guess about number of years
                        sum(ts_scale_to_period)/365.25
                END as period_length
                FROM study_date WHERE time_sample = %(time_sample)s
                GROUP BY 1
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
    write_table('periods.tab',
        with_period_length + """
        SELECT p.period AS "INVESTMENT_PERIOD",
                p.period as period_start,
                p.period + period_length as period_end
            FROM study_periods p JOIN period_length l USING (period)
            WHERE time_sample = %(time_sample)s
            ORDER by 1;
    """, args)

    write_table('timeseries.tab', """
        SELECT study_date as "TIMESERIES", period as ts_period,
            ts_duration_of_tp, ts_num_tps, ts_scale_to_period
        FROM study_date
        WHERE time_sample = %(time_sample)s
        ORDER BY 1;
    """, args)

    write_table('timepoints.tab', """
        SELECT h.study_hour as timepoint_id,
                to_char(date_time + (period - extract(year from date_time)) * interval '1 year',
                    'YYYY-MM-DD-HH24:MI') as timestamp,
                h.study_date as timeseries
            FROM study_hour h JOIN study_date d USING (study_date, time_sample)
            WHERE h.time_sample = %(time_sample)s
            ORDER BY period, extract(doy from date), study_hour;
    """, args)

    # double-check that arguments are valid
    cur = db_cursor()
    for table in ['generator_costs_by_year', 'generator_info']:
        cur.execute(
            'select * from {} where tech_scen_id = %(tech_scen_id)s limit 1'.format(table),
            args
        )
        if len(list(cur)) == 0:
            print "================================================================"
            print "WARNING: no records found in {} for tech_scen_id='{}'".format(table, args['tech_scen_id'])
            print "================================================================"
            time.sleep(2)
    del cur

    #########################
    # create temporary tables that can be referenced by other queries
    # to identify available projects and technologies
    db_cursor().execute("""
        DROP TABLE IF EXISTS study_length;
        CREATE TEMPORARY TABLE study_length AS
            {}
            SELECT min(period)::real as study_start, max(period+period_length)::real AS study_end
            FROM period_length;

        DROP TABLE IF EXISTS study_projects;
        CREATE TEMPORARY TABLE study_projects AS
            SELECT DISTINCT
                CONCAT_WS('_', load_zone, p.technology, nullif(site, 'na'), nullif(orientation, 'na'))
                    AS "GENERATION_PROJECT",
                p.*,
                g.tech_scen_id
            FROM project p
                JOIN generator_info g USING (technology)
                CROSS JOIN study_length
                -- existing projects still in use during the study
                LEFT JOIN proj_existing_builds e ON (
                    e.project_id = p.project_id
                    AND e.build_year + g.max_age_years > study_start
                    AND e.build_year < study_end
                )
                -- projects that could be built during the study
                LEFT JOIN generator_costs_by_year c ON (
                    c.tech_scen_id = g.tech_scen_id
                    AND c.technology = g.technology
                    AND (g.min_vintage_year IS NULL OR c.year >= g.min_vintage_year)
                    AND c.year >= study_start
                    AND c.year < study_end
                )
            WHERE (e.project_id IS NOT NULL OR c.technology IS NOT NULL)
                AND p.load_zone in %(load_zones)s
                AND g.tech_scen_id IN ('all', %(tech_scen_id)s)
                AND g.technology NOT IN %(exclude_technologies)s;

        DROP TABLE IF EXISTS study_generator_info;
        CREATE TEMPORARY TABLE study_generator_info AS
            SELECT DISTINCT g.*
            FROM generator_info g JOIN study_projects p USING (tech_scen_id, technology);
    """.format(with_period_length), args)

    # import pdb; pdb.set_trace()

    #########################
    # financials

    # this just uses a dat file, not a table (and the values are not in a database for now)
    write_dat_file(
        'financials.dat',
        ['base_financial_year', 'interest_rate', 'discount_rate'],
        args
    )

    #########################
    # load_zones

    # note: we don't provide the following fields in this version:
    # zone_cost_multipliers, zone_ccs_distance_km, zone_dbid,
    # existing_local_td, local_td_annual_cost_per_mw
    write_table('load_zones.tab', """
        SELECT load_zone as "LOAD_ZONE"
        FROM load_zone
        WHERE load_zone in %(load_zones)s
    """, args)

    # NOTE: we don't provide zone_peak_loads.tab (sometimes used by local_td.py) in this version.

    # get system loads, scaled from the historical years to the model years
    # note: 'offset' is a keyword in postgresql, so we use double-quotes to specify the column name
    write_table('loads.tab', """
        SELECT
            l.load_zone AS "LOAD_ZONE",
            study_hour AS "TIMEPOINT",
            GREATEST(0, system_load * scale + "offset") AS zone_demand_mw
        FROM study_date d
            JOIN study_hour h USING (time_sample, study_date)
            JOIN system_load l USING (date_time)
            JOIN system_load_scale s ON (
                s.load_zone = l.load_zone
                AND s.year_hist = extract(year from l.date_time)
                AND s.year_fore = d.period)
        WHERE l.load_zone in %(load_zones)s
            AND d.time_sample = %(time_sample)s
            AND load_scen_id = %(load_scen_id)s;
    """, args)


    #########################
    # fuels

    write_table('non_fuel_energy_sources.tab', """
        SELECT DISTINCT fuel AS "NON_FUEL_ENERGY_SOURCES"
            FROM study_generator_info
            WHERE fuel NOT IN (SELECT fuel_type FROM fuel_costs);
    """, args)

    # gather info on fuels
    write_table('fuels.tab', """
        SELECT DISTINCT replace(c.fuel_type, ' ', '_') AS fuel, co2_intensity, 0.0 AS upstream_co2_intensity, rps_eligible
        FROM fuel_costs c JOIN energy_source_properties p on (p.energy_source = c.fuel_type)
        WHERE load_zone in %(load_zones)s AND fuel_scen_id=%(fuel_scen_id)s
        ORDER BY 1;
    """, args)

    #########################
    # rps targets

    write_tab_file(
        'rps_targets.tab',
        headers=('year', 'rps_target'),
        data=[(y, args['rps_targets'][y]) for y in sorted(args['rps_targets'].keys())],
        arguments=args
    )

    #########################
    # fuel_markets

    # deflate HECO fuel scenarios to base year, and inflate EIA-based scenarios
    # from 2013 (forecast base year) to model base year. (ugh)
    # TODO: add a flag to fuel_costs indicating whether forecasts are real or nominal,
    # and base year, and possibly inflation rate.
    if args['fuel_scen_id'] in ('1', '2', '3'):
        raise ValueError("fuel_scen_ids '1', '2' and '3' (specified in nominal dollars) are no longer supported.")

    if args.get("use_simple_fuel_costs", False):
        # simple fuel markets with no bulk LNG expansion option (use fuel_cost module)
        # TODO: get monthly fuel costs from Karl Jandoc spreadsheet
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

        write_table('fuel_cost.tab',
            with_period_length + """
            SELECT load_zone, replace(fuel_type, ' ', '_') as fuel, p.period,
                avg(
                    price_mmbtu
                    * power(1.0+%(inflation_rate)s, %(base_financial_year)s-c.base_year)
                    + COALESCE(fixed_cost, 0.00)
                ) as fuel_cost
            FROM fuel_costs c, study_periods p JOIN period_length l USING (period)
            WHERE load_zone in %(load_zones)s
                AND fuel_scen_id = %(fuel_scen_id)s
                AND p.time_sample = %(time_sample)s
                AND (fuel_type != 'LNG' OR {lng_selector})
                AND c.year >= p.period AND c.year < p.period + l.period_length
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3;
        """.format(lng_selector=lng_selector), args)
    else:
        # advanced fuel markets with LNG expansion options (used by forward-looking models)
        # (use fuel_markets module)
        write_table('regional_fuel_markets.tab', """
            SELECT DISTINCT
                concat('Hawaii_', replace(fuel_type, ' ', '_')) AS regional_fuel_market,
                replace(fuel_type, ' ', '_') AS fuel
            FROM fuel_costs
            WHERE load_zone in %(load_zones)s AND fuel_scen_id = %(fuel_scen_id)s;
        """, args)

        write_table('fuel_supply_curves.tab',
            with_period_length + """
            SELECT concat('Hawaii_', replace(fuel_type, ' ', '_')) as regional_fuel_market,
                replace(fuel_type, ' ', '_') as fuel,
                tier,
                p.period,
                avg(price_mmbtu * power(1.0+%(inflation_rate)s, %(base_financial_year)s-c.base_year)) as unit_cost,
                avg(max_avail_at_cost) as max_avail_at_cost,
                avg(fixed_cost) as fixed_cost,
                avg(max_age) as max_age
            FROM fuel_costs c, study_periods p JOIN period_length l USING (period)
            WHERE load_zone in %(load_zones)s
                AND fuel_scen_id = %(fuel_scen_id)s
                AND p.time_sample = %(time_sample)s
                AND (c.year >= p.period AND c.year < p.period + l.period_length)
            GROUP BY 1, 2, 3, 4
            ORDER BY 1, 2, 3, 4;
        """, args)

        write_table('zone_to_regional_fuel_market.tab', """
            SELECT DISTINCT load_zone, concat('Hawaii_', replace(fuel_type, ' ', '_')) AS regional_fuel_market
            FROM fuel_costs
            WHERE load_zone in %(load_zones)s AND fuel_scen_id = %(fuel_scen_id)s;
        """, args)

    # TODO: (when multi-island) add fuel_cost_adders for each zone


    #########################
    # investment.gen_build and part of operation.unitcommit.commit

    # NOTE: this converts variable o&m from $/kWh to $/MWh
    # and heat rate from Btu/kWh to MBtu/MWh

    # NOTE: for all energy sources other than 'SUN' and 'WND' (i.e., all fuels),
    # we report the fuel as 'multiple' and then provide data in a multi-fuel table.
    # Some of these are actually single-fuel, but this approach is simpler than sorting
    # them out within each query, and it doesn't add any complexity to the model.

    if args.get('wind_capital_cost_escalator', 0.0) or args.get('pv_capital_cost_escalator', 0.0):
        # user supplied a non-zero escalator
        raise ValueError(
            'wind_capital_cost_escalator and pv_capital_cost_escalator arguments are '
            'no longer supported by scenario_data.write_tables(); '
            'assign time-varying costs in the generator_costs_by_year table instead.'
        )
    if args.get('generator_costs_base_year', 0):
        # user supplied a generator_costs_base_year
        raise ValueError(
            'generator_costs_base_year is no longer supported by scenario_data.write_tables(); '
            'assign base_year in the generator_costs_by_year table instead.'
        )


    # TODO: make sure the heat rates are null for non-fuel projects in the upstream database,
    # and remove the correction code from here

    # TODO: maybe replace "fuel IN ('SUN', 'WND', 'MSW')" with "fuel not in (SELECT fuel FROM fuel_cost)"
    # TODO: convert 'MSW' to a proper fuel, possibly with a negative cost, instead of ignoring it

    # Omit full load heat rates if we are providing heat rate curves instead
    if args.get('use_incremental_heat_rates', False):
        full_load_heat_rate = 'null'
    else:
        full_load_heat_rate = '0.001*heat_rate'

    if args.get('report_forced_outage_rates', False):
        forced_outage_rate = 'forced_outage_rate'
    else:
        forced_outage_rate = '0'

    # if needed, follow the query below with another one that specifies
    # COALESCE(gen_connect_cost_per_mw, 0.0) AS gen_connect_cost_per_mw
    write_table('generation_projects_info.tab', """
        SELECT
            "GENERATION_PROJECT",
            load_zone AS gen_load_zone,
            technology AS gen_tech,
            spur_line_cost_per_mw + 1000 * substation_cost_per_kw AS gen_connect_cost_per_mw,
            max_capacity AS gen_capacity_limit_mw,
            unit_size as gen_unit_size,
            max_age_years as gen_max_age,
            scheduled_outage_rate as gen_scheduled_outage_rate,
            {fo} as gen_forced_outage_rate,
            intermittent as gen_is_variable,
            baseload as gen_is_baseload,
            -- 0 as gen_is_flexible_baseload,
            cogen as gen_is_cogen,
            -- non_cycling as gen_non_cycling,
            variable_o_m * 1000.0 AS gen_variable_om,
            CASE WHEN fuel IN ('SUN', 'WND', 'MSW', 'Battery', 'Hydro') THEN fuel ELSE 'multiple' END AS gen_energy_source,
            CASE WHEN fuel IN ('SUN', 'WND', 'MSW', 'Battery', 'Hydro') THEN null ELSE {flhr} END AS gen_full_load_heat_rate,
            min_uptime as gen_min_uptime,
            min_downtime as gen_min_downtime,
            startup_energy / unit_size as gen_startup_fuel,
            gen_storage_efficiency,
            gen_storage_energy_to_power_ratio,
            gen_storage_max_cycles_per_year
        FROM study_projects JOIN study_generator_info USING (technology)
        ORDER BY 2, 3, 1;
    """.format(fo=forced_outage_rate, flhr=full_load_heat_rate), args)

    write_table('gen_build_predetermined.tab', """
        SELECT
            "GENERATION_PROJECT",
            build_year,
            SUM(proj_existing_cap) as gen_predetermined_cap
        FROM study_projects JOIN proj_existing_builds USING (project_id)
        GROUP BY 1, 2
        ORDER BY 1, 2;
    """, args)

    # NOTE: these costs must be expressed in $/MW, $/MWh or $/MW-year,
    # not $/kW, $/kWh or $/kW-year.
    # NOTE: for now, we only specify storage costs per unit of power, not
    # on per unit of energy, so we insert $0 as the energy cost here.
    # NOTE: projects should have NULL for overnight cost and fixed O&M in
    # proj_existing_builds if they have an entry for the same year in
    # generator_costs_by_year. If they have costs in both, they will both
    # get passed through to the data table, and Switch will raise an error
    # (as it should, because costs are ambiguous in this case).
    write_table('gen_build_costs.tab', """
        WITH gen_build_costs AS (
            SELECT
                i.technology,
                c.year AS build_year,
                c.capital_cost_per_kw * 1000.0
                    * power(1.0+%(inflation_rate)s, %(base_financial_year)s-c.base_year)
                    AS gen_overnight_cost,
                c.capital_cost_per_kwh * 1000.0 AS gen_storage_energy_overnight_cost,
                c.fixed_o_m * 1000.0 * power(1.0+%(inflation_rate)s, %(base_financial_year)s-i.base_year)
                    AS gen_fixed_o_m,
                i.min_vintage_year  -- used for build_year filter below
            FROM study_generator_info i
                JOIN generator_costs_by_year c USING (technology, tech_scen_id)
            ORDER BY 1, 2
        )
        SELECT   -- costs specified in proj_existing_builds
            "GENERATION_PROJECT",
            b.build_year,
            SUM(
                power(1.0+%(inflation_rate)s, %(base_financial_year)s-b.base_year)
                * b.proj_overnight_cost * 1000.0 * proj_existing_cap
            ) / SUM(proj_existing_cap)
                AS gen_overnight_cost,
            null AS gen_storage_energy_overnight_cost,
            SUM(
                power(1.0+%(inflation_rate)s, %(base_financial_year)s-b.base_year)
                * b.proj_fixed_om * 1000.0 * proj_existing_cap
            ) / SUM(proj_existing_cap)
                AS gen_fixed_om
        FROM study_projects p
            JOIN proj_existing_builds b USING (project_id)
        WHERE (b.proj_overnight_cost IS NOT NULL OR b.proj_fixed_om IS NOT NULL)
        GROUP BY 1, 2
        UNION
        SELECT   -- costs specified in generator_costs_by_year
            "GENERATION_PROJECT", c.build_year, gen_overnight_cost,
            gen_storage_energy_overnight_cost, gen_fixed_o_m
        FROM study_projects proj
            JOIN gen_build_costs c USING (technology)
            LEFT JOIN study_periods per ON (per.time_sample = %(time_sample)s AND c.build_year = per.period)
            LEFT JOIN proj_existing_builds e ON (e.project_id = proj.project_id AND e.build_year = c.build_year)
        WHERE
            -- note: this allows users to have build_year < min_vintage_year for predetermined projects
            -- that have entries in the cost table, e.g., if they want to prespecify some, but postpone
            -- additional construction until some later year (unlikely)
            (per.period IS NOT NULL AND (c.min_vintage_year IS NULL OR c.build_year >= c.min_vintage_year))
            OR e.project_id IS NOT NULL
        ORDER BY 1, 2;
    """, args)

    #########################
    # spinning_reserves_advanced (if wanted; otherwise defaults to just "spinning"
    if 'max_reserve_capability' in args or args.get('write_generation_projects_reserve_capability', False):

        # args['max_reserve_capability'] is a list of tuples of (technology, reserve_type)
        # (assumed equivalent to 'regulation' if not specified)
        # We unzip it to use with the unnest function (psycopg2 passes lists of tuples
        # as arrays of tuples, and unnest would keeps those as tuples)
        try:
            reserve_technologies, reserve_types = map(list, zip(*args['max_reserve_capability']))
        except KeyError:
            reserve_technologies, reserve_types = [], []
        res_args = args.copy()
        res_args['reserve_technologies']=reserve_technologies
        res_args['reserve_types']=reserve_types

        # note: casting is needed if the lists are empty; see https://stackoverflow.com/a/41893576/3830997
        write_table('generation_projects_reserve_capability.tab', """
            WITH reserve_capability (technology, reserve_type) as (
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
        """, res_args)


    #########################
    # operation.unitcommit.fuel_use

    # get part load heat rate curves if requested
    # note: we sort lexicographically by power output and fuel consumption, in case
    # there are segments where power or fuel consumption steps up while the other stays constant
    # That is nonconvex and not currently supported by SWITCH, but could potentially be used
    # in the future by assigning binary variables for activating each segment.
    # note: for sqlite, you could use "CONCAT(technology, ' ', output_mw, ' ', fuel_consumption_mmbtu_per_h) AS key"
    # TODO: rename fuel_consumption_mmbtu_per_h to fuel_use_mmbtu_per_h here and in import_data.py

    if args.get('use_incremental_heat_rates', False):
        write_table('gen_inc_heat_rates.tab', """
            WITH part_load AS (
                SELECT
                    row_number() OVER (ORDER BY technology, output_mw, fuel_consumption_mmbtu_per_h) AS key,
                    technology,
                    output_mw,
                    fuel_consumption_mmbtu_per_h
                FROM part_load_fuel_consumption JOIN study_generator_info USING (technology)
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
        """, args)

    # This gets a list of all the fueled projects (listed as "multiple" energy sources above),
    # and lists them as accepting any equivalent or lighter fuel. (However, cogen plants and plants
    # using fuels with rank 0 are not changed.) Fuels are also filtered against the list of fuels with
    # costs reported for the current scenario, so this can end up re-mapping one fuel in the database
    # (e.g., LSFO) to a similar fuel in the scenario (e.g., LSFO-Diesel-Blend), even if the original fuel
    # doesn't exist in the fuel_costs table. This can also be used to remap different names for the same
    # fuel (e.g., "COL" in the plant definition and "Coal" in the fuel_costs table, both with the same
    # fuel_rank).
    write_indexed_set_dat_file('gen_multiple_fuels.dat', 'FUELS_FOR_MULTIFUEL_GEN', """
        WITH all_techs AS (
            SELECT
                technology,
                fuel as orig_fuel,
                cogen
            FROM study_generator_info
        ), all_fueled_techs AS (
            SELECT * from all_techs WHERE orig_fuel NOT IN ('SUN', 'WND', 'MSW', 'Battery', 'Hydro')
        ), gen_multiple_fuels AS (
            SELECT DISTINCT technology, b.energy_source as fuel
            FROM all_fueled_techs t
                JOIN energy_source_properties a ON a.energy_source = t.orig_fuel
                JOIN energy_source_properties b ON b.fuel_rank >= a.fuel_rank AND
                    (a.fuel_rank > 0 OR a.energy_source = b.energy_source)    -- 0-rank can't change fuels
                WHERE b.energy_source IN (SELECT fuel_type FROM fuel_costs WHERE fuel_scen_id = %(fuel_scen_id)s)
        )
        SELECT "GENERATION_PROJECT", fuel
            FROM gen_multiple_fuels g JOIN study_projects p USING (technology)
            ORDER BY p.technology, p."GENERATION_PROJECT", g.fuel
    """, args)


    #########################
    # operation.gen_dispatch

    # skip this step if the user specifies "skip_cf" in the arguments (to speed up execution)
    if args.get("skip_cf", False):
        print "SKIPPING variable_capacity_factors.tab"
    else:
        write_table('variable_capacity_factors.tab', """
            SELECT
                "GENERATION_PROJECT",
                study_hour as timepoint,
                cap_factor as gen_max_capacity_factor
            FROM study_generator_info g
                JOIN study_projects p USING (technology)
                JOIN cap_factor c USING (project_id)
                JOIN study_hour h using (date_time)
            WHERE time_sample = %(time_sample)s
            ORDER BY 1, 2
        """, args)


    #########################
    # project.discrete_build

    # include this module, but it doesn't need any additional data.


    #########################
    # operation.unitcommit.commit

    # minimum commitment levels for existing projects

    # TODO: set gen_max_commit_fraction based on maintenance outage schedules
    # (needed for comparing switch marginal costs to FERC 715 data in 2007-08)

    # TODO: create data files showing reserve rules

    write_table('gen_timepoint_commit_bounds.tab', """
        SELECT * FROM (
            SELECT "GENERATION_PROJECT",
                study_hour AS "TIMEPOINT",
                CASE WHEN %(enable_must_run)s = 1 AND must_run = 1 THEN 1.0 ELSE null END
                    AS gen_min_commit_fraction,
                null AS gen_max_commit_fraction,
                null AS gen_min_load_fraction_TP
            FROM study_projects JOIN study_generator_info USING (technology)
                CROSS JOIN study_hour
            WHERE time_sample = %(time_sample)s
        ) AS the_data
        WHERE gen_min_commit_fraction IS NOT NULL
            OR gen_max_commit_fraction IS NOT NULL
            OR gen_min_load_fraction_TP IS NOT NULL;
    """, args)


    #########################
    # project.unitcommit.discrete

    # include this module, but it doesn't need any additional data.


    #########################
    # trans_build
    # --- Not used ---

    #
    # write_table('trans_lines.tab', """
    #     SELECT load_area_start AS load_zone_start, load_area_end AS load_zone_end,
    #         tid, length_km AS transmission_length_km, efficiency AS transmission_efficiency,
    #         existing_mw_from AS existing_transmission_from,
    #         existing_mw_to AS existing_transmission_to
    #     FROM trans_line
    #     WHERE load_area_start IN %(load_zones)s OR load_area_end IN %(load_zones)s
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
    bat_years = 'BATTERY_CAPITAL_COST_YEARS'
    bat_cost = 'battery_capital_cost_per_mwh_capacity_by_year'
    non_cost_bat_vars = sorted([k for k in args if k.startswith('battery_') and k not in [bat_years, bat_cost]])
    if non_cost_bat_vars:
        write_dat_file(
            'batteries.dat',
            non_cost_bat_vars,
            args
        )
    if bat_years in args and bat_cost in args:
        # annual costs were provided -- write those to a tab file
        write_tab_file(
            'battery_capital_cost.tab',
            headers=[bat_years, bat_cost],
            data=zip(args[bat_years], args[bat_cost]),
            arguments=args
        )

    #########################
    # EV annual energy consumption (original, basic version)
    # print "ev_scenario:", args.get('ev_scenario', None)
    if args.get('ev_scenario', None) is not None:
        write_table('ev_fleet_info.tab', """
            SELECT load_zone as "LOAD_ZONE", period as "PERIOD",
                ev_share, ice_miles_per_gallon, ev_miles_per_kwh, ev_extra_cost_per_vehicle_year,
                n_all_vehicles, vmt_per_vehicle
            FROM ev_adoption a JOIN study_periods p on a.year = p.period
            WHERE load_zone in %(load_zones)s
                AND time_sample = %(time_sample)s
                AND ev_scenario = %(ev_scenario)s
            ORDER BY 1, 2;
        """, args)
        # power consumption for each hour of the day under business-as-usual charging
        # note: the charge weights have a mean value of 1.0, but go up and down in different hours
        write_table('ev_bau_load.tab', """
            SELECT
                load_zone AS "LOAD_ZONE",
                study_hour AS "TIMEPOINT",
                charge_weight * ev_share * n_all_vehicles * vmt_per_vehicle / (1000.0 * ev_miles_per_kwh) / 8760 as ev_bau_mw
            FROM ev_adoption e
                JOIN study_date d ON d.period = e.year
                JOIN study_hour h USING (study_date, time_sample)
                JOIN ev_hourly_charge_profile p
                    ON p.hour_of_day = h.hour_of_day
            WHERE load_zone in %(load_zones)s
                AND time_sample = %(time_sample)s
                AND ev_scenario = %(ev_scenario)s
            ORDER BY 1, 2;
        """, args)

    #########################
    # EV annual energy consumption (advanced, frozen Dantzig-Wolfe version)
    if args.get('ev_scenario', None) is not None:
        write_table('ev_share.tab', """
            SELECT
                load_zone as "LOAD_ZONE", period as "PERIOD",
                ev_share
            FROM ev_adoption a JOIN study_periods p on a.year = p.period
            WHERE load_zone in %(load_zones)s
                AND time_sample = %(time_sample)s
                AND ev_scenario = %(ev_scenario)s
            ORDER BY 1, 2;
        """, args)
        write_table('ev_fleet_info_advanced.tab', """
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
                    JOIN study_periods p ON a.year = p.period
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
        """, args)
        # power consumption bids for each hour of the day
        # (consolidate to one vehicle class to accelerate data retrieval and
        # reduce model memory requirements) (note that there are 6 classes of
        # vehicle and 25 bids for for 24-hour models, which makes 150 entries
        # per load zone and timestep, which is larger than the renewable
        # capacity factor data)
        if args.get("skip_ev_bids", False):
            print "SKIPPING ev_charging_bids.tab"
        else:
            write_table('ev_charging_bids.tab', """
                SELECT
                    b.load_zone AS "LOAD_ZONE",
                    CONCAT_WS('_', 'All', "ICE fuel", 'Vehicles') AS "VEHICLE_TYPE",
                    bid_number AS "BID_NUM",
                    study_hour AS "TIMEPOINT",
                    sum(charge_mw) AS ev_bid_by_type
                FROM study_date d
                    JOIN study_hour h USING (study_date, time_sample)
                    JOIN ev_charging_bids b
                        ON b.hour = h.hour_of_day AND b.hours_per_step = d.ts_duration_of_tp
                    JOIN ev_fleet f ON b.vehicle_type=f."vehicle type" AND b.load_zone=f.load_zone
                WHERE b.load_zone in %(load_zones)s
                    AND d.time_sample = %(time_sample)s
                GROUP BY 1, 2, 3, 4
                ORDER BY 1, 2, 3, 4;
            """, args)

    #########################
    # pumped hydro
    # TODO: put these data in a database with hydro_scen_id's and pull them from there

    if "pumped_hydro_headers" in args:
        write_tab_file(
            'pumped_hydro.tab',
            headers=args["pumped_hydro_headers"],
            data=args["pumped_hydro_projects"],
            arguments=args
        )

    # write_dat_file(
    #     'pumped_hydro.dat',
    #     [k for k in args if k.startswith('pumped_hydro_')],
    #     args
    # )

    #########################
    # hydrogen
    # TODO: put these data in a database and write a .tab file instead
    write_dat_file(
        'hydrogen.dat',
        sorted([k for k in args if k.startswith('hydrogen_') or k.startswith('liquid_hydrogen_')]),
        args
    )


    #########################
    # PHA data
    pha_params = sorted([k for k in args if k.startswith('pha_')])
    if pha_params:
        write_dat_file(
            'pha.dat',
            pha_params,
            args
        )

# the two functions below could be used as the start of a system
# to write placeholder files for any files in the current scenario
# that match the base files. This could be used to avoid creating large
# files (variable_cap_factor.tab) for alternative scenarios that are
# otherwise very similar. i.e., placeholder .tab or .dat files could
# be written with just the line 'include ../variable_cap_factor.tab' or
# 'include ../financial.dat'.

def any_alt_args_in_list(args, l):
    """Report whether any arguments in the args list appear in the list l."""
    for a in args.get('alt_args', {}):
        if a in l:
            return True
    return False

def any_alt_args_in_query(args, query):
    """Report whether any arguments in the args list appear in the list l."""
    for a in args.get('alt_args', {}):
        if '%(' + a + ')s' in query:
            return True
    return False

def make_file_path(file, args):
    """Create any directories and subdirectories needed to store data in the specified file,
    based on inputs_dir and inputs_subdir arguments. Return a pathname to the file."""
    # extract extra path information from args (if available)
    # and build a path to the specified file.
    path = os.path.join(args.get('inputs_dir', ''), args.get('inputs_subdir', ''))
    if path != '' and not os.path.exists(path):
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
            global psycopg2
            import psycopg2
        except ImportError:
            print dedent("""
                ############################################################################################
                Unable to import psycopg2 module to access database server.
                Please install this module via 'conda install psycopg2' or 'pip install psycopg2'.
                ############################################################################################
                """)
            raise
        try:
            pghost='redr.eng.hawaii.edu'
            # note: the connection gets created when the module loads and never gets closed (until presumably python exits)
            con = psycopg2.connect(database='switch', host=pghost) #, user='switch_user')

        except psycopg2.OperationalError:
            print dedent("""
                ############################################################################################
                Error while connecting to switch database on postgres server {server}.
                Please ensure that the PGUSER environment variable is set with your postgres username
                and there is a line like "*:*:*:<user>:<password>" in ~/.pgpass (which should be chmod 0600)
                or in %APPDATA%\postgresql\pgpass.conf (Windows).
                See http://www.postgresql.org/docs/9.1/static/libpq-pgpass.html for more details.
                ############################################################################################
                """.format(server=pghost))
            raise
    return con.cursor()

def write_dat_file(output_file, args_to_write, arguments):
    """ write a simple .dat file with the arguments specified in args_to_write,
    drawn from the arguments dictionary"""

    if any(arg in arguments for arg in args_to_write):
        output_file = make_file_path(output_file, arguments)
        print "Writing {file} ...".format(file=output_file),
        sys.stdout.flush()  # display the part line to the user
        start=time.time()

        with open(output_file, 'w') as f:
            f.writelines([
                'param ' + name + ' := ' + str(arguments[name]) + ';\n'
                for name in args_to_write if name in arguments
            ])

        print "time taken: {dur:.2f}s".format(dur=time.time()-start)

def write_table(output_file, query, arguments):
    output_file = make_file_path(output_file, arguments)
    cur = db_cursor()

    print "Writing {file} ...".format(file=output_file),
    sys.stdout.flush()  # display the part line to the user

    start=time.time()
    cur.execute(dedent(query), arguments)

    with open(output_file, 'w') as f:
        # write header row
        writerow(f, [d[0] for d in cur.description])
        # write the query results (cur is used as an iterator here to get all the rows one by one)
        writerows(f, cur)

    print "time taken: {dur:.2f}s".format(dur=time.time()-start)

def write_tab_file(output_file, headers, data, arguments={}):
    "Write a tab file using the headers and data supplied."
    output_file = make_file_path(output_file, arguments)

    print "Writing {file} ...".format(file=output_file),
    sys.stdout.flush()  # display the part line to the user

    start=time.time()

    with open(output_file, 'w') as f:
        writerow(f, headers)
        writerows(f, data)

    print "time taken: {dur:.2f}s".format(dur=time.time()-start)


def write_indexed_set_dat_file(output_file, set_name, query, arguments):
    """Write a .dat file defining an indexed set, based on the query provided.

    Note: the query should produce a table with index values in all columns except
    the last, and then set members for each index in the last column. (There should
    be multiple rows with the same values in the index columns.)"""

    output_file = make_file_path(output_file, arguments)
    print "Writing {file} ...".format(file=output_file),
    sys.stdout.flush()  # display the part line to the user

    start=time.time()

    cur = db_cursor()
    cur.execute(dedent(query), arguments)

    # build a dictionary grouping all values (last column) according to their index keys (earlier columns)
    data_dict = collections.defaultdict(list)
    for r in cur:
        # note: data_dict[(index vals)] is created as an empty list on first reference,
        # then gets data from all matching rows appended to it
        data_dict[tuple(r[:-1])].append(r[-1])

    # .dat file format based on p. 161 of http://ampl.com/BOOK/CHAPTERS/12-data.pdf
    with open(output_file, 'w') as f:
        f.writelines([
            'set {sn}[{idx}] := {items} ;\n'.format(
                sn=set_name,
                idx=', '.join(k),
                items=' '.join(v))
            for k, v in data_dict.iteritems()
        ])

    print "time taken: {dur:.2f}s".format(dur=time.time()-start)


def stringify(val):
    if val is None:
        out = '.'
    elif type(val) is str:
        out = val.replace('"', '""')
        if any(char in out for char in [' ', '\t', '"', "'"]):
            out = '"' + out + '"'
    else:
        out = str(val)
    return out

def writerow(f, row):
    f.write('\t'.join(stringify(c) for c in row) + '\n')

def writerows(f, rows):
    for r in rows:
        writerow(f, r)

def tuple_dict(keys, vals):
    "Create a tuple of dictionaries, one for each row in vals, using the specified keys."
    return tuple(zip(keys, row) for row in vals)
