#!/usr/bin/python

# based on "Switch-Hawaii/ampl/working oahu version/get_scenario_data.py"

from write_pyomo_table import write_table

# NOTE: ANSI SQL specifies single quotes for literal strings, and postgres conforms
# to this, so all the queries below should use single quotes around strings.

###########################
# Scenario Definition

# particular settings chosen for this case
# (these will be passed as arguments when the queries are run)
args = dict(
    load_scen_id = "med",        # "Moved by Passion"
    fuel_scen_id = 3,            # 1=low, 2=high, 3=reference
    time_sample = "2007",       # use a sample of dates in 2007-08 (will eventually be all of them)
    load_zones = ('Oahu',),       # subset of load zones to model
    # TODO: integrate the connect length into switch financial calculations,
    # rather than assigning a cost per MW-km here.
    connect_cost_per_mw_km = 1000000,
    base_financial_year = 2015,
    interest_rate = 0.06,
    discount_rate = 0.03
)


#########################
# timescales

write_table('periods.tab', """
    SELECT period AS "INVESTMENT_PERIOD",
            period as period_start,
            period + (
                SELECT (max(period)-min(period)) / (count(distinct period)-1) as length 
                    FROM study_periods WHERE time_sample = %(time_sample)s
                ) - 1 as period_end
        FROM study_periods
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
                'YYYY-MM-DD-HH24:MI') as timepoint_label,
            h.study_date as timeseries 
        FROM study_hour h JOIN study_date d USING (study_date, time_sample)
        WHERE h.time_sample = %(time_sample)s
        ORDER BY period, 3, 2;
""", args)

#########################
# financials

# this just uses a dat file, not a table (and the values are not in a database for now)
with open('financials.dat', 'w') as f:
    f.writelines([
        'param ' + name + ' := ' + str(args[name]) + ';\n' 
        for name in ['base_financial_year', 'interest_rate', 'discount_rate']
    ])

#########################
# load_zones

write_table('load_zones.tab', """
    SELECT load_zone as "LOAD_ZONE",
        '.' as cost_multipliers,
        '.' as ccs_distance_km,
        load_zone as dbid
    FROM load_zone 
    WHERE load_zone in %(load_zones)s
""", args)

# TODO: drop this table and calculate peak demand internally
write_table('lz_peak_loads.tab', """
    SELECT load_zone as "LOAD_ZONE",
        period as "PERIOD",
        0.0 as peak_demand_mw
    FROM load_zone, study_periods
    WHERE load_zone in %(load_zones)s
    AND time_sample = %(time_sample)s
""", args)



if args['time_sample'] == '2007':
    # don't rescale loads for historical scenario
    # TODO: add scale factors to system_load_scale for 2007 and 2008, so we don't need separate queries here.
    write_table('loads.tab', """
        SELECT l.load_zone AS "LOAD_ZONE", study_hour AS "TIMEPOINT",
                system_load AS demand_mw
            FROM study_date d 
                JOIN study_hour h USING (time_sample, study_date)
                JOIN system_load l USING (date_time)
            WHERE l.load_zone in %(load_zones)s
                AND d.time_sample = %(time_sample)s;
    """, args)
else:
    # scale for the future
    # note: 'offset' is a keyword in postgresql, so we use double-quotes to specify the column name
    write_table('loads.tab', """
        SELECT l.load_zone AS "LOAD_ZONE", study_hour AS "TIMEPOINT",
                system_load * scale + "offset" AS demand_mw
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
        FROM generator_costs 
        WHERE fuel NOT IN (SELECT fuel_type FROM fuel_costs)
            AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    UNION DISTINCT 
        SELECT aer_fuel_code AS "NON_FUEL_ENERGY_SOURCES" 
        FROM existing_plants 
        WHERE aer_fuel_code NOT IN (SELECT fuel_type FROM fuel_costs)
            AND load_zone in %(load_zones)s
            AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s);
""", args)

# TODO: tabulate CO2 intensity of fuels
write_table('fuels.tab', """
    SELECT DISTINCT fuel_type AS fuel, 0.0 AS co2_intensity, 0.0 AS upstream_co2_intensity
    FROM fuel_costs;
""", args)
        
#########################
# fuel_markets

# TODO: get monthly fuel costs from Karl Jandoc spreadsheet

write_table('fuel_cost.tab', """
    SELECT load_zone, fuel_type as fuel, period, price_mmbtu as fuel_cost 
        FROM fuel_costs c JOIN study_periods p ON (c.year=p.period)
        WHERE load_zone in %(load_zones)s 
            AND fuel_scen_id = %(fuel_scen_id)s
            AND p.time_sample = %(time_sample)s;
""", args)


#########################
# gen_tech

# TODO: provide reasonable retirement ages for existing plants (not 100+base age)
# TODO: rename/drop the DistPV_peak and DistPV_flat technologies in the generator_costs table

write_table('generator_info.tab', """
    SELECT  replace(technology,'DistPV_peak', 'DistPV') as generation_technology, 
            replace(technology,'DistPV_peak', 'DistPV')  as g_dbid,
            max_age_years as g_max_age, 
            '.' as g_min_build_capacity,
            scheduled_outage_rate as g_scheduled_outage_rate, 
            forced_outage_rate as g_forced_outage_rate,
            intermittent as g_is_variable, 
            0 as g_is_baseload,
            0 as g_is_flexible_baseload, 
            1 as g_is_dispatchable, 
            0 as g_is_cogen,
            0 as g_competes_for_space, 
            variable_o_m as g_variable_o_m
        FROM generator_costs
        WHERE technology NOT IN ('DistPV_flat')
            AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
        UNION SELECT
                technology as generation_technology, 
                technology as g_dbid, 
                max_age + 100 as g_max_age, 
                '.' as g_min_build_capacity,
                scheduled_outage_rate as g_scheduled_outage_rate, 
                forced_outage_rate as g_forced_outage_rate,
                variable as g_is_variable, 
                baseload as g_is_baseload,
                flexible_baseload as g_is_flexible_baseload, 
                dispatchable as g_is_dispatchable, 
                cogen as g_is_cogen,
                competes_for_space as g_competes_for_space, 
                variable_o_m as g_variable_o_m
            FROM existing_plants_gen_tech
            WHERE technology IN 
                (SELECT technology FROM existing_plants WHERE load_zone in %(load_zones)s
                    AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s))
        ORDER BY 1;
""", args)

# not providing ccs_info

# TODO: account for multiple fuel sources for a single plant in the upstream database
# and propagate that to this table.
write_table('generator_energy_sources.tab', """
    SELECT DISTINCT
        technology as generation_technology, 
        fuel as energy_source
    FROM generator_costs
    WHERE min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    UNION DISTINCT SELECT DISTINCT
            technology as generation_technology, 
            aer_fuel_code as energy_source
        FROM existing_plants
        WHERE load_zone in %(load_zones)s
            AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    ORDER BY 1;
""", args)

# note: this table can only hold costs for technologies with future build years,
# so costs for existing technologies are specified in project_specific_costs.tab
write_table('gen_new_build_costs.tab', """
    SELECT  
        replace(technology,'DistPV_peak', 'DistPV') as generation_technology, 
        period AS investment_period,
        capital_cost_per_kw AS g_overnight_cost, 
        fixed_o_m AS g_fixed_o_m
    FROM generator_costs, study_periods
    WHERE technology NOT IN ('DistPV_flat')
        AND time_sample = %(time_sample)s
        AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    ORDER BY 1, 2;
""", args)
    # UNION
    # SELECT technology AS generation_technology, 
    #         insvyear AS investment_period, 
    #         sum(overnight_cost * peak_mw) / sum(peak_mw) as g_overnight_cost,
    #         sum(fixed_o_m * peak_mw) / sum(peak_mw) as g_fixed_o_m
    # FROM existing_plants
    # WHERE load_zone in %(load_zones)s
    #     AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    # GROUP BY 1, 2


# not providing storage_info

# list sizes of units for projects that need unit-sized construction and dispatch

# TODO: add unit sizes for new projects to the generator_costs table (new projects) from
# Switch-Hawaii/data/HECO\ IRP\ Report/IRP-2013-App-K-Supply-Side-Resource-Assessment-062813-Filed.pdf
# and then incorporate those into unit_sizes.tab below.

write_table('unit_sizes.tab', """
    SELECT DISTINCT
        technology as generation_technology, 
        peak_mw as g_unit_size
    FROM existing_plants
    WHERE load_zone in %(load_zones)s
        AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    ORDER by 1;
""", args)

# TODO: write code in project.unitcommit.commit to load part-load heat rates
# TODO: get part-load heat rates for new plant technologies and report them in 
# project.unit.commit instead of full-load heat rates here.
# TODO: report part-load heat rates for existing plants in project.unitcommit.commit
# (maybe on a project-specific basis instead of generalized for each technology)
write_table('gen_heat_rates.tab', """
    SELECT DISTINCT
        technology AS generation_technology, 
        heat_rate AS full_load_heat_rate
    FROM generator_costs
    WHERE fuel IN (SELECT fuel_type FROM fuel_costs)
        AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    UNION SELECT
        technology AS generation_technology, 
        round(sum(heat_rate*avg_mw)/sum(avg_mw)) AS full_load_heat_rate
    FROM existing_plants
    WHERE load_zone in %(load_zones)s
        AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
        AND aer_fuel_code IN (SELECT fuel_type FROM fuel_costs)
    GROUP BY 1
    ORDER by 1;
""", args)

#########################
# project.build

# TODO: find connection costs and add them to the switch database (currently all zeroes)
write_table('all_projects.tab', """
    SELECT concat_ws('_', load_zone, technology, site, orientation) as "PROJECT",
        '.' as proj_dbid,
        technology as proj_gen_tech, 
        load_zone as proj_load_zone, 
        %(connect_cost_per_mw_km)s*connect_length_km + 1000*connect_cost_per_kw as proj_connect_cost_per_mw
        FROM connect_cost JOIN generator_costs using (technology)
        WHERE load_zone IN %(load_zones)s
            AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
        UNION SELECT DISTINCT 
            project_id AS "PROJECT",
            '.' as dbid,
            technology as proj_gen_tech, 
            load_zone as proj_load_zone, 
            0.0 as proj_connect_cost_per_mw
            FROM existing_plants
            WHERE load_zone IN %(load_zones)s
                AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
        ORDER BY 3, 2, 1;
""", args)

# note, this is really more like 'existing_project_buildyears.tab'.
write_table('existing_projects.tab', """
    SELECT project_id AS "PROJECT", 
            insvyear AS build_year, 
            sum(peak_mw) as proj_existing_cap
    FROM existing_plants
    WHERE load_zone in %(load_zones)s
        AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    GROUP BY 1, 2;
""", args)

write_table('cap_limited_projects.tab', """
    SELECT 
        concat_ws('_', load_zone, technology, site, orientation) as "PROJECT",
        max_capacity as proj_capacity_limit_mw
    FROM max_capacity JOIN generator_costs USING (technology)
    WHERE load_zone in %(load_zones)s
        AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
""", args)

# note: we don't supply proj_heat_rate.tab because that's focused
# on otherwise similar projects that now have different heat rates (degraded)

# note: we have to put cost data for existing projects in project_specific_costs.tab
# because gen_new_build_costs only covers future investment periods.
write_table('project_specific_costs.tab', """
    SELECT project_id AS "PROJECT", 
            insvyear AS build_year, 
            sum(overnight_cost * peak_mw) / sum(peak_mw) as proj_overnight_cost,
            sum(fixed_o_m * peak_mw) / sum(peak_mw) as proj_fixed_om
    FROM existing_plants
    WHERE load_zone in %(load_zones)s
        AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    GROUP BY 1, 2;
""", args)


#########################
# project.dispatch

write_table('variable_capacity_factors.tab', """
    SELECT 
        concat_ws('_', load_zone, technology, site, orientation) as "PROJECT",
        study_hour as timepoint,
        cap_factor as prj_capacity_factor
    FROM generator_costs g JOIN cap_factor c USING (technology)
        JOIN study_hour h using (date_time)
    WHERE load_zone in %(load_zones)s
        AND min_vintage_year <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    UNION SELECT c.project_id as "PROJECT", study_hour as timepoint, cap_factor as prj_capacity_factor
    FROM existing_plants p JOIN existing_plants_cap_factor c USING (project_id)
        JOIN study_hour h USING (date_time)
    WHERE h.date_time = c.date_time 
        AND c.load_zone in %(load_zones)s
        AND h.time_sample = %(time_sample)s
        AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    ORDER BY 1, 2
""", args)

# note: these could alternatively be added to the generator_info.tab table
# (aggregated by technology instead of project)
# That is where we put the variable costs for new projects.
write_table('proj_variable_costs.tab', """
    SELECT project_id AS "PROJECT", 
            sum(variable_o_m * avg_mw) / sum(avg_mw) as proj_variable_om
    FROM existing_plants
    WHERE load_zone in %(load_zones)s
        AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
    GROUP BY 1;
""", args)


#########################
# project.discrete_build

# include this module, but it doesn't need any additional data.


#########################
# project.unitcommit.commit

# TODO: heat rate curves for new projects
# TODO: heat rate curves for existing plants

# TODO: get minimum loads for new and existing power plants and then activate the query below

# write_table('gen_unit_commit.tab', """
#     SELECT 
#         technology AS generation_technology, 
#         min_load / unit_size AS g_min_load_fraction, 
#         '.' AS g_startup_fuel,
#         '.' AS g_startup_om
#     FROM generator_costs
#     UNION SELECT DISTINCT
#         technology AS generation_technology, 
#         sum(min_load) / sum(peak_mw) AS g_min_load_fraction, 
#         '.' AS g_startup_fuel,
#         '.' AS g_startup_om
#     FROM existing_plants
#     WHERE load_zone in %(load_zones)s
#        AND insvyear <= (SELECT MAX(period) FROM study_periods WHERE time_sample = %(time_sample)s)
#     GROUP BY 1
#     ORDER by 1;
# """, args)


# TODO: get minimum and maximum commitment levels for existing projects
# (i.e., identify plants that are forced on and find maintenance outage schedules
# for all plants) and then write queries to create proj_commit_bounds_timeseries.tab.

# proj_commit_bounds_timeseries.tab
#     PROJECT, TIMEPOINT, proj_min_commit_fraction, proj_max_commit_fraction,
#     proj_min_load_fraction


#########################
# project.unitcommit.discrete

# include this module, but it doesn't need any additional data.


# TODO: write reserves code
# TODO: create data files showing reserve rules


#########################
# project.local_td
# --- Not used ---


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


