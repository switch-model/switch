# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Upgrade input directories from 2.0.0b0 to 2.0.0b1.
Major changes are:
* Merge gen_tech files into project_ files
* Drop lz_economic_multiplier from load_zones & merge into project-specific costs
* Rename several input files:
    'proj_existing_builds.tab':       'gen_build_predetermined.tab',
    'project_info.tab':               'generation_projects_info.tab',
    'proj_build_costs.tab':           'gen_build_costs.tab',
    'proj_inc_heat_rates.tab':        'gen_inc_heat_rates.tab',
    'hydro_projects.tab':             'hydro_generation_projects.tab',
    'lz_peak_loads.tab':              'zone_coincident_peak_demand.tab',
    'lz_to_regional_fuel_market.tab': 'zone_to_regional_fuel_market.tab'
* Rename various columns of input files. See old_new_column_names_in_file
  in this module for a complete listing.
* Explicity list each module by its full name in modules.txt
    - Insert the list of core modules as needed; previously switch would
      auto-insert them as needed
    - Expand any package listing to its core modules
* Several modules were renamed and/or moved. See the rename_modules list in
  this module for a complete listing.
* Store the software version number in the input directory
"""

import os
import shutil
import pandas
import argparse
import switch_model.upgrade

upgrades_from = '2.0.0b0'
upgrades_to = '2.0.0b1'

old_modules = {
    'switch_mod.balancing_areas',
    'switch_mod.export',
    'switch_mod.export.__init__',
    'switch_mod.export.dump',
    'switch_mod.export.example_export',
    'switch_mod.financials',
    'switch_mod.fuel_cost',
    'switch_mod.fuel_markets',
    'switch_mod.fuels',
    'switch_mod.gen_tech',
    'switch_mod.generators.hydro_simple',
    'switch_mod.generators.hydro_system',
    'switch_mod.generators.storage',
    'switch_mod.hawaii.batteries',
    'switch_mod.hawaii.batteries_fixed_calendar_life',
    'switch_mod.hawaii.constant_elasticity_demand_system',
    'switch_mod.hawaii.demand_response',
    'switch_mod.hawaii.demand_response_no_reserves',
    'switch_mod.hawaii.demand_response_simple',
    'switch_mod.hawaii.emission_rules',
    'switch_mod.hawaii.ev',
    'switch_mod.hawaii.fed_subsidies',
    'switch_mod.hawaii.fuel_markets_expansion',
    'switch_mod.hawaii.hydrogen',
    'switch_mod.hawaii.kalaeloa',
    'switch_mod.hawaii.lng_conversion',
    'switch_mod.hawaii.no_central_pv',
    'switch_mod.hawaii.no_onshore_wind',
    'switch_mod.hawaii.no_renewables',
    'switch_mod.hawaii.no_wind',
    'switch_mod.hawaii.psip',
    'switch_mod.hawaii.pumped_hydro',
    'switch_mod.hawaii.r_demand_system',
    'switch_mod.hawaii.reserves',
    'switch_mod.hawaii.rps',
    'switch_mod.hawaii.save_results',
    'switch_mod.hawaii.scenario_data',
    'switch_mod.hawaii.scenarios',
    'switch_mod.hawaii.smooth_dispatch',
    'switch_mod.hawaii.switch_patch',
    'switch_mod.hawaii.unserved_load',
    'switch_mod.hawaii.util',
    'switch_mod.load_zones',
    'switch_mod.local_td',
    'switch_mod.main',
    'switch_mod.project.build',
    'switch_mod.project.discrete_build',
    'switch_mod.project.dispatch',
    'switch_mod.project.no_commit',
    'switch_mod.project.unitcommit.commit',
    'switch_mod.project.unitcommit.discrete',
    'switch_mod.project.unitcommit.fuel_use',
    'switch_mod.solve',
    'switch_mod.solve_scenarios',
    'switch_mod.test',
    'switch_mod.timescales',
    'switch_mod.trans_build',
    'switch_mod.trans_dispatch',
    'switch_mod.utilities',
    'switch_mod.project',
    'switch_mod.project.unitcommit',
}
rename_modules = {
    'switch_mod.load_zones': 'switch_mod.balancing.load_zones',
    'switch_mod.fuels': 'switch_mod.energy_sources.properties',
    'switch_mod.trans_build': 'switch_mod.transmission.transport.build',
    'switch_mod.trans_dispatch': 'switch_mod.transmission.transport.dispatch',
    'switch_mod.project.build': 'switch_mod.generators.core.build',
    'switch_mod.project.discrete_build': 'switch_mod.generators.core.gen_discrete_build',
    'switch_mod.project.dispatch': 'switch_mod.generators.core.dispatch',
    'switch_mod.project.no_commit': 'switch_mod.generators.core.no_commit',
    'switch_mod.project.unitcommit.commit': 'switch_mod.generators.core.commit.operate',
    'switch_mod.project.unitcommit.fuel_use': 'switch_mod.generators.core.commit.fuel_use',
    'switch_mod.project.unitcommit.discrete': 'switch_mod.generators.core.commit.discrete',
    'switch_mod.fuel_cost': 'switch_mod.energy_sources.fuel_costs.simple',
    'switch_mod.fuel_markets': 'switch_mod.energy_sources.fuel_costs.markets',
    'switch_mod.export': 'switch_mod.reporting',
    'switch_mod.local_td': 'switch_mod.transmission.local_td',
    'switch_mod.balancing_areas': 'switch_mod.balancing.operating_reserves.areas',
    'switch_mod.export.dump': 'switch_mod.reporting.dump',
    'switch_mod.generators.hydro_simple': 
        'switch_mod.generators.extensions.hydro_simple',
    'switch_mod.generators.hydro_system':
        'switch_mod.generators.extensions.hydro_system',
    'switch_mod.generators.storage':
        'switch_mod.generators.extensions.storage',
}
module_prefix = 'switch_mod.'
expand_modules = { # Old module name: [new module names]
    'switch_mod': [
        '### begin core modules ###',
        'switch_mod',
        'switch_mod.timescales',
        'switch_mod.financials',
        'switch_mod.balancing.load_zones',
        'switch_mod.energy_sources.properties',
        'switch_mod.generators.core.build',
        'switch_mod.generators.core.dispatch',
        'switch_mod.reporting',
        '### end core modules ###'
    ],
    'switch_mod.project': [
        'switch_mod.generators.core.build',
        'switch_mod.generators.core.dispatch'
    ],
    'switch_mod.project.unitcommit': [
        'switch_mod.generators.core.commit.operate',
        'switch_mod.generators.core.commit.fuel_use'
    ],
}


def upgrade_input_dir(inputs_dir):
    """
    Upgrade an input directory.
    """

    def rename_file(old_name, new_name, optional_file=True):
        old_path = os.path.join(inputs_dir, old_name)
        new_path = os.path.join(inputs_dir, new_name)
        if optional_file and not os.path.isfile(old_path):
            return
        shutil.move(old_path, new_path)
    
    def rename_column(file_name, old_col_name, new_col_name, optional_file=True):
        path = os.path.join(inputs_dir, file_name)
        if optional_file and not os.path.isfile(path):
            return
        df = pandas.read_csv(path, na_values=['.'], sep='\t')
        df.rename(columns={old_col_name: new_col_name}, inplace=True)
        df.to_csv(path, sep='\t', na_rep='.', index=False)        
    
    rename_file('modules', 'modules.txt')
    modules_path = os.path.join(inputs_dir, 'modules.txt')
    if not os.path.isfile(modules_path):
        modules_path = os.path.join(inputs_dir, '..', 'modules.txt')
    if not os.path.isfile(modules_path):
        raise RuntimeError(
            "Unable to find modules or modules.txt file for input directory '{}'. "
            "This file should be located in the input directory or its parent."
            .format(inputs_dir)
        )

    ###
    # Upgrade module listings
    # Each line of the original file is either a module identifier or a comment
    with open(modules_path) as f:
        module_list = [line.strip() for line in f.read().splitlines()]

    # If the original file didn't specify either switch_mod or the list of
    # core modules, we need to insert switch_mod.
    if not('switch_mod' in module_list or
           'timescales' in module_list or
           'switch_mod.timescales' in module_list):
        module_list.insert(0, 'switch_mod')
    
    new_module_list=[]
    for module in module_list:
        # add prefix if appropriate 
        # (standardizes names for further processing)
        if module_prefix + module in old_modules:
            module = module_prefix + module
        if module in rename_modules:
            module = rename_modules[module]
        if module in expand_modules:
            new_module_list.extend(expand_modules[module])
        else:
            new_module_list.append(module)
    # remove duplicates (e.g., repeated expansion of switch_mod)
    # This mimics old switch behavior if a module was expanded
    # and also added separately.
    final_module_list = []
    for module in new_module_list:
        if module not in final_module_list:
            final_module_list.append(module)

    with open(modules_path, 'w') as f:
       for module in final_module_list:
            f.write(module + "\n")

    ###
    # Get load zone economic multipliers (if available), then drop that column.
    load_zone_path = os.path.join(inputs_dir, 'load_zones.tab')
    load_zone_df = pandas.read_csv(load_zone_path, na_values=['.'], sep='\t')
    if 'lz_cost_multipliers' in load_zone_df:
        load_zone_df['lz_cost_multipliers'].fillna(1)
    else:
        load_zone_df['lz_cost_multipliers'] = 1
    load_zone_keep_cols = [c for c in load_zone_df if c != 'lz_cost_multipliers']
    load_zone_df.to_csv(load_zone_path, sep='\t', na_rep='.', 
                        index=False, columns=load_zone_keep_cols)

    ###
    # Merge generator_info with project_info
    gen_info_path = os.path.join(inputs_dir, 'generator_info.tab')
    gen_info_df = pandas.read_csv(gen_info_path, na_values=['.'], sep='\t')
    gen_info_col_renames = {
        'generation_technology': 'proj_gen_tech',
        'g_energy_source': 'proj_energy_source',
        'g_max_age': 'proj_max_age',
        'g_scheduled_outage_rate': 'proj_scheduled_outage_rate.default',
        'g_forced_outage_rate': 'proj_forced_outage_rate.default',
        'g_variable_o_m': 'proj_variable_om.default',
        'g_full_load_heat_rate': 'proj_full_load_heat_rate.default',
        'g_is_variable': 'proj_is_variable',
        'g_is_baseload': 'proj_is_baseload',
        'g_min_build_capacity': 'proj_min_build_capacity',
        'g_is_cogen': 'proj_is_cogen',
        'g_storage_efficiency': 'proj_storage_efficiency.default',
        'g_store_to_release_ratio': 'proj_store_to_release_ratio.default',
        'g_unit_size': 'proj_unit_size.default',
        'g_min_load_fraction': 'proj_min_load_fraction.default',
        'g_startup_fuel': 'proj_startup_fuel.default',
        'g_startup_om': 'proj_startup_om.default',
        'g_ccs_capture_efficiency': 'proj_ccs_capture_efficiency.default', 
        'g_ccs_energy_load': 'proj_ccs_energy_load.default'
    }
    drop_cols = [c for c in gen_info_df if c not in gen_info_col_renames]
    for c in drop_cols:
        del gen_info_df[c]
    gen_info_df.rename(columns=gen_info_col_renames, inplace=True)
    proj_info_path = os.path.join(inputs_dir, 'project_info.tab')
    proj_info_df = pandas.read_csv(proj_info_path, na_values=['.'], sep='\t')
    proj_info_df = pandas.merge(proj_info_df, gen_info_df, on='proj_gen_tech', how='left')
    # Factor in the load zone cost multipliers
    proj_info_df = pandas.merge(
        load_zone_df[['LOAD_ZONE', 'lz_cost_multipliers']], proj_info_df,
        left_on='LOAD_ZONE', right_on='proj_load_zone', how='right')
    proj_info_df['proj_variable_om.default'] *= proj_info_df['lz_cost_multipliers']
    for c in ['LOAD_ZONE', 'lz_cost_multipliers']:
        del proj_info_df[c]

    # An internal function to apply a column of default values to the actual column
    def update_cols_with_defaults(df, col_list):
        for col in col_list:
            default_col = col + '.default'
            if default_col not in df:
                continue
            if col not in df:
                df.rename(columns={default_col: col}, inplace=True)
            else:
                df[col].fillna(df[default_col], inplace=True)
                del df[default_col]

    columns_with_defaults = ['proj_scheduled_outage_rate', 'proj_forced_outage_rate',
                             'proj_variable_om', 'proj_full_load_heat_rate',
                             'proj_storage_efficiency', 'proj_store_to_release_ratio',
                             'proj_unit_size', 'proj_min_load_fraction',
                             'proj_startup_fuel', 'proj_startup_om',
                             'proj_ccs_capture_efficiency', 'proj_ccs_energy_load']
    update_cols_with_defaults(proj_info_df, columns_with_defaults)
    proj_info_df.to_csv(proj_info_path, sep='\t', na_rep='.', index=False)
    os.remove(gen_info_path)

    ###
    # Merge gen_new_build_costs into proj_build_costs

    # Translate default generator costs into costs for each project
    gen_build_path = os.path.join(inputs_dir, 'gen_new_build_costs.tab')
    if os.path.isfile(gen_build_path):
        gen_build_df = pandas.read_csv(gen_build_path, na_values=['.'], sep='\t')
        new_col_names = {
            'generation_technology': 'proj_gen_tech',
            'investment_period': 'build_year',
            'g_overnight_cost': 'proj_overnight_cost.default',
            'g_storage_energy_overnight_cost': 'proj_storage_energy_overnight_cost.default',
            'g_fixed_o_m': 'proj_fixed_om.default'}
        gen_build_df.rename(columns=new_col_names, inplace=True)
        new_g_builds = pandas.merge(
            gen_build_df, proj_info_df[['PROJECT', 'proj_gen_tech', 'proj_load_zone']],
            on='proj_gen_tech')
        # Factor in the load zone cost multipliers
        new_g_builds = pandas.merge(
            load_zone_df[['LOAD_ZONE', 'lz_cost_multipliers']], new_g_builds,
            left_on='LOAD_ZONE', right_on='proj_load_zone', how='right')
        new_g_builds['proj_overnight_cost.default'] *= new_g_builds['lz_cost_multipliers']
        new_g_builds['proj_fixed_om.default'] *= new_g_builds['lz_cost_multipliers']
        # Clean up
        for drop_col in ['LOAD_ZONE', 'proj_gen_tech', 'proj_load_zone',
                         'lz_cost_multipliers']:
            del new_g_builds[drop_col]

        # Merge the expanded gen_new_build_costs data into proj_build_costs
        project_build_path = os.path.join(inputs_dir, 'proj_build_costs.tab')
        if os.path.isfile(project_build_path):
            project_build_df = pandas.read_csv(project_build_path, na_values=['.'], sep='\t')
            project_build_df = pandas.merge(project_build_df, new_g_builds,
                                             on=['PROJECT', 'build_year'], how='outer')
        else:
            # Make sure the order of the columns is ok since merge won't ensuring that.
            idx_cols = ['PROJECT', 'build_year']
            dat_cols = [c for c in new_g_builds if c not in idx_cols]
            col_order = idx_cols + dat_cols
            project_build_df = new_g_builds[col_order]
        columns_with_defaults = ['proj_overnight_cost', 'proj_fixed_om', 
                                 'proj_storage_energy_overnight_cost']
        update_cols_with_defaults(project_build_df, columns_with_defaults)
        project_build_df.to_csv(project_build_path, sep='\t', na_rep='.', index=False)
        os.remove(gen_build_path)

    # Merge gen_inc_heat_rates.tab into proj_inc_heat_rates.tab
    g_hr_path = os.path.join(inputs_dir, 'gen_inc_heat_rates.tab')
    if os.path.isfile(g_hr_path):
        g_hr_df = pandas.read_csv(g_hr_path, na_values=['.'], sep='\t')
        proj_hr_default = pandas.merge(g_hr_df, proj_info_df[['PROJECT', 'proj_gen_tech']],
                                       left_on='generation_technology',
                                       right_on='proj_gen_tech')
        col_renames = {
            'PROJECT': 'project',
            'power_start_mw': 'power_start_mw.default',
            'power_end_mw': 'power_end_mw.default',
            'incremental_heat_rate_mbtu_per_mwhr': 'incremental_heat_rate_mbtu_per_mwhr.default',
            'fuel_use_rate_mmbtu_per_h': 'fuel_use_rate_mmbtu_per_h.default'
        }
        proj_hr_default.rename(columns=col_renames, inplace=True)
        proj_hr_path = os.path.join(inputs_dir, 'proj_inc_heat_rates.tab')
        if os.path.isfile(proj_hr_path):
            proj_hr_df = pandas.read_csv(proj_hr_path, na_values=['.'], sep='\t')
            proj_hr_df = pandas.merge(proj_hr_df, proj_hr_default, on='proj_gen_tech', how='left')
        else:
            proj_hr_df = proj_hr_default
        columns_with_defaults = ['power_start_mw', 'power_end_mw',
                                 'incremental_heat_rate_mbtu_per_mwhr',
                                 'fuel_use_rate_mmbtu_per_h']
        update_cols_with_defaults(proj_hr_df, columns_with_defaults)
        cols = ['project', 'power_start_mw', 'power_end_mw',
                'incremental_heat_rate_mbtu_per_mwhr', 'fuel_use_rate_mmbtu_per_h']
        proj_hr_df.to_csv(proj_hr_path, sep='\t', na_rep='.', index=False, columns=cols)
        os.remove(g_hr_path)
    
    # Done with restructuring. Now apply component renaming.
    
    old_new_file_names = {
        'proj_existing_builds.tab':'gen_build_predetermined.tab',
        'project_info.tab':'generation_projects_info.tab',
        'proj_build_costs.tab':'gen_build_costs.tab',
        'proj_inc_heat_rates.tab':'gen_inc_heat_rates.tab',
        'hydro_projects.tab':'hydro_generation_projects.tab',
        'lz_peak_loads.tab':'zone_coincident_peak_demand.tab',
        'lz_to_regional_fuel_market.tab':'zone_to_regional_fuel_market.tab'
    }
    
    for old, new in old_new_file_names.iteritems():
        rename_file(old, new)
    
    old_new_column_names_in_file = {
        'gen_build_predetermined.tab':[
        ('proj_existing_cap','gen_predetermined_cap')
        ],
        'gen_build_costs.tab':[
        ('proj_overnight_cost','gen_overnight_cost'),
        ('proj_fixed_om','gen_fixed_om'),
        ('proj_storage_energy_overnight_cost','gen_storage_energy_overnight_cost')
        ],
        'generation_projects_info.tab':[
        ('proj_dbid','gen_dbid'),('proj_gen_tech','gen_tech'),
        ('proj_load_zone','gen_load_zone'),
        ('proj_connect_cost_per_mw','gen_connect_cost_per_mw'),
        ('proj_capacity_limit_mw','gen_capacity_limit_mw'),
        ('proj_variable_om','gen_variable_om'),
        ('proj_max_age','gen_max_age'),
        ('proj_min_build_capacity','gen_min_build_capacity'),
        ('proj_scheduled_outage_rate','gen_scheduled_outage_rate'),
        ('proj_forced_outage_rate','gen_forced_outage_rate'),
        ('proj_is_variable','gen_is_variable'),
        ('proj_is_baseload','gen_is_baseload'),
        ('proj_is_cogen','gen_is_cogen'),
        ('proj_energy_source','gen_energy_source'),
        ('proj_full_load_heat_rate','gen_full_load_heat_rate'),
        ('proj_storage_efficiency','gen_storage_efficiency'),
        ('proj_min_load_fraction','gen_min_load_fraction'),
        ('proj_startup_fuel','gen_startup_fuel'),
        ('proj_startup_om','gen_startup_om'),
        ('proj_min_uptime','gen_min_uptime'),
        ('proj_min_downtime','gen_min_downtime'),
        ('proj_min_commit_fraction','gen_min_commit_fraction'),
        ('proj_max_commit_fraction','gen_max_commit_fraction'),
        ('proj_min_load_fraction_TP','gen_min_load_fraction_TP'),
        ('proj_unit_size','gen_unit_size')
        ],
        'loads.tab':[
        ('lz_demand_mw','zone_demand_mw')
        ],
        'zone_coincident_peak_demand.tab':[
        ('peak_demand_mw','zone_expected_coincident_peak_demand')
        ],
        'variable_capacity_factors.tab':[
        ('proj_max_capacity_factor','gen_max_capacity_factor')
        ]
    }
    
    for fname, old_new_pairs in old_new_column_names_in_file.iteritems():
        for old_new_pair in old_new_pairs:
            old = old_new_pair[0]
            new = old_new_pair[1]
            rename_column(fname, old_col_name=old, new_col_name=new)

    # Write a new version text file.
    switch_model.upgrade._write_input_version(inputs_dir, upgrades_to)
