This example is based on the carbon_cap case, but tightens the cap to near
zero in 2020 and zero in 2030. It also restricts some firm options and winter
availability from renewables, which makes conditions favorable for hydrogen
storage.

The natural-gas CC power plants have been converted to run on natural gas or
hydrogen (gen_energy_source in gen_info.csv is set to "multiple") and two
fuel-cell options have been added in the N and S regions.

The switch_model.energy_sources.hydrogen module was added to modules.txt to
enable production of hydrogen from electricity. Cost and efficiency parameters for
hydrogen production equipment are in inputs/hydrogen.csv.

"Hydrogen" was also added to inputs/fuels.csv with zero emissions and to
inputs/fuel_costs.csv with a zero cost. This means no cost is added on top of
the cost of building and operating the hydrogen production equipment, already
represented in the hydrogen production module.
