# wecc_2020inputs_update
Queries used to update inputs in 2020 for the WECC.

Overall steps to create baseline scenario:

1. Run scrape.py to scrape updated EIA data from EIA 860 and 923 forms

2. Run database_interface.py to clean scraped data and copy into database tables as scenario 19, and scenario 20 (aggregated generators by load zone)

3. Run the variable_capacity_factors function of database_interface.py as a set of sql queries run in a screen session (because this takes so long). This copies the variable capacity factors for the existing EIA generators into the variable_capacity_factors db table.

4. Run Query_to_add_Canada_Mexico_gen.sql to create a new set of scenarios 21 which is a combination of the set of existing and planned generators from the EIA 2020 update (non-aggregated) scenario 19 and the existing generators from AMPL for Canada and Mexico (from scenario 1) 

5. Run Query_to_copy_AMPL_Canada_Mex_attributes_to_new_gen_plant.sql to:

- copy the attributes from the old AMPL generation_plant_ids to a new set of generation_plant_ids for the new SWITCH baseline, for Canada and Mexico existing plants. Before running this script, create an Excel file that maps the new generation_plant_ids to the old generation_plant_ids that were copied. 

- Add in the capacity_mw values by generation_plant_id into the generation_plant table for the Canadian and Mexican existing generators that were added to the scenario, by summing the capacity across build_year for each generation_plant_id

- Make the overnight cost and variable O&m cost for existing generators = 0 (the ones added in from Canada and Mexico) to be consistent with the costs of existing generators added from EIA

6. Run Queries_to_copy_hydro_median_year_2010_2070.sql to copy the median year of hydropower capacity factors for each year of the simulation 2010 to 2070.
Do this by copying the sql file to db2 with rsync and then running the sql query from db2 as above. 

7. Run Add_proposed_generation_to_existing_gen.sql to create a new set of scenarios 22 which includes 
the existing and proposed generation from EIA and AMPL for Canada and Mexico (21) and adds candidate generators from prior scenario data (proposed non-wind plants and proposed wind plants from scenario 14).

8. Make a new backup table of generation_plant to preserve the new AMPL and EIA generation plants X

9. Run Standardize_gen_tech_names_between_EIA_and_AMPL_generators.sql to update the gen_tech of the EIA existing generators to match the gen_tech labels of the candidate generators (AMPL naming conventions)
- This runs the update statements to update the gen_tech for the generation_plant_ids that are in scenario 22 X
- This adds 2 columns to the generation_plant_technologies table to document the mapping from gen_tech to gen_tech_AMPL and energy_source_AMPL X

Cost updates: 

10. Run the Update_costs_for_baseline.sql script, which for all generators (in generation_plant scenario 22), updates the connect_cost_per_mw and variable_o_m from $2016 to $2018 dollars with CPI multiplier (x1.05). Some of the variable o_m costs will be updated based on the gen_tech, but this makes sure that the technologies that are not updated are in the correct $2018.

11. Make generation_plant_cost_scenario 23 a copy of the generation_plant_cost scenario 22 and update these overnight and fixed_o_m costs from $2016 to $2018 dollars with CPI multiplier: 
https://www.bls.gov/data/inflation_calculator.htm
- Multiply $2016 costs by 1.05

12. Create a new table baseline_2020_generation_plant_cost_update with the overnight costs and fixed_o_m by gen_tech and build_year for the technologies being updated: Battery_Storage, Wind, Central_PV, Commercial_PV, Residential_PV, CSP_Trough_6h_Storage, CCGT, Gas_Combustion_Turbine,Geothermal
- For the candidate generators only in scenario 23 (not in existing_and_planned scenario 22), join the generator_plant_ids that have matching gen_tech and build_year with the new overnight and fixed_o_m costs in baseline_2020_generation_plant_cost_update.
- Do this update for all generators named 'Proposed' with matching gen_tech
- Do this update for all named Wind candidate generators (gen_tech = wind but not in existing and planned scenarios, and not named 'proposed')

13. Update variable o_m costs by gen_tech for both existing and candidate generators. 
- Create a new variable_o_m_costs table with average variable_o_m costs by energy source and gen_tech from the prior CEC generator_plant scenario 14 as scenario 1 in $2016, and as scenario 2 in $2018 dollars
- Make a copy of scenario 2 as scenario 3, update the gen_tech names with the standardized set of names, and replace the variable_o_m costs from NREL ATB data in $2018 with the technologies being updated: Battery_Storage, Wind, Central_PV, Commercial_PV, Residential_PV, CSP_Trough_6h_Storage, CCGT, Gas_Combustion_Turbine,Geothermal
- Update the get_inputs.py script to query from the new variable_o_m_costs table instead of generation_plant to get the variable_o_m costs.

14. Copy the prior fuel costs scenario and update the costs from $2016 to $2018 dollars with CPI multiplier
- Update fuel_supply_curves:
Copy previous supply_curves_scenario_id 1 to supply_curves_scenario_id 2
In new supply_curves_scenario_id 2, multiply unit_cost column * 1.05 to $2018 dollars
- Update fuel_simple_prices_yearly:
Copy previous fuel_simple_scenario_id 3 to supply_curves_scenario_id 4
In new supply_curves_scenario_id 4, multiply fuel_price column * 1.05 to $2018 dollars

15. Copy the variable capacity factors from variable_capacity_factors_historical into variable_capacity_factors_existing_and_candidate table
- Make a copy of the variable_capacity_factors table as variable_capacity_factors_existing_and_candidate
- Run query to insert into variable_capacity_factors_existing_and_candidate the data from the variable_capacity_factors_historical table for candidate generators in scenario 22
- Update the get_inputs.py script to query the new variable_capacity_factors_existing_and_candidate table instead of variable_capacity_factors_historical

16. Update the transmission costs in get_inputs.py from $2016 to $2018 dollars with CPI multiplier
- Updated the transmission costs to $1208 per MW per km from the previous $1150 which was in $2016 (multiplied by 1.05 CPI multiplier)

17. Update both the discount and interest rate to 5%, and the base_financial_year to 2018 in get_inputs.py

18. Double check the carbon cap scenario to use: 
- Going to use the previous carbon_cap_scenario 90, where the WECC and CA have an 80% reduction by 2050

19. Run the make_new_rps_scenario.sql script to update the RPS scenario 1 to use 60% RPS in CA load zones by 2030 and beyond as a new scenario 6 to be consistent with SB 100: 44% by 2024, 47% by 2025, 50% by 2026, 52% by 2027, 55% for 2028, 27% by 2029, 60% by 2030
- Text of the SB100 bill is here: https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=201720180SB100 

20. Run the Make_new_baseline_scenario_id.sql script to create new scenario 171 (copy of scenario 147 but with updated components to match new scenario ids):
Gen_cost_scenario: 23
Gen_plant_scenario: 22
Gen_plant_existing_and_planned: 21
Hydro_simple: 22
Carbon_cap_scenario: 90 (same as before)
Rps_scenario: 6
Fuel_cost_scenario: 4
Supply_curve_scenario: 2
Run get_inputs.py with s=171

FUTURE REFINEMENT TO-DOs:

Will test a CA carbon cap of 100% reduction by 2045 in the future

Add fixed_o_m costs for all existing generators that should have had them (from EIA and AMPL data for Canada and Mexico)

