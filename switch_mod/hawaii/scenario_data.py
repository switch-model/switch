import time, sys, collections, os
from textwrap import dedent
import psycopg2

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

    # catch obsolete arguments (otherwise they would be silently ignored)
    if 'ev_scen_id' in args:
        raise ValueError("ev_scen_id argument is no longer supported; use ev_scenario instead.")
        
    #########################
    # timescales
    
    write_table('periods.tab', """
        WITH period_length as (
            SELECT 
                CASE WHEN max(period) = min(period) 
                    THEN
                        -- one-period model; assume length = number of days provided
                        sum(ts_scale_to_period) / 365
                    ELSE
                        -- multi-period model; count number of years between periods
                        (max(period)-min(period)) / (count(distinct period)-1)
                END as length 
                FROM study_date WHERE time_sample = %(time_sample)s
        )
        SELECT period AS "INVESTMENT_PERIOD",
                period as period_start,
                round(period + length - 1)::int as period_end
                -- note: period_end is forced to nearest year before next period
                -- it would probably be better to count directly to some fractional year
                -- but that's not how the core switch code works
                -- (this code also converts period to an int, since postgresql started
                -- appending .0 to int-valued floats at some point around 9.4)
            FROM study_periods, period_length
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
    # lz_cost_multipliers, lz_ccs_distance_km, lz_dbid, 
    # existing_local_td, local_td_annual_cost_per_mw
    write_table('load_zones.tab', """
        SELECT load_zone as "LOAD_ZONE"
        FROM load_zone 
        WHERE load_zone in %(load_zones)s
    """, args)

    # NOTE: we don't provide lz_peak_loads.tab (sometimes used by local_td.py) in this version.

    # get system loads, scaled from the historical years to the model years
    # note: 'offset' is a keyword in postgresql, so we use double-quotes to specify the column name
    write_table('loads.tab', """
        SELECT 
            l.load_zone AS "LOAD_ZONE", 
            study_hour AS "TIMEPOINT",
            system_load * scale + "offset" AS lz_demand_mw
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
            FROM generator_info 
            WHERE fuel NOT IN (SELECT fuel_type FROM fuel_costs)
                AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
        UNION DISTINCT 
            SELECT aer_fuel_code AS "NON_FUEL_ENERGY_SOURCES" 
            FROM existing_plants 
            WHERE aer_fuel_code NOT IN (SELECT fuel_type FROM fuel_costs)
                AND load_zone in %(load_zones)s
                AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
                AND technology NOT IN %(exclude_technologies)s;
    """, args)

    # gather info on fuels
    write_table('fuels.tab', """
        SELECT DISTINCT c.fuel_type AS fuel, co2_intensity, 0.0 AS upstream_co2_intensity, rps_eligible
        FROM fuel_costs c JOIN energy_source_properties p on (p.energy_source = c.fuel_type)
        WHERE load_zone in %(load_zones)s AND fuel_scen_id=%(fuel_scen_id)s;
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
        inflator = 'power(1.0+%(inflation_rate)s, %(base_financial_year)s-c.year)'
    elif args['fuel_scen_id'].startswith('EIA'):
        inflator = 'power(1.0+%(inflation_rate)s, %(base_financial_year)s-2013)'
    else:
        inflator = '1.0'

    if args.get("use_simple_fuel_costs", False):
        # simple fuel markets with no bulk LNG expansion option
        # (use fuel_cost module)
        # TODO: get monthly fuel costs from Karl Jandoc spreadsheet
        if args.get("use_bulk_lng_for_simple_fuel_costs", False):
            lng_selector = "tier = 'bulk'"
        else:
            lng_selector = "tier != 'bulk'"
        write_table('fuel_cost.tab', """
            SELECT load_zone, fuel_type as fuel, period,
                price_mmbtu * {inflator} 
                + CASE WHEN (fuel_type='LNG' AND tier='bulk') THEN %(bulk_lng_fixed_cost)s ELSE 0.0 END
                    as fuel_cost
            FROM fuel_costs c JOIN study_periods p ON (c.year=p.period)
            WHERE load_zone in %(load_zones)s
                AND fuel_scen_id = %(fuel_scen_id)s
                AND p.time_sample = %(time_sample)s
                AND (fuel_type != 'LNG' OR {lng_selector})
            ORDER BY 1, 2, 3;
        """.format(inflator=inflator, lng_selector=lng_selector), args)
    else:
        # advanced fuel markets with LNG expansion options (used by forward-looking models)
        # (use fuel_markets module)
        write_table('regional_fuel_markets.tab', """
            SELECT DISTINCT concat('Hawaii_', fuel_type) AS regional_fuel_market, fuel_type AS fuel 
            FROM fuel_costs
            WHERE load_zone in %(load_zones)s AND fuel_scen_id = %(fuel_scen_id)s;
        """, args)

        write_table('fuel_supply_curves.tab', """
            SELECT concat('Hawaii_', fuel_type) as regional_fuel_market, fuel_type as fuel, 
                period, tier, price_mmbtu * {inflator} as unit_cost, max_avail_at_cost, fixed_cost
            FROM fuel_costs c JOIN study_periods p ON (c.year=p.period)
            WHERE load_zone in %(load_zones)s
                AND fuel_scen_id = %(fuel_scen_id)s
                AND p.time_sample = %(time_sample)s
            ORDER BY 1, 2, 4, 3;
        """.format(inflator=inflator), args)

        write_table('lz_to_regional_fuel_market.tab', """
            SELECT DISTINCT load_zone, concat('Hawaii_', fuel_type) AS regional_fuel_market 
            FROM fuel_costs 
            WHERE load_zone in %(load_zones)s AND fuel_scen_id = %(fuel_scen_id)s;
        """, args)

    # TODO: (when multi-island) add fuel_cost_adders for each zone


    #########################
    # gen_tech

    # TODO: provide reasonable retirement ages for existing plants (not 100+base age)
    # note: this zeroes out variable_o_m for renewable projects
    # TODO: find out where variable_o_m came from for renewable projects and put it in the right place
    # TODO: fix baseload flag in the database
    # TODO: account for multiple fuel sources for a single plant in the upstream database
    # and propagate that to this table.
    # TODO: make sure the heat rates are null for non-fuel projects in the upstream database, 
    # and remove the correction code from here
    # TODO: create heat_rate and fuel columns in the existing_plants_gen_tech table and simplify the query below.
    # TODO: add unit sizes for new projects to the generator_info table (new projects) from
    # Switch-Hawaii/data/HECO\ IRP\ Report/IRP-2013-App-K-Supply-Side-Resource-Assessment-062813-Filed.pdf
    # and then incorporate those into unit_sizes.tab below.
    # NOTE: this converts variable o&m from $/kWh to $/MWh
    # NOTE: we don't provide the following in this version:
    # g_min_build_capacity
    # g_ccs_capture_efficiency, g_ccs_energy_load,
    # g_storage_efficiency, g_store_to_release_ratio

    # NOTE: for all energy sources other than 'SUN' and 'WND' (i.e., all fuels),
    # We report the fuel as 'multiple' and then provide data in a multi-fuel table.
    # Some of these are actually single-fuel, but this approach is simpler than sorting
    # them out within each query, and it doesn't add any complexity to the model.
    
    # TODO: maybe replace "fuel IN ('SUN', 'WND', 'MSW')" with "fuel not in (SELECT fuel FROM fuel_cost)"
    # TODO: convert 'MSW' to a proper fuel, possibly with a negative cost, instead of ignoring it
            
    write_table('generator_info.tab', """
        SELECT  technology as generation_technology, 
                technology as g_dbid,
                unit_size as g_unit_size,
                max_age_years as g_max_age, 
                scheduled_outage_rate as g_scheduled_outage_rate, 
                forced_outage_rate as g_forced_outage_rate,
                intermittent as g_is_variable, 
                0 as g_is_baseload,
                0 as g_is_flexible_baseload, 
                0 as g_is_cogen,
                0 as g_competes_for_space, 
                variable_o_m * 1000.0 AS g_variable_o_m,
                CASE WHEN fuel IN ('SUN', 'WND', 'MSW') THEN fuel ELSE 'multiple' END AS g_energy_source,
                CASE WHEN fuel IN ('SUN', 'WND', 'MSW') THEN null ELSE 0.001*heat_rate END AS g_full_load_heat_rate
            FROM generator_info
            WHERE technology NOT IN %(exclude_technologies)s
                AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
        UNION SELECT
                g.technology as generation_technology, 
                g.technology as g_dbid, 
                avg(peak_mw) AS g_unit_size,    -- minimum block size for unit commitment
                g.max_age as g_max_age,         -- formerly g.max_age + 100 as g_max_age
                g.scheduled_outage_rate as g_scheduled_outage_rate, 
                g.forced_outage_rate as g_forced_outage_rate,
                g.variable as g_is_variable, 
                g.baseload as g_is_baseload,
                0 as g_is_flexible_baseload, 
                g.cogen as g_is_cogen,
                g.competes_for_space as g_competes_for_space, 
                CASE WHEN MIN(p.aer_fuel_code) IN ('SUN', 'WND') THEN 0.0 ELSE AVG(g.variable_o_m) * 1000.0 END 
                    AS g_variable_o_m,
                CASE WHEN MIN(p.aer_fuel_code) IN ('SUN', 'WND', 'MSW') THEN MIN(p.aer_fuel_code) ELSE 'multiple' END AS g_energy_source,
                CASE WHEN MIN(p.aer_fuel_code) IN ('SUN', 'WND', 'MSW') THEN null 
                    ELSE 0.001*SUM(p.heat_rate*p.avg_mw)/SUM(p.avg_mw) 
                    END AS g_full_load_heat_rate
            FROM existing_plants_gen_tech g JOIN existing_plants p USING (technology)
            WHERE p.load_zone in %(load_zones)s
                AND p.insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
                AND g.technology NOT IN %(exclude_technologies)s
            GROUP BY 1, 2, 4, 5, 6, 7, 8, 9, 10, 11
        ORDER BY 1;
    """, args)

    # This gets a list of all the fueled projects (listed as "multiple" energy sources above),
    # and lists them as accepting any equivalent or lighter fuel. (However, cogen plants and plants 
    # using fuels with rank 0 are not changed.) Fuels are also filtered against the list of fuels with
    # costs reported for the current scenario, so this can end up re-mapping one fuel in the database
    # (e.g., LSFO) to a similar fuel in the scenario (e.g., LSFO-Diesel-Blend), even if the original fuel
    # doesn't exist in the fuel_costs table. This can also be used to remap different names for the same
    # fuel (e.g., "COL" in the plant definition and "Coal" in the fuel_costs table, both with the same
    # fuel_rank).
    write_indexed_set_dat_file('gen_multiple_fuels.dat', 'G_MULTI_FUELS', """
        WITH all_techs AS (
            SELECT
                technology as generation_technology,
                fuel as orig_fuel,
                0 as cogen
            FROM generator_info c
            WHERE min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
                AND technology NOT IN %(exclude_technologies)s
            UNION DISTINCT
            SELECT DISTINCT
                g.technology as generation_technology, 
                p.aer_fuel_code as orig_fuel,
                g.cogen
            FROM existing_plants_gen_tech g JOIN existing_plants p USING (technology)
            WHERE p.load_zone in %(load_zones)s
                AND p.insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
                AND g.technology NOT IN %(exclude_technologies)s
        ), all_fueled_techs AS (
            SELECT * from all_techs WHERE orig_fuel NOT IN ('SUN', 'WND', 'MSW')
        )
        SELECT DISTINCT generation_technology, b.energy_source as fuel
        FROM all_fueled_techs t 
            JOIN energy_source_properties a ON a.energy_source = t.orig_fuel
            JOIN energy_source_properties b ON b.fuel_rank >= a.fuel_rank AND
                (a.fuel_rank > 0 OR a.energy_source = b.energy_source)    -- 0-rank can't change fuels
            WHERE b.energy_source IN (SELECT fuel_type FROM fuel_costs WHERE fuel_scen_id = %(fuel_scen_id)s);
    """, args)


    # TODO: write code in project.unitcommit.commit to load part-load heat rates
    # TODO: get part-load heat rates for new plant technologies and report them in 
    # project.unit.commit instead of full-load heat rates here.
    # TODO: report part-load heat rates for existing plants in project.unitcommit.commit
    # (maybe on a project-specific basis instead of generalized for each technology)
    # NOTE: we divide heat rate by 1000 to convert from Btu/kWh to MBtu/MWh


    if args.get('wind_capital_cost_escalator', 0.0) or args.get('pv_capital_cost_escalator', 0.0):
        # user supplied a non-zero escalator
        raise ValueError(
            'wind_capital_cost_escalator and pv_capital_cost_escalator arguments are '
            'no longer supported by scenario_data.write_tables(); '
            'assign variable costs in the generator_costs_by_year table instead.'
        )

    # note: this table can only hold costs for technologies with future build years,
    # so costs for existing technologies are specified in proj_build_costs.tab
    # NOTE: costs in this version of switch are expressed in $/MW, $/MW-year, etc., not per kW.
    # TODO: store generator costs base year in a table, not an argument
    write_table('gen_new_build_costs.tab', """
        SELECT  
            i.technology as generation_technology, 
            period AS investment_period,
            capital_cost_per_kw * 1000.0 
                * power(1.0+%(inflation_rate)s, %(base_financial_year)s-%(generator_costs_base_year)s)
                AS g_overnight_cost, 
            fixed_o_m*1000.0 AS g_fixed_o_m
        FROM generator_info i
            JOIN generator_costs_by_year c USING (technology)
            JOIN study_periods p ON p.period = c.year
        WHERE i.technology NOT IN %(exclude_technologies)s
            AND time_sample = %(time_sample)s
            AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
        ORDER BY 1, 2;
    """, args)



    #########################
    # project.build

    # TODO: find connection costs and add them to the switch database (currently all zeroes)
    # TODO: find out why existing wind and solar projects have non-zero variable O&M in the switch 
    # database, and zero them out there instead of here.
    # NOTE: if a generator technology in the generator_info table doesn't have a match in the project
    # table, we use the generic_cost_per_kw from the generator_info table. If that is also null,
    # then the connection cost will be given whatever default value is specified in the SWITCH code
    # (probably zero).
    # If individual projects are identified in the project table, we use those;
    # then we also add generic projects in each load_zone for any technologies that are not
    # marked as resource_limited in generator_info.
    # NOTE: if a technology ever appears in the project table, then
    # every possible project of that type should be recorded in that table. 
    # Technologies that don't appear in this table are deemed generic projects,
    # which can be added once in each load zone.
    # NOTE: we don't provide the following, because they are specified in generator_info.tab instead:
    # proj_full_load_heat_rate, proj_forced_outage_rate, proj_scheduled_outage_rate
    # (the project-specific data would only be for otherwise-similar projects that have degraded and 
    # now have different heat rates)
    # NOTE: variable costs for existing plants could alternatively be added to the generator_info.tab 
    # table (aggregated by technology instead of project). That is where we put the variable costs 
    # for new projects.
    # NOTE: we convert costs from $/kWh to $/MWh

    if args.get('connect_cost_per_mw_km', 0):
        print(
            "WARNING: ignoring connect_cost_per_mw_km specified in arguments; "
            "using project.connect_cost_per_mw instead."
        )
    write_table('project_info.tab', """
            -- make a list of all projects with detailed definitions (and gather the available data)
            DROP TABLE IF EXISTS t_specific_projects;
            CREATE TEMPORARY TABLE t_specific_projects AS
                SELECT 
                    concat_ws('_', load_zone, technology, site, orientation) AS "PROJECT",
                    load_zone as proj_load_zone,
                    technology AS proj_gen_tech,
                    connect_cost_per_mw AS proj_connect_cost_per_mw,
                    max_capacity as proj_capacity_limit_mw
                FROM project;

            -- make a list of generic projects (for which no detailed definitions are available)
            DROP TABLE IF EXISTS t_generic_projects;
            CREATE TEMPORARY TABLE t_generic_projects AS
                SELECT 
                    concat_ws('_', load_zone, technology) AS "PROJECT",
                    load_zone as proj_load_zone,
                    technology AS proj_gen_tech,
                    cast(null as float) AS proj_connect_cost_per_mw,
                    cast(null as float) AS proj_capacity_limit_mw
                FROM generator_info g
                    CROSS JOIN (SELECT DISTINCT load_zone FROM system_load) z
                WHERE g.technology NOT IN (SELECT proj_gen_tech FROM t_specific_projects);
        
            -- merge the specific and generic projects
            DROP TABLE IF EXISTS t_all_projects;
            CREATE TEMPORARY TABLE t_all_projects AS
            SELECT * FROM t_specific_projects UNION SELECT * from t_generic_projects;
        
            -- collect extra data from the generator_info table and filter out disallowed projects
            SELECT
                a."PROJECT", 
                null as proj_dbid,
                a.proj_gen_tech, 
                a.proj_load_zone, 
                COALESCE(a.proj_connect_cost_per_mw, 1000.0*g.connect_cost_per_kw_generic, 0.0) AS proj_connect_cost_per_mw,
                a.proj_capacity_limit_mw,
                cast(null as float) AS proj_variable_om    -- this is supplied in generator_info.tab for new projects
            FROM t_all_projects a JOIN generator_info g on g.technology=a.proj_gen_tech
            WHERE a.proj_load_zone IN %(load_zones)s
                AND g.min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
                AND g.technology NOT IN %(exclude_technologies)s
            UNION
            -- collect data on existing projects
            SELECT DISTINCT 
                project_id AS "PROJECT",
                null AS dbid,
                technology AS proj_gen_tech, 
                load_zone AS proj_load_zone, 
                0.0 AS proj_connect_cost_per_mw,
                cast(null as float) AS proj_capacity_limit_mw,
                sum(CASE WHEN aer_fuel_code IN ('SUN', 'WND') THEN 0.0 ELSE variable_o_m END * 1000.0 * avg_mw)
                   / sum(avg_mw) AS proj_variable_om
            FROM existing_plants
            WHERE load_zone IN %(load_zones)s
                AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
                AND technology NOT IN %(exclude_technologies)s
            GROUP BY 1, 2, 3, 4, 5, 6
            ORDER BY 4, 3, 1;
    """, args)


    write_table('proj_existing_builds.tab', """
        SELECT project_id AS "PROJECT", 
                insvyear AS build_year, 
                sum(peak_mw) as proj_existing_cap
        FROM existing_plants
        WHERE load_zone in %(load_zones)s
            AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
            AND technology NOT IN %(exclude_technologies)s
        GROUP BY 1, 2;
    """, args)

    # note: we have to put cost data for existing projects in proj_build_costs.tab
    # because gen_new_build_costs only covers future investment periods.
    # NOTE: these costs must be expressed per MW, not per kW
    write_table('proj_build_costs.tab', """
        SELECT project_id AS "PROJECT", 
                insvyear AS build_year, 
                sum(overnight_cost * 1000.0 * peak_mw) / sum(peak_mw) as proj_overnight_cost,
                sum(fixed_o_m * 1000.0 * peak_mw) / sum(peak_mw) as proj_fixed_om
        FROM existing_plants
        WHERE load_zone in %(load_zones)s
            AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
            AND technology NOT IN %(exclude_technologies)s
        GROUP BY 1, 2;
    """, args)


    #########################
    # project.dispatch

    # skip this step if the user specifies "skip_cf" in the arguments (to speed up execution)
    if args.get("skip_cf", False):
        print "SKIPPING variable_capacity_factors.tab"
    else:
        write_table('variable_capacity_factors.tab', """
            SELECT 
                concat_ws('_', load_zone, technology, site, orientation) as "PROJECT",
                study_hour as timepoint,
                cap_factor as proj_max_capacity_factor
            FROM generator_info g 
                JOIN project p USING (technology)
                JOIN cap_factor c USING (project_id)
                JOIN study_hour h using (date_time)
            WHERE load_zone in %(load_zones)s and time_sample = %(time_sample)s
                AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
                AND g.technology NOT IN %(exclude_technologies)s
            UNION 
            SELECT 
                c.project_id as "PROJECT", 
                study_hour as timepoint, 
                cap_factor as proj_max_capacity_factor
            FROM existing_plants p JOIN existing_plants_cap_factor c USING (project_id)
                JOIN study_hour h USING (date_time)
            WHERE h.date_time = c.date_time 
                AND c.load_zone in %(load_zones)s
                AND h.time_sample = %(time_sample)s
                AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
                AND p.technology NOT IN %(exclude_technologies)s
            ORDER BY 1, 2
        """, args)


    #########################
    # project.discrete_build

    # include this module, but it doesn't need any additional data.


    #########################
    # project.unitcommit.commit

    # minimum commitment levels for existing projects

    # TODO: set proj_max_commit_fraction based on maintenance outage schedules
    # (needed for comparing switch marginal costs to FERC 715 data in 2007-08)

    # TODO: eventually add code to only provide these values for the timepoints before 
    # each project retires (providing them after retirement will cause an error).

    write_table('proj_commit_bounds_timeseries.tab', """
        SELECT * FROM (
            SELECT project_id as "PROJECT",
                study_hour AS "TIMEPOINT",
                case when %(enable_must_run)s = 1 and must_run = 1 then 1.0 else null end as proj_min_commit_fraction, 
                null as proj_max_commit_fraction,
                null as proj_min_load_fraction
            FROM existing_plants, study_hour
            WHERE load_zone in %(load_zones)s
                AND time_sample = %(time_sample)s
                AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
                AND technology NOT IN %(exclude_technologies)s
        ) AS the_data
        WHERE proj_min_commit_fraction IS NOT NULL OR proj_max_commit_fraction IS NOT NULL OR proj_min_load_fraction IS NOT NULL;
    """, args)

    # TODO: get minimum loads for new and existing power plants and then activate the query below

    # write_table('gen_unit_commit.tab', """
    #     SELECT 
    #         technology AS generation_technology, 
    #         min_load / unit_size AS g_min_load_fraction, 
    #         null AS g_startup_fuel,
    #         null AS g_startup_om
    #     FROM generator_info
    #     UNION SELECT DISTINCT
    #         technology AS generation_technology, 
    #         sum(min_load) / sum(peak_mw) AS g_min_load_fraction, 
    #         null AS g_startup_fuel,
    #         null AS g_startup_om
    #     FROM existing_plants
    #     WHERE load_zone in %(load_zones)s
    #        AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    #        AND technology NOT IN %(exclude_technologies)s
    #     GROUP BY 1
    #     ORDER by 1;
    # """, args)


    #########################
    # project.unitcommit.fuel_use

    # TODO: heat rate curves for new projects
    # TODO: heat rate curves for existing plants

    #########################
    # project.unitcommit.discrete

    # include this module, but it doesn't need any additional data.


    # TODO: write reserves code
    # TODO: create data files showing reserve rules


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
    # TODO: put these data in a database and write a .tab file instead
    bat_years = 'BATTERY_CAPITAL_COST_YEARS'
    bat_cost = 'battery_capital_cost_per_mwh_capacity_by_year'
    write_dat_file(
        'batteries.dat',
        sorted([k for k in args if k.startswith('battery_') and k not in [bat_years, bat_cost]]),
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
    # EV annual energy consumption
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
