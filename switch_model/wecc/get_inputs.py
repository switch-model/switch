#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright 2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.
# Renewable and Appropriate Energy Laboratory, UC Berkeley.
# Operations, Control and Markets laboratory at Pontificia Universidad
# Católica de Chile.
"""

Retrieves data inputs for the Switch WECC model from the database. Data
is formatted into corresponding .tab or .dat files.

"""

import argparse
import getpass
import os
import sys
import time

import psycopg2
import sshtunnel


# Set python to stream output unbuffered.
#sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

def write_tab(fname, headers, cursor):
    with open(fname + '.tab', 'w') as f: # Paty: open() opens file named fname and only allows us to (re)write on it ('w'). "with" keyword ensures the file is closed at the end of the function. 
        f.write('\t'.join(headers) + os.linesep) # Paty: str.join(headers) joins the strings in the sequence "headers" and separates them with string "str"
        for row in cursor:
            # Replace None values with dots for Pyomo. Also turn all datatypes into strings
            row_as_clean_strings = ['.' if element is None else str(element) for element in row]
            f.write('\t'.join(row_as_clean_strings) + os.linesep) # concatenates "line" separated by tabs, and appends \n 


db_cursor = None
db_connection = None
tunnel = None
def shutdown():
	global db_cursor
	global db_connection
	global tunnel
	if db_cursor:
		db_cursor.close()
		db_cursor = None
	if db_connection:
		db_connection.close()
		db_connection = None
	# os.chdir('..')
	if tunnel:
		tunnel.stop()
		tunnel = None
# Make sure the ssh tunnel is shutdown properly when python exits, even if an exception has been raised.
# Hmm. the ssh tunnel still manages to hang before atexit gets called. 
# atexit.register(shutdown)



def main():
	global db_cursor
	global db_connection
	global tunnel
	start_time = time.time()
	
	parser = argparse.ArgumentParser(
		usage='get_switch_pyomo_input_tables.py [--help] [options]',
		description='Write SWITCH input files from database tables. Default \
		options asume an SSH tunnel has been opened between the local port 5432\
		and the Postgres port at the remote host where the database is stored.',
		formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument(
		'-H', '--hostname', dest="host", type=str, 
		default='switch-db2.erg.berkeley.edu', metavar='hostname', 
		help='Database host address')
	parser.add_argument(
		'-P', '--port', dest="port", type=int, default=5432, metavar='port',
		help='Database host port')
	parser.add_argument(
		'-U', '--user', dest='user', type=str, default=getpass.getuser(), metavar='username',
		help='Database username')
	parser.add_argument(
		'-D', '--database', dest='database', type=str, default='switch_wecc', metavar='dbname',
		help='Database name')
	parser.add_argument(
		'-s', type=int, required=True, metavar='scenario_id',
		help='Scenario ID for the simulation')
	parser.add_argument(
		'-i', type=str, default='inputs', metavar='inputsdir',
		help='Directory where the inputs will be built')
	args = parser.parse_args()
	
	passw = getpass.getpass('Enter database password for user %s:' % args.user)
	
	# Connection settings are determined by parsed command line inputs
	# Start an ssh tunnel because the database only permits local connections
	tunnel = sshtunnel.SSHTunnelForwarder(
		args.host,
		ssh_pkey= os.path.expanduser('~') + "/.ssh/id_rsa",
		remote_bind_address=('127.0.0.1', args.port)
	)
	tunnel.start()
	try:
		db_connection = psycopg2.connect(database=args.database, user=args.user, host='127.0.0.1',
							   port=tunnel.local_bind_port, password=passw)
	except:
		tunnel.stop()
		raise
	print "Connection to database established..."
	
	if not os.path.exists(args.i):
		os.makedirs(args.i)
		print 'Inputs directory created...'
	else:
		print 'Inputs directory exists, so contents will be overwritten...'
	
	db_cursor = db_connection.cursor()

	# Test db connection for debugging...
	# db_cursor.execute("select 1 + 1 as x;")
	# print db_cursor.fetchone()
	# shutdown()
	# sys.exit("Finished our test")
	
	############################################################################################################
	# These next variables determine which input data is used, though some are only for documentation and result exports.
	
	db_cursor.execute("SELECT name, description, study_timeframe_id, time_sample_id, demand_scenario_id,  fuel_simple_price_scenario_id, generation_plant_scenario_id, generation_plant_cost_scenario_id, generation_plant_existing_and_planned_scenario_id, hydro_simple_scenario_id, carbon_cap_scenario_id  FROM switch.scenario WHERE scenario_id = %s" % args.s)
	s_details = db_cursor.fetchone()
	#name, description, sample_ts_scenario_id, hydro_scenario_meta_id, fuel_id, gen_costs_id, new_projects_id, carbon_tax_id, carbon_cap_id, rps_id, lz_hourly_demand_id, gen_info_id, load_zones_scenario_id, existing_projects_id, demand_growth_id = s_details[1], s_details[2], s_details[3], s_details[4], s_details[5], s_details[6], s_details[7], s_details[8], s_details[9], s_details[10], s_details[11], s_details[12], s_details[13], s_details[14], s_details[15]
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
	
	os.chdir(args.i)
	
	# The format for tab files is:
	# col1_name col2_name ...
	# [rows of data]
	
	# The format for dat files is the same as in AMPL dat files.
	
	print '\nStarting data copying from the database to input files for scenario: "%s"' % name
	
	# Write general scenario parameters into a documentation file
	print 'Writing scenario documentation into scenario_params.txt.'
	with open('scenario_params.txt', 'w') as f:
		f.write('Scenario id: %s' % args.s)
		f.write('\nScenario name: %s' % name)
		f.write('\nScenario notes: %s' % description)
	
	########################################################
	# TIMESCALES
	
	print '  periods.tab...'
	db_cursor.execute(("""select label, start_year as period_start, end_year as period_end
					from period where study_timeframe_id={id}
					order by 1;
					""").format(id=study_timeframe_id))			
	write_tab('periods', ['INVESTMENT_PERIOD', 'period_start', 'period_end'], db_cursor)
	
	print '  timeseries.tab...'
	timeseries_id_select = "date_part('year', first_timepoint_utc)|| '_' || replace(sampled_timeseries.name, ' ', '_') as timeseries"
	db_cursor.execute(("""select {timeseries_id_select}, t.label as ts_period, 
					hours_per_tp as ts_duration_of_tp, num_timepoints as ts_num_tps, scaling_to_period as ts_scale_to_period
					from switch.sampled_timeseries
						join period as t using(period_id)
					where sampled_timeseries.study_timeframe_id={id}
					order by label;
					""").format(timeseries_id_select=timeseries_id_select, id=study_timeframe_id))
	write_tab('timeseries', ['TIMESERIES', 'ts_period', 'ts_duration_of_tp', 'ts_num_tps', 'ts_scale_to_period'], db_cursor)
	
	print '  timepoints.tab...'
	db_cursor.execute(("""select raw_timepoint_id as timepoint_id, to_char(timestamp_utc, 'YYYYMMDDHH24') as timestamp, 
					{timeseries_id_select}
					from sampled_timepoint as t
						join sampled_timeseries using(sampled_timeseries_id)
					where t.study_timeframe_id={id}
					order by 1;
					""").format(timeseries_id_select=timeseries_id_select, id=study_timeframe_id))
	write_tab('timepoints', ['timepoint_id','timestamp','timeseries'], db_cursor)
	
	########################################################
	# LOAD ZONES
	
	#done
	print '  load_zones.tab...'
	db_cursor.execute("""SELECT name, ccs_distance_km as zone_ccs_distance_km, load_zone_id as zone_dbid 
					FROM switch.load_zone  
					ORDER BY 1;
					""" )
	write_tab('load_zones',['LOAD_ZONE','zone_ccs_distance_km','zone_dbid'],db_cursor)
	
	print '  loads.tab...'
	db_cursor.execute(("""select load_zone_name, t.raw_timepoint_id as timepoint, demand_mw as zone_demand_mw
					from sampled_timepoint as t
						join sampled_timeseries using(sampled_timeseries_id)
						join demand_timeseries as d using(raw_timepoint_id)
					where t.study_timeframe_id={id}
					and demand_scenario_id={id2}
					order by 1,2;
					""").format(id=study_timeframe_id, id2=demand_scenario_id))
	write_tab('loads',['LOAD_ZONE','TIMEPOINT','zone_demand_mw'],db_cursor)
	
	########################################################
	# BALANCING AREAS [Pending zone_coincident_peak_demand.tab]
	
	print '  balancing_areas.tab...'
	db_cursor.execute("""SELECT balancing_area, quickstart_res_load_frac, quickstart_res_wind_frac, quickstart_res_solar_frac,spinning_res_load_frac, 
					spinning_res_wind_frac, spinning_res_solar_frac 
					FROM switch.balancing_areas;
					""")
	write_tab('balancing_areas',['BALANCING_AREAS','quickstart_res_load_frac','quickstart_res_wind_frac','quickstart_res_solar_frac','spinning_res_load_frac','spinning_res_wind_frac','spinning_res_solar_frac'],db_cursor)
	
	print '  zone_balancing_areas.tab...'
	db_cursor.execute("""SELECT name, reserves_area as balancing_area 
					FROM switch.load_zone;
					""")
	write_tab('zone_balancing_areas',['LOAD_ZONE','balancing_area'],db_cursor)
	
	#Paty: in this version of switch this tables is named zone_coincident_peak_demand.tab
	#PATY: PENDING TAB!
	# # For now, only taking 2014 peak demand and repeating it.
	# print '  lz_peak_loads.tab'
	# db_cursor.execute("""SELECT lzd.name, p.period_name, max(lz_demand_mwh) 
	#				FROM switch.timescales_sample_timepoints tps 
	#				JOIN switch.lz_hourly_demand lzd ON TO_CHAR(lzd.timestamp_cst,'MMDDHH24')=TO_CHAR(tps.timestamp,'MMDDHH24') 
	#				JOIN switch.timescales_sample_timeseries sts USING (sample_ts_id) 
	#				JOIN switch.timescales_population_timeseries pts ON sts.sampled_from_population_timeseries_id = pts.population_ts_id 
	#				JOIN switch.timescales_periods p USING (period_id) 
	#				WHERE sample_ts_scenario_id = %s 
	#				AND lz_hourly_demand_id = %s 
	#				AND load_zones_scenario_id = %s 
	#				AND TO_CHAR(lzd.timestamp_cst,'YYYY') = '2014' 
	#				GROUP BY lzd.name, p.period_name 
	#				ORDER BY 1,2;""" % (sample_ts_scenario_id,lz_hourly_demand_id,load_zones_scenario_id))
	# write_tab('lz_peak_loads',['LOAD_ZONE','PERIOD','peak_demand_mw'],db_cursor)
	
	########################################################
	# TRANSMISSION
	
	print '  transmission_lines.tab...'
	db_cursor.execute("""SELECT start_load_zone_id || '-' || end_load_zone_id, t1.name, t2.name, 
					trans_length_km, trans_efficiency, existing_trans_cap_mw 
					FROM switch.transmission_lines
					join load_zone as t1 on(t1.load_zone_id=start_load_zone_id)
					join load_zone as t2 on(t2.load_zone_id=end_load_zone_id)  
					ORDER BY 2,3;
					""")
	write_tab('transmission_lines',['TRANSMISSION_LINE','trans_lz1','trans_lz2','trans_length_km','trans_efficiency','existing_trans_cap'],db_cursor)
	
	print '  trans_optional_params.tab...'
	db_cursor.execute("""SELECT start_load_zone_id || '-' || end_load_zone_id, transmission_line_id, derating_factor, terrain_multiplier, 
					new_build_allowed 
					FROM switch.transmission_lines 
					ORDER BY 1;
					""")
	write_tab('trans_optional_params.tab',['TRANSMISSION_LINE','trans_dbid','trans_derating_factor','trans_terrain_multiplier','trans_new_build_allowed'],db_cursor)
	
	print '  trans_params.dat...'
	with open('trans_params.dat','w') as f:
		f.write("param trans_capital_cost_per_mw_km:=1150;\n") # $1150 opposed to $1000 to reflect change to US$2016
		f.write("param trans_lifetime_yrs:=20;\n") # Paty: check what lifetime has been used for the wecc
		f.write("param trans_fixed_om_fraction:=0.03;\n")
		#f.write("param distribution_loss_rate:=0.0652;\n")
	
	########################################################
	# FUEL
	
	print '  fuels.tab...'
	db_cursor.execute("""SELECT name, co2_intensity, upstream_co2_intensity 
					FROM switch.energy_source WHERE is_fuel IS TRUE;
					""")
	write_tab('fuels',['fuel','co2_intensity','upstream_co2_intensity'],db_cursor)
	
	print '  non_fuel_energy_sources.tab...'
	db_cursor.execute("""SELECT name 
					FROM switch.energy_source 
					WHERE is_fuel IS FALSE;
					""")
	write_tab('non_fuel_energy_sources',['energy_source'],db_cursor)
	
	# Fuel projections are yearly averages in the DB. For now, Switch only accepts fuel prices per period, so they are averaged.
	print '  fuel_cost.tab'
	db_cursor.execute("""select load_zone_name as load_zone, fuel, period, AVG(fuel_price) as fuel_cost 
					from 
					(select load_zone_name, fuel, fuel_price, projection_year, 
							(case when 
							projection_year >= period.start_year 
							and projection_year <= period.start_year + length_yrs -1 then label else 0 end) as period
							from switch.fuel_simple_price_yearly
							join switch.period on(projection_year>=start_year)
							where study_timeframe_id = %s and fuel_simple_scenario_id = %s) as w
					where period!=0
					group by load_zone_name, fuel, period
					order by 1,2,3;
					""" % (study_timeframe_id, fuel_simple_price_scenario_id))
	write_tab('fuel_cost',['load_zone','fuel','period','fuel_cost'],db_cursor)
	
	########################################################
	# GENERATORS
	
	#    Optional missing columns in generation_projects_info.tab:
	#        gen_unit_size, 
	#		 gen_ccs_energy_load,
	#        gen_ccs_capture_efficiency, 
	#        gen_is_distributed
	print '  generation_projects_info.tab...'
	db_cursor.execute(
		"""select 
				generation_plant_id, 
				gen_tech, 
				energy_source as gen_energy_source, 
				t2.name as gen_load_zone, 
				max_age as gen_max_age, 
				is_variable as gen_is_variable, 
				is_baseload as gen_is_baseload,
				full_load_heat_rate as gen_full_load_heat_rate, 
				variable_o_m as gen_variable_om,
				connect_cost_per_mw as gen_connect_cost_per_mw,
				generation_plant_id as gen_dbid, 
				scheduled_outage_rate as gen_scheduled_outage_rate,
				forced_outage_rate as gen_forced_outage_rate, 
				capacity_limit_mw as gen_capacity_limit_mw,
				min_build_capacity as gen_min_build_capacity, 
				is_cogen as gen_is_cogen
			from generation_plant as t
			join load_zone as t2 using(load_zone_id)
			order by gen_dbid;
					""" ) 
	write_tab('generation_projects_info',['GENERATION_PROJECT','gen_tech','gen_energy_source','gen_load_zone','gen_max_age','gen_is_variable','gen_is_baseload','gen_full_load_heat_rate','gen_variable_om','gen_connect_cost_per_mw','gen_dbid','gen_scheduled_outage_rate','gen_forced_outage_rate','gen_capacity_limit_mw', 'gen_min_build_capacity', 'gen_is_cogen'],db_cursor)
	
	print '  gen_build_predetermined.tab...'
	db_cursor.execute("""select generation_plant_id, build_year, capacity as gen_predetermined_cap  
					from generation_plant_existing_and_planned 
					join generation_plant as t using(generation_plant_id)  
					where generation_plant_existing_and_planned_scenario_id=%s
					;
				""" % (generation_plant_existing_and_planned_scenario_id))
	write_tab('gen_build_predetermined',['GENERATION_PROJECT','build_year','gen_predetermined_cap'],db_cursor)
	
	print '  gen_build_costs.tab...'
	db_cursor.execute(("""select project_id as generation_plant_id, start_year as label,  overnight_cost as gen_overnight_cost, fixed_o_m as gen_fixed_om
					from generation_plant_vintage_cost
					union
					select generation_plant_id, label, avg(overnight_cost) as gen_overnight_cost, avg(fixed_o_m) as gen_fixed_om
					from generation_plant_cost 
					JOIN generation_plant using(generation_plant_id) 
					JOIN period on(build_year>=start_year and build_year<=end_year)
					where period.study_timeframe_id={id1} 
					and generation_plant_cost.generation_plant_cost_scenario_id={id2}
					group by 1,2
					order by 1,2;
					""").format(id1=study_timeframe_id, id2=generation_plant_cost_scenario_id)) 
	write_tab('gen_build_costs',['GENERATION_PROJECT','build_year','gen_overnight_cost','gen_fixed_om'],db_cursor)
	
	########################################################
	# FINANCIALS
	
	print '  financials.dat...'
	with open('financials.dat','w') as f:
		f.write("param base_financial_year := 2016;\n")
		f.write("param interest_rate := .07;\n")
		f.write("param discount_rate := .07;\n")
	
	########################################################
	# VARIABLE CAPACITY FACTORS
	
	#Pyomo will raise an error if a capacity factor is defined for a project on a timepoint when it is no longer operational (i.e. Canela 1 was built on 2007 and has a 30 year max age, so for tp's ocurring later than 2037, its capacity factor must not be written in the table).
	
	
	print '  variable_capacity_factors.tab...'
	db_cursor.execute(("""select project_id, raw_timepoint_id, cap_factor  
						FROM temp_ampl_study_timepoints 
						JOIN temp_load_scenario_historic_timepoints USING(timepoint_id)
						JOIN temp_variable_capacity_factors_historical ON(historic_hour=hour)
						JOIN temp_ampl__proposed_projects_v3 USING(project_id)
						JOIN temp_ampl_load_area_info_v3 USING(area_id)
						JOIN sampled_timepoint as t ON(raw_timepoint_id = timepoint_id)
						JOIN sampled_timeseries using(sampled_timeseries_id)
						WHERE load_scenario_id=21 -- not an input from scenarios. This id is related to historical timepoints table
						AND (( avg_cap_factor_percentile_by_intermittent_tech >= 0.75 or cumulative_avg_MW_tech_load_area <= 3 * total_yearly_load_mwh / 8766 or rank_by_tech_in_load_area <= 5 or avg_cap_factor_percentile_by_intermittent_tech is null) and technology <> 'Concentrating_PV') 
						AND technology_id <> 7 
						AND t.study_timeframe_id={id} 
				UNION 
						select project_id, raw_timepoint_id, cap_factor_adjusted as cap_factor  
						FROM temp_ampl_study_timepoints 
						JOIN temp_load_scenario_historic_timepoints USING(timepoint_id)
						JOIN temp_variable_capacity_factors_historical_csp ON(historic_hour=hour)
						JOIN temp_ampl__proposed_projects_v3 USING(project_id)
						JOIN temp_ampl_load_area_info_v3 USING(area_id)
						JOIN sampled_timepoint as t ON(raw_timepoint_id = timepoint_id)
						JOIN sampled_timeseries using(sampled_timeseries_id)
						WHERE load_scenario_id=21 -- not an input from scenarios. This id is related to historical timepoints table
						AND (( avg_cap_factor_percentile_by_intermittent_tech >= 0.75 or cumulative_avg_MW_tech_load_area <= 3 * total_yearly_load_mwh / 8766 or rank_by_tech_in_load_area <= 5 or avg_cap_factor_percentile_by_intermittent_tech is null) and technology <> 'Concentrating_PV') 
						AND technology_id = 7
						AND t.study_timeframe_id={id}
				UNION 
						select project_id, raw_timepoint_id, cap_factor
						from ampl_existing_intermittent_plant_cap_factor as t2
						join sampled_timepoint as t ON(raw_timepoint_id = t2.timepoint_id)
						JOIN sampled_timeseries using(sampled_timeseries_id)
						WHERE t.study_timeframe_id={id}
						order by 1,2;
						""").format(id=study_timeframe_id))
	write_tab('variable_capacity_factors',['GENERATION_PROJECT','timepoint','gen_max_capacity_factor'],db_cursor)
	
	########################################################
	# HYDROPOWER
	
	print '  hydro_timeseries.tab...'
# 	db_cursor.execute(("""select generation_plant_id as hydro_project, 
# 					{timeseries_id_select}, 
# 					hydro_min_flow_mw, hydro_avg_flow_mw
# 					from hydro_historical_monthly_capacity_factors
# 						join sampled_timeseries on(month = date_part('month', first_timepoint_utc))
# 					where hydro_simple_scenario_id={id1}
# 					and study_timeframe_id = {id2};
# 					""").format(timeseries_id_select=timeseries_id_select, id1=hydro_simple_scenario_id, id2=study_timeframe_id))
	# Work-around for some hydro plants having 100% capacity factors in a month, which exceeds their 
	# standard maintenance derating of 5%. These conditions arise periodically with individual hydro
	# units, but rarely or never for virtual hydro units that aggregate all hydro in a zone or 
	# zone + watershed. Eventually, we may rethink this derating, but it is a reasonable 
	# approximation for a large hydro fleet where plant outages are individual random events.
	db_cursor.execute(("""
		select generation_plant_id as hydro_project, 
			{timeseries_id_select}, 
			hydro_min_flow_mw, 
			least(hydro_avg_flow_mw, capacity * (1-forced_outage_rate)) as hydro_avg_flow_mw
		from hydro_historical_monthly_capacity_factors
			join sampled_timeseries on(month = date_part('month', first_timepoint_utc))
			join generation_plant_existing_and_planned using(generation_plant_id)
			join generation_plant using(generation_plant_id)
		where hydro_simple_scenario_id={id1}
			and study_timeframe_id = {id2};
		""").format(timeseries_id_select=timeseries_id_select, id1=hydro_simple_scenario_id, id2=study_timeframe_id))
	write_tab('hydro_timeseries',['hydro_project','timeseries','hydro_min_flow_mw', 'hydro_avg_flow_mw'],db_cursor)
	
	########################################################
	# CARBON CAP
	
	# future work: join with table with carbon_cost_dollar_per_tco2
	print '  carbon_policies.tab...'
	db_cursor.execute(("""select period, AVG(carbon_cap_tco2_per_yr) as carbon_cap_tco2_per_yr, '.' as  carbon_cost_dollar_per_tco2
					from 
					(select carbon_cap_tco2_per_yr, year, 
							(case when 
							year >= period.start_year 
							and year <= period.start_year + length_yrs -1 then label else 0 end) as period
							from switch.carbon_cap
							join switch.period on(year>=start_year)
							where study_timeframe_id = {id1} and carbon_cap_scenario_id = {id2}) as w
					where period!=0
					group by period
					order by 1;
					""").format(id1=study_timeframe_id, id2=carbon_cap_scenario_id))
	write_tab('carbon_policies',['PERIOD','carbon_cap_tco2_per_yr','carbon_cost_dollar_per_tco2'],db_cursor)
	
	end_time = time.time()
	
	print '\nScript took %s seconds building input tables.' % (end_time-start_time)
	shutdown()

if __name__ == "__main__":
    main()
