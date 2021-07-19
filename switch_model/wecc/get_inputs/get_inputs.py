"""
Script to retrieve data inputs for the Switch WECC model from the database.
Data is formatted into corresponding .csv files.

Note: previously we used an SSH tunnel to connect to the database.
That code was removed however it can still be found at this commit
273be083c743e0527c2753356a101c479fe053e8 on the REAM-lab repo.
(https://github.com/REAM-lab/switch/tree/273be083c743e0527c2753356a101c479fe053e8)
"""

# Standard packages
import warnings
from typing import Iterable, List

# Switch packages
from switch_model.wecc.utilities import connect
from switch_model.version import __version__

def write_csv_from_query(cursor, fname: str, headers: List[str], query: str):
    """Create CSV file from cursor."""
    print(f"\t{fname}.csv... ", flush=True)
    cursor.execute(query)
    data = cursor.fetchall()
    write_csv(data, fname, headers, log=False)
    if not data:
        warnings.warn(f"File {fname} is empty.")


def write_csv(data: Iterable[List], fname, headers: List[str], log=True):
    """Create CSV file from Iterable."""
    if log:
        print(f"\t{fname}.csv... ", flush=True)
    with open(fname + ".csv", "w") as f:
        f.write(",".join(headers) + "\n")
        for row in data:
            # Replace None values with dots for Pyomo. Also turn all datatypes into strings
            row_as_clean_strings = [
                "." if element is None else str(element) for element in row
            ]
            f.write(
                ",".join(row_as_clean_strings) + "\n"
            )  # concatenates "line" separated by commas, and appends \n


# List of modules that is used to generate modules.txt
modules = [
    # Core modules
    "switch_model",
    "switch_model.timescales",
    "switch_model.financials",
    "switch_model.balancing.load_zones",
    "switch_model.energy_sources.properties",
    "switch_model.generators.core.build",
    "switch_model.generators.core.dispatch",
    "switch_model.reporting",
    # Custom Modules
    "switch_model.generators.core.no_commit",
    "switch_model.generators.extensions.hydro_simple",
    "switch_model.generators.extensions.storage",
    "switch_model.energy_sources.fuel_costs.markets",
    "switch_model.transmission.transport.build",
    "switch_model.transmission.transport.dispatch",
    "switch_model.policies.carbon_policies",
    "switch_model.policies.rps_unbundled",
    "switch_model.policies.min_per_tech",  # Always include since it provides useful outputs even when unused
    # "switch_model.reporting.basic_exports_wecc",
]


def query_db(full_config, skip_cf):
    config = full_config["get_inputs"]
    scenario_id = config["scenario_id"]

    # Connect to database
    db_conn = connect()
    db_cursor = db_conn.cursor()

    print("Copying data from the database to the input files...")

    scenario_params = [
        "name",
        "description",
        "study_timeframe_id",
        "time_sample_id",
        "demand_scenario_id",
        "fuel_simple_price_scenario_id",
        "generation_plant_scenario_id",
        "generation_plant_cost_scenario_id",
        "generation_plant_existing_and_planned_scenario_id",
        "hydro_simple_scenario_id",
        "carbon_cap_scenario_id",
        "supply_curves_scenario_id",
        "regional_fuel_market_scenario_id",
        "rps_scenario_id",
        "enable_dr",
        "enable_ev",
        "transmission_base_capital_cost_scenario_id",
        "ca_policies_scenario_id",
        "enable_planning_reserves",
        "generation_plant_technologies_scenario_id",
        "variable_o_m_cost_scenario_id"
    ]

    db_cursor.execute(
        f"""SELECT
            {",".join(scenario_params)}
        FROM switch.scenario
        WHERE scenario_id = {scenario_id};"""
    )
    s_details = list(db_cursor.fetchone())

    # Allow overriding from config
    for i, param_name in enumerate(scenario_params):
        if param_name in config:
            s_details[i] = config[param_name]

    name = s_details[0]
    description = s_details[1]
    study_timeframe_id = s_details[2]
    time_sample_id = s_details[3]
    demand_scenario_id = s_details[4]
    fuel_simple_price_scenario_id = s_details[5]
    generation_plant_scenario_id = s_details[6]
    generation_plant_cost_scenario_id = s_details[7]
    generation_plant_existing_and_planned_scenario_id = s_details[8]
    hydro_simple_scenario_id = s_details[9]
    carbon_cap_scenario_id = s_details[10]
    supply_curves_scenario_id = s_details[11]
    regional_fuel_market_scenario_id = s_details[12]
    rps_scenario_id = s_details[13]
    enable_dr = s_details[14]
    enable_ev = s_details[15]
    transmission_base_capital_cost_scenario_id = s_details[16]
    ca_policies_scenario_id = s_details[17]
    enable_planning_reserves = s_details[18]
    generation_plant_technologies_scenario_id =s_details[19]
    variable_o_m_cost_scenario_id = s_details[20]

    print(f"Scenario: {scenario_id}: {name}.")

    # Write general scenario parameters into a documentation file
    print("\tscenario_params.txt...")
    colnames = [desc[0] for desc in db_cursor.description]
    with open("scenario_params.txt", "w") as f:
        f.write(f"Scenario id: {scenario_id}\n")
        f.write(f"Scenario name: {name}\n")
        f.write(f"Scenario notes: {description}\n")
        for i, col in enumerate(colnames):
            f.write(f"{col}: {s_details[i]}\n")

    ########################################################
    # Which input specification are we writing against?
    print("\tswitch_inputs_version.txt...")
    with open("switch_inputs_version.txt", "w") as f:
        f.write(f"{__version__}\n")

    ########################################################
    # TIMESCALES

    # periods.csv
    write_csv_from_query(
        db_cursor,
        "periods",
        ["INVESTMENT_PERIOD", "period_start", "period_end"],
        f"""
        select
          label  as label, --This is to fix build year problem
          start_year as period_start,
          end_year as period_end
        from
          switch.period
        where
          study_timeframe_id = {study_timeframe_id}
        order by
          1;
        """,
    )

    # timeseries.csv
    timeseries_id_select = "date_part('year', first_timepoint_utc)|| '_' || replace(sampled_timeseries.name, ' ', '_') as timeseries"
    write_csv_from_query(
        db_cursor,
        "timeseries",
        [
            "TIMESERIES",
            "ts_period",
            "ts_duration_of_tp",
            "ts_num_tps",
            "ts_scale_to_period",
        ],
        # TODO what's happening here
        f"""
            select
              date_part('year', first_timepoint_utc)|| '_' || replace(
                sampled_timeseries.name, ' ', '_'
              ) as timeseries,
              t.label  as ts_period,
              hours_per_tp as ts_duration_of_tp,
              num_timepoints as ts_num_tps,
              scaling_to_period as ts_scale_to_period
            from
              switch.sampled_timeseries
              join switch.period as t using(period_id, study_timeframe_id)
            where
              sampled_timeseries.time_sample_id = {time_sample_id}
              and sampled_timeseries.study_timeframe_id = {study_timeframe_id}
            order by
                label desc,
                timeseries asc;""",
    )

    # timepoints.csv
    write_csv_from_query(
        db_cursor,
        "timepoints",
        ["timepoint_id", "timestamp", "timeseries"],
        f"""
            select
              raw_timepoint_id as timepoint_id,
              to_char(timestamp_utc, 'YYYYMMDDHH24') as timestamp,
              date_part('year', first_timepoint_utc)|| '_' || replace(
                sampled_timeseries.name, ' ', '_'
              ) as timeseries
            from
              switch.sampled_timepoint as t
              join switch.sampled_timeseries using(
                sampled_timeseries_id, study_timeframe_id
              )
            where
              t.time_sample_id = {time_sample_id}
              and t.study_timeframe_id = {study_timeframe_id}
            order by
              1;
            """,
    )

    ########################################################
    # LOAD ZONES

    write_csv_from_query(
        db_cursor,
        "load_zones",
        ["LOAD_ZONE", "zone_ccs_distance_km", "zone_dbid"],
        """
        SELECT 
            name, 
            ccs_distance_km as zone_ccs_distance_km, 
            load_zone_id as zone_dbid 
        FROM switch.load_zone  
        WHERE name != '_ALL_ZONES'
        ORDER BY 1;
        """,
    )

    # loads.csv
    write_csv_from_query(
        db_cursor,
        "loads",
        ["LOAD_ZONE", "TIMEPOINT", "zone_demand_mw"],
        f"""
            select load_zone_name, t.raw_timepoint_id as timepoint,
                CASE WHEN demand_mw < 0 THEN 0 ELSE demand_mw END as zone_demand_mw
            from sampled_timepoint as t
                join demand_timeseries as d using(raw_timepoint_id)
            where t.time_sample_id={time_sample_id}
                and demand_scenario_id={demand_scenario_id}
            order by 1,2;
            """,
    )

    ########################################################
    # BALANCING AREAS [Pending zone_coincident_peak_demand.csv]

    # balancing_areas.csv
    write_csv_from_query(
        db_cursor,
        "balancing_areas",
        [
            "BALANCING_AREAS",
            "quickstart_res_load_frac",
            "quickstart_res_wind_frac",
            "quickstart_res_solar_frac",
            "spinning_res_load_frac",
            "spinning_res_wind_frac",
            "spinning_res_solar_frac",
        ],
        """
        SELECT
            balancing_area,
            quickstart_res_load_frac,
            quickstart_res_wind_frac,
            quickstart_res_solar_frac,
            spinning_res_load_frac,
            spinning_res_wind_frac,
            spinning_res_solar_frac
        FROM switch.balancing_areas;""",
    )

    # zone_balancing_areas.csv
    write_csv_from_query(
        db_cursor,
        "zone_balancing_areas",
        ["LOAD_ZONE", "balancing_area"],
        """
        SELECT
            name, reserves_area as balancing_area
        FROM switch.load_zone;""",
    )

    # Paty: in this version of switch this tables is named zone_coincident_peak_demand.csv
    # PATY: PENDING csv!
    # # For now, only taking 2014 peak demand and repeating it.
    # print '  lz_peak_loads.csv'
    # db_cursor.execute("""SELECT lzd.name, p.period_name, max(lz_demand_mwh)
    # 				FROM switch.timescales_sample_timepoints tps
    # 				JOIN switch.lz_hourly_demand lzd ON TO_CHAR(lzd.timestamp_cst,'MMDDHH24')=TO_CHAR(tps.timestamp,'MMDDHH24')
    # 				JOIN switch.timescales_sample_timeseries sts USING (sample_ts_id)
    # 				JOIN switch.timescales_population_timeseries pts ON sts.sampled_from_population_timeseries_id = pts.population_ts_id
    # 				JOIN switch.timescales_periods p USING (period_id)
    # 				WHERE sample_ts_scenario_id = %s
    # 				AND lz_hourly_demand_id = %s
    # 				AND load_zones_scenario_id = %s
    # 				AND TO_CHAR(lzd.timestamp_cst,'YYYY') = '2014'
    # 				GROUP BY lzd.name, p.period_name
    # 				ORDER BY 1,2;""" % (sample_ts_scenario_id,lz_hourly_demand_id,load_zones_scenario_id))
    # write_csv('lz_peak_loads',['LOAD_ZONE','PERIOD','peak_demand_mw'],db_cursor)

    ########################################################
    # TRANSMISSION

    # transmission_lines.csv
    write_csv_from_query(
        db_cursor,
        "transmission_lines",
        [
            "TRANSMISSION_LINE",
            "trans_lz1",
            "trans_lz2",
            "trans_length_km",
            "trans_efficiency",
            "existing_trans_cap",
            "trans_dbid",
            "trans_derating_factor",
            "trans_terrain_multiplier",
            "trans_new_build_allowed",
        ],
        """
         SELECT start_load_zone_id || '-' || end_load_zone_id, t1.name, t2.name,
             trans_length_km, trans_efficiency, existing_trans_cap_mw, transmission_line_id,
            derating_factor, terrain_multiplier * transmission_cost_econ_multiplier as terrain_multiplier,
            new_build_allowed
         FROM switch.transmission_lines
             join load_zone as t1 on(t1.load_zone_id=start_load_zone_id)
             join load_zone as t2 on(t2.load_zone_id=end_load_zone_id)
         WHERE start_load_zone_id < end_load_zone_id
         ORDER BY 2,3;
         """,
    )

    # trans_params.csv
    write_csv_from_query(
        db_cursor,
        "trans_params",
        [
            "trans_capital_cost_per_mw_km",
            "trans_lifetime_yrs",
            "trans_fixed_om_fraction"
        ],
        f"""
        SELECT trans_capital_cost_per_mw_km,
            20 as trans_lifetime_yrs,
            0.03 as trans_fixed_om_fraction
        FROM switch.transmission_base_capital_cost
        WHERE transmission_base_capital_cost_scenario_id = {transmission_base_capital_cost_scenario_id}
        ORDER BY 1;
        """,
    )

    ########################################################
    # FUEL

    # fuels.csv
    write_csv_from_query(
        db_cursor,
        "fuels",
        ["fuel", "co2_intensity", "upstream_co2_intensity"],
        """
        SELECT name, co2_intensity, upstream_co2_intensity
        FROM switch.energy_source
        WHERE is_fuel IS TRUE;
        """,
    )

    # non_fuel_energy_sources.csv

    write_csv_from_query(
        db_cursor,
        "non_fuel_energy_sources",
        ["energy_source"],
        """
        SELECT name
        FROM switch.energy_source
        WHERE is_fuel IS FALSE;
        """,
    )

    # Fuel projections are yearly averages in the DB. For now, Switch only accepts fuel prices per period, so they are averaged.
    # fuel_cost.csv
    write_csv_from_query(
        db_cursor,
        "fuel_cost",
        ["load_zone", "fuel", "period", "fuel_cost"],
        f"""
        select load_zone_name as load_zone, fuel, period  as period, AVG(fuel_price) as fuel_cost
		from (
		    select load_zone_name, fuel, fuel_price, projection_year,
		        (
		            case when projection_year >= period.start_year
					and projection_year <= period.start_year + length_yrs -1 then label else 0 end
				) as period
				from switch.fuel_simple_price_yearly
				join switch.period on(projection_year>=start_year)
				where study_timeframe_id = {study_timeframe_id} and fuel_simple_scenario_id = {fuel_simple_price_scenario_id}
		) as w
		where period!=0
		group by load_zone_name, fuel, period
		order by 1,2,3;
		""",
    )

    ########################################################
    # GENERATORS

    #    Optional missing columns in generation_projects_info.csv:
    #        gen_unit_size,
    # 		 gen_ccs_energy_load,
    #        gen_ccs_capture_efficiency,
    #        gen_is_distributed
    # generation_projects_info.csv
    write_csv_from_query(
        db_cursor,
        "generation_projects_info",
        [
            "GENERATION_PROJECT",
            "gen_tech",
            "gen_energy_source",
            "gen_load_zone",
            "gen_max_age",
            "gen_is_variable",
            "gen_is_baseload",
            "gen_full_load_heat_rate",
            "gen_variable_om",
            "gen_connect_cost_per_mw",
            "gen_dbid",
            "gen_scheduled_outage_rate",
            "gen_forced_outage_rate",
            "gen_capacity_limit_mw",
            "gen_min_build_capacity",
            "gen_is_cogen",
            "gen_storage_efficiency",
            "gen_store_to_release_ratio",
            "gen_can_provide_cap_reserves",
            "gen_self_discharge_rate",
            "gen_discharge_efficiency",
            "gen_land_use_rate"
        ],
        f"""
            select
            t.generation_plant_id,
            t.gen_tech,
            t.energy_source as gen_energy_source,
            t2.name as gen_load_zone,
            t.max_age as gen_max_age,
            t.is_variable as gen_is_variable,
            gt.is_baseload as gen_is_baseload,
            t.full_load_heat_rate as gen_full_load_heat_rate,
            vom.variable_o_m as gen_variable_om,
            t.connect_cost_per_mw as gen_connect_cost_per_mw,
            t.generation_plant_id as gen_dbid,
            gt.scheduled_outage_rate as gen_scheduled_outage_rate,
            gt.forced_outage_rate as gen_forced_outage_rate,
            t.final_capacity_limit_mw as gen_capacity_limit_mw,
            t.min_build_capacity as gen_min_build_capacity,
            t.is_cogen as gen_is_cogen,
            storage_efficiency as gen_storage_efficiency,
            store_to_release_ratio as gen_store_to_release_ratio,
            -- hardcode all projects to be allowed as a reserve. might later make this more granular
            1 as gen_can_provide_cap_reserves,
            daily_self_discharge_rate,
            discharge_efficiency,
            land_use_rate
            from switch.generation_plant as t
            join switch.load_zone as t2 using(load_zone_id)
            join switch.generation_plant_scenario_member using(generation_plant_id)
            join switch.variable_o_m_costs as vom
            on vom.gen_tech = t.gen_tech
            and vom.energy_source = t.energy_source
            join switch.generation_plant_technologies as gt
            on gt.gen_tech = t.gen_tech
            and gt.energy_source = t.energy_source
            where variable_o_m_cost_scenario_id = {variable_o_m_cost_scenario_id}
            and generation_plant_technologies_scenario_id = {generation_plant_technologies_scenario_id}
            and generation_plant_scenario_id={generation_plant_scenario_id}
            order by gen_dbid;
            """,
    )

    # gen_build_predetermined.csv
    write_csv_from_query(
        db_cursor,
        "gen_build_predetermined",
        ["GENERATION_PROJECT", "build_year", "gen_predetermined_cap", "gen_predetermined_storage_energy_mwh"],
        f"""select generation_plant_id, build_year, capacity as gen_predetermined_cap, gen_predetermined_storage_energy_mwh
                from generation_plant_existing_and_planned
                join generation_plant as t using(generation_plant_id)
                join generation_plant_scenario_member using(generation_plant_id)
                where generation_plant_scenario_id={generation_plant_scenario_id}
                and generation_plant_existing_and_planned_scenario_id={generation_plant_existing_and_planned_scenario_id}
                ;
                """,
    )

    # gen_build_costs.csv
    write_csv_from_query(
        db_cursor,
        "gen_build_costs",
        [
            "GENERATION_PROJECT",
            "build_year",
            "gen_overnight_cost",
            "gen_fixed_om",
            "gen_storage_energy_overnight_cost",
        ],
        f"""
        select generation_plant_id, generation_plant_cost.build_year,
            overnight_cost as gen_overnight_cost, fixed_o_m as gen_fixed_om,
            storage_energy_capacity_cost_per_mwh as gen_storage_energy_overnight_cost
        FROM generation_plant_cost
          JOIN generation_plant_existing_and_planned USING (generation_plant_id)
          JOIN generation_plant_scenario_member using(generation_plant_id)
          join generation_plant as t1 using(generation_plant_id)
        WHERE generation_plant_scenario_id={generation_plant_scenario_id}
          AND generation_plant_cost.generation_plant_cost_scenario_id={generation_plant_cost_scenario_id}
          AND generation_plant_existing_and_planned_scenario_id={generation_plant_existing_and_planned_scenario_id}
        UNION
        SELECT generation_plant_id, period.label,
            avg(overnight_cost) as gen_overnight_cost, avg(fixed_o_m) as gen_fixed_om,
            avg(storage_energy_capacity_cost_per_mwh) as gen_storage_energy_overnight_cost
        FROM generation_plant_cost
          JOIN generation_plant using(generation_plant_id)
          JOIN period on(build_year>=start_year and build_year<=end_year)
          JOIN generation_plant_scenario_member using(generation_plant_id)
          join generation_plant as t1 using(generation_plant_id)
        WHERE generation_plant_scenario_id={generation_plant_scenario_id}
          AND period.study_timeframe_id={study_timeframe_id}
          AND generation_plant_cost.generation_plant_cost_scenario_id={generation_plant_cost_scenario_id}
        GROUP BY 1,2
        ORDER BY 1,2;""",
    )

    ########################################################
    # FINANCIALS

    #updated from $2016 and 7%
    write_csv(
        [[2018, 0.05, 0.05]],
        "financials",
        ["base_financial_year", "interest_rate", "discount_rate"],
    )
    ########################################################
    # VARIABLE CAPACITY FACTORS

    # Pyomo will raise an error if a capacity factor is defined for a project on a timepoint when it is no longer operational (i.e. Canela 1 was built on 2007 and has a 30 year max age, so for tp's ocurring later than 2037, its capacity factor must not be written in the table).

    # variable_capacity_factors.csv
    if not skip_cf:
        write_csv_from_query(
            db_cursor,
            "variable_capacity_factors",
            ["GENERATION_PROJECT", "timepoint", "gen_max_capacity_factor"],
            f"""
                select
                    generation_plant_id,
                    t.raw_timepoint_id,
                    -- we round down when the capacity factor is less than 1e-5 to avoid numerical issues and simplify our model
                    -- performance wise this doesn't have any significant impact
                    case when abs(capacity_factor) < 0.00001 then 0 else capacity_factor end
                FROM variable_capacity_factors_exist_and_candidate_gen v
                    JOIN generation_plant_scenario_member USING(generation_plant_id)
                    JOIN sampled_timepoint as t ON(t.raw_timepoint_id = v.raw_timepoint_id)
                WHERE generation_plant_scenario_id = {generation_plant_scenario_id}
                    AND t.time_sample_id={time_sample_id};
                """,
        )

    ########################################################
    # HYDROPOWER

    # hydro_timeseries.csv
    # 	db_cursor.execute(("""select generation_plant_id as hydro_project,
    # 					{timeseries_id_select},
    # 					hydro_min_flow_mw, hydro_avg_flow_mw
    # 					from hydro_historical_monthly_capacity_factors
    # 						join sampled_timeseries on(month = date_part('month', first_timepoint_utc))
    # 					where hydro_simple_scenario_id={id1}
    # 					and time_sample_id = {id2};
    # 					""").format(timeseries_id_select=timeseries_id_select, id1=hydro_simple_scenario_id, id2=time_sample_id))
    # Work-around for some hydro plants having 100% capacity factors in a month, which exceeds their
    # standard maintenance derating of 5%. These conditions arise periodically with individual hydro
    # units, but rarely or never for virtual hydro units that aggregate all hydro in a zone or
    # zone + watershed. Eventually, we may rethink this derating, but it is a reasonable
    # approximation for a large hydro fleet where plant outages are individual random events.
    # Negative flows are replaced by 0.
    write_csv_from_query(
        db_cursor,
        "hydro_timeseries",
        ["hydro_project", "timeseries", "hydro_min_flow_mw", "hydro_avg_flow_mw"],
        f"""
        select generation_plant_id as hydro_project,
            {timeseries_id_select},
            CASE
                WHEN hydro_min_flow_mw <= 0 THEN 0
                ELSE least(hydro_min_flow_mw, capacity_limit_mw * (1-forced_outage_rate)) END,
            CASE
                WHEN hydro_avg_flow_mw <= 0 THEN 0
                ELSE least(hydro_avg_flow_mw, capacity_limit_mw * (1-forced_outage_rate)) END
            as hydro_avg_flow_mw
        from hydro_historical_monthly_capacity_factors
            join sampled_timeseries on(month = date_part('month', first_timepoint_utc) and year = date_part('year', first_timepoint_utc))
            join generation_plant using (generation_plant_id)
            join generation_plant_scenario_member using(generation_plant_id)
        where generation_plant_scenario_id = {generation_plant_scenario_id}
        and hydro_simple_scenario_id={hydro_simple_scenario_id}
            and time_sample_id = {time_sample_id}
        order by 1;
        """,
    )

    ########################################################
    # CARBON CAP

    # future work: join with table with carbon_cost_dollar_per_tco2
    # carbon_policies.csv
    write_csv_from_query(
        db_cursor,
        "carbon_policies",
        [
            "PERIOD",
            "carbon_cap_tco2_per_yr",
            "carbon_cap_tco2_per_yr_CA",
            "carbon_cost_dollar_per_tco2",
        ],
        f"""
        select period, AVG(carbon_cap_tco2_per_yr) as carbon_cap_tco2_per_yr, AVG(carbon_cap_tco2_per_yr_CA) as carbon_cap_tco2_per_yr_CA,
            '.' as  carbon_cost_dollar_per_tco2
        from
        (select carbon_cap_tco2_per_yr, carbon_cap_tco2_per_yr_CA, year,
                (case when
                year >= period.start_year
                and year <= period.start_year + length_yrs -1 then label else 0 end) as period
                from switch.carbon_cap
                join switch.period on(year>=start_year)
                where study_timeframe_id = {study_timeframe_id} and carbon_cap_scenario_id = {carbon_cap_scenario_id}) as w
        where period!=0
        group by period
        order by 1;
        """
    )

    ########################################################
    # RPS
    if rps_scenario_id is not None:
        # rps_targets.csv
        write_csv_from_query(
            db_cursor,
            "rps_targets",
            ["load_zone", "period", "rps_target"],
            f"""
            select load_zone, w.period as period, avg(rps_target) as rps_target
                    from
                    (select load_zone, rps_target,
                    (case when
                    year >= period.start_year
                    and year <= period.start_year + length_yrs -1 then label else 0 end) as period
                    from switch.rps_target
                    join switch.period on(year>=start_year)
                    where study_timeframe_id = {study_timeframe_id} and rps_scenario_id = {rps_scenario_id}) as w
            where period!=0
            group by load_zone, period
            order by 1, 2;
            """
        )

    ########################################################
    # BIO_SOLID SUPPLY CURVE

    if supply_curves_scenario_id is not None:
        # fuel_supply_curves.csv
        write_csv_from_query(
            db_cursor,
            "fuel_supply_curves",
            [
                "regional_fuel_market",
                "period",
                "tier",
                "unit_cost",
                "max_avail_at_cost",
            ],
            f"""
                select regional_fuel_market, label as period, tier, unit_cost,
                        (case when max_avail_at_cost is null then 'inf'
                            else max_avail_at_cost::varchar end) as max_avail_at_cost
                from switch.fuel_supply_curves
                join switch.period on(year>=start_year)
                where year=FLOOR(period.start_year + length_yrs/2-1)
                -- we filter out extremly large unit_costs that are only used to indicate that we should never
                -- buy at this price point. This is to simplify the model and improve its numerical properties.
                and not (
                    unit_cost > 1e9
                    and max_avail_at_cost is null
                )
                and study_timeframe_id = {study_timeframe_id}
                and supply_curves_scenario_id = {supply_curves_scenario_id};
                            """,
        )

    # regional_fuel_markets.csv
    write_csv_from_query(
        db_cursor,
        "regional_fuel_markets",
        ["regional_fuel_market", "fuel"],
        f"""
        select regional_fuel_market, fuel
        from switch.regional_fuel_market
        where regional_fuel_market_scenario_id={regional_fuel_market_scenario_id};
                    """,
    )

    # zone_to_regional_fuel_market.csv
    write_csv_from_query(
        db_cursor,
        "zone_to_regional_fuel_market",
        ["load_zone", "regional_fuel_market"],
        f"""
        select load_zone, regional_fuel_market
        from switch.zone_to_regional_fuel_market
        where regional_fuel_market_scenario_id={regional_fuel_market_scenario_id};
                    """,
    )

    ########################################################
    # DEMAND RESPONSE
    if enable_dr is not None:
        write_csv_from_query(
            db_cursor,
            "dr_data",
            ["LOAD_ZONE", "timepoint", "dr_shift_down_limit", "dr_shift_up_limit"],
            f"""
                select load_zone_name as load_zone, sampled_timepoint.raw_timepoint_id AS timepoint,
                case
                    when load_zone_id>=10 and load_zone_id<=21 and extract(year from sampled_timepoint.timestamp_utc)=2020 then 0.003*demand_mw
                    when load_zone_id>=10 and load_zone_id<=21 and extract(year from sampled_timepoint.timestamp_utc)=2030 then 0.02*demand_mw
                    when load_zone_id>=10 and load_zone_id<=21 and extract(year from sampled_timepoint.timestamp_utc)=2040 then 0.07*demand_mw
                    when load_zone_id>=10 and load_zone_id<=21 and extract(year from sampled_timepoint.timestamp_utc)=2050 then 0.1*demand_mw
                    when (load_zone_id<10 or load_zone_id>21) and extract(year from sampled_timepoint.timestamp_utc)=2020 then 0*demand_mw
                    when (load_zone_id<10 or load_zone_id>21) and extract(year from sampled_timepoint.timestamp_utc)=2030 then 0.03*demand_mw
                    when (load_zone_id<10 or load_zone_id>21) and extract(year from sampled_timepoint.timestamp_utc)=2040 then 0.02*demand_mw
                    when (load_zone_id<10 or load_zone_id>21) and extract(year from sampled_timepoint.timestamp_utc)=2050 then 0.07*demand_mw
                end as dr_shift_down_limit,
                NULL as dr_shift_up_limit
                from sampled_timepoint
                left join demand_timeseries on sampled_timepoint.raw_timepoint_id=demand_timeseries.raw_timepoint_id
                where demand_scenario_id = {demand_scenario_id}
                and study_timeframe_id = {study_timeframe_id}
                order by demand_scenario_id, load_zone_id, sampled_timepoint.raw_timepoint_id;
                            """,
        )

    ########################################################
    # ELECTRICAL VEHICLES
    if enable_ev is not None:
        # ev_limits.csv
        write_csv_from_query(
            db_cursor,
            "ev_limits",
            [
                "LOAD_ZONE",
                "timepoint",
                "ev_cumulative_charge_lower_mwh",
                "ev_cumulative_charge_upper_mwh",
                "ev_charge_limit_mw",
            ],
            f"""
                SELECT load_zone_name as load_zone, raw_timepoint_id as timepoint,
                (CASE
                    WHEN raw_timepoint_id=max_raw_timepoint_id THEN ev_cumulative_charge_upper_mwh
                    ELSE ev_cumulative_charge_lower_mwh
                END) AS ev_cumulative_charge_lower_mwh,
                ev_cumulative_charge_upper_mwh,
                ev_charge_limit as ev_charge_limit_mw
                FROM(
                --Table sample_points: with the sample points
                    SELECT
                        load_zone_id,
                        ev_profiles_per_timepoint_v3.raw_timepoint_id,
                        sampled_timeseries_id,
                        sampled_timepoint.timestamp_utc,
                        load_zone_name,
                        ev_cumulative_charge_lower_mwh,
                        ev_cumulative_charge_upper_mwh,
                        ev_charge_limit  FROM ev_profiles_per_timepoint_v3
                    LEFT JOIN sampled_timepoint
                    ON ev_profiles_per_timepoint_v3.raw_timepoint_id = sampled_timepoint.raw_timepoint_id
                    WHERE study_timeframe_id = {study_timeframe_id}
                    --END sample_points
                )AS sample_points
                LEFT JOIN(
                --Table max_raw: with max raw_timepoint_id per _sample_timesseries_id
                SELECT
                    sampled_timeseries_id,
                    MAX(raw_timepoint_id) AS max_raw_timepoint_id
                FROM sampled_timepoint
                WHERE study_timeframe_id = {study_timeframe_id}
                GROUP BY sampled_timeseries_id
                --END max_raw
                )AS max_raw
                ON max_raw.sampled_timeseries_id=sample_points.sampled_timeseries_id
                ORDER BY load_zone_id, raw_timepoint_id ;
                            """,
        )

    ca_policies(db_cursor, ca_policies_scenario_id, study_timeframe_id)
    if enable_planning_reserves:
        planning_reserves(db_cursor, time_sample_id, hydro_simple_scenario_id)
    create_modules_txt()


def ca_policies(db_cursor, ca_policies_scenario_id, study_timeframe_id):
    if ca_policies_scenario_id is None:
        return
    elif ca_policies_scenario_id == 0:
        # scenario_id 0 means
        # "Cali must generate 80% of its load at each timepoint for all periods that have generation in 2030 or later"
        query = f"""
        select
          p.label  as PERIOD, --This is to fix build year problem
          case when p.end_year >= 2030 then 0.8 end as ca_min_gen_timepoint_ratio,
          null as ca_min_gen_period_ratio,
          null as carbon_cap_tco2_per_yr_CA
        from
          switch.period as p
        where
          study_timeframe_id = {study_timeframe_id}
        order by
          1;
        """
    elif ca_policies_scenario_id == 1:
        # scenario_id 1 means
        # "Cali must generate 80% of its load at each timepoint for all periods that have generation in 2030 or later"

        query = f"""
        select
            p.label  as PERIOD, --This is to fix build year problem
            null as ca_min_gen_timepoint_ratio,
            case when p.end_year >= 2030 then 0.8 end as ca_min_gen_period_ratio,
            null as carbon_cap_tco2_per_yr_CA
        from
            switch.period as p
        where
            study_timeframe_id = {study_timeframe_id}
        order by
            1;
        """
    else:
        raise Exception(f"Unknown ca_policies_scenario_id {ca_policies_scenario_id}")

    write_csv_from_query(
        db_cursor,
        "ca_policies",
        ['PERIOD', 'ca_min_gen_timepoint_ratio', 'ca_min_gen_period_ratio', 'carbon_cap_tco2_per_yr_CA'],
        query
    )

    modules.append('switch_model.policies.CA_policies')

def planning_reserves(db_cursor, time_sample_id, hydro_simple_scenario_id):
    # reserve_capacity_value.csv specifies the capacity factors that should be used when calculating
    # the reserves. By default, the capacity factor defaults to gen_max_capacity_factor for renewable
    # projects with variable output and 1.0 for other plants. This is all fine except for hydropower
    # where it doesn't make sense for the reserve capacity factor to be 1.0 since hydropower
    # is limited by hydro_avg_flow_mw. Therefore, we override the default of 1.0 for hydropower
    # generation and instead set the capacity factor as the hydro_avg_flow_mw / capacity_limit_mw.
    write_csv_from_query(
        db_cursor,
        "reserve_capacity_value",
        ["GENERATION_PROJECT","timepoint","gen_capacity_value"],
        f"""
        select
            generation_plant_id,
            raw_timepoint_id,
            -- zero out capacity_factors that are less than 1e-5 in magnitude to simplify the model
            case when abs(capacity_factor) < 1e-5 then 0 else capacity_factor end
        from switch.sampled_timepoint as t
        left join (
            select generation_plant_id, year, month, hydro_avg_flow_mw / capacity_limit_mw as capacity_factor
            from switch.hydro_historical_monthly_capacity_factors
            left join switch.generation_plant
                using(generation_plant_id)
            where hydro_simple_scenario_id = {hydro_simple_scenario_id}
        ) as h
            on (
                month = date_part('month', timestamp_utc) and
                year = date_part('year', timestamp_utc)
            )
        where time_sample_id = {time_sample_id};
        """
    )

    write_csv_from_query(
        db_cursor,
        "planning_reserve_requirement_zones",
        ["PLANNING_RESERVE_REQUIREMENT", "LOAD_ZONE"],
        """
        SELECT
            planning_reserve_requirement, load_zone
        FROM switch.planning_reserve_zones
        """
    )

    write_csv_from_query(
        db_cursor,
        "planning_reserve_requirements",
        ["PLANNING_RESERVE_REQUIREMENT", "prr_cap_reserve_margin", "prr_enforcement_timescale"],
        """
        SELECT
            planning_reserve_requirement, prr_cap_reserve_margin, prr_enforcement_timescale
        FROM switch.planning_reserve_requirements
        """
    )

    modules.append("switch_model.balancing.planning_reserves")


def create_modules_txt():
    print("\tmodules.txt...")
    with open("modules.txt", "w") as f:
        for module in modules:
            f.write(module + "\n")
