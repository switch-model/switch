class ScenarioParams:
    def __init__(self, scenario_id=None):
        # This list of attributes defines the columns that we query from the database.
        # Therefore attribute names matter!
        self.scenario_id = scenario_id
        self.name = None
        self.description = None
        self.study_timeframe_id = None
        self.time_sample_id = None
        self.demand_scenario_id = None
        self.fuel_simple_price_scenario_id = None
        self.generation_plant_scenario_id = None
        self.generation_plant_cost_scenario_id = None
        self.generation_plant_existing_and_planned_scenario_id = None
        self.hydro_simple_scenario_id = None
        self.carbon_cap_scenario_id = None
        self.supply_curves_scenario_id = None
        self.regional_fuel_market_scenario_id = None
        self.rps_scenario_id = None
        self.enable_dr = None
        self.enable_ev = None
        self.transmission_base_capital_cost_scenario_id = None
        self.ca_policies_scenario_id = None
        self.enable_planning_reserves = None
        self.generation_plant_technologies_scenario_id = None
        self.variable_o_m_cost_scenario_id = None
        self.wind_to_solar_ratio = None


def load_scenario_from_config(config, db_cursor) -> ScenarioParams:
    config = config["get_inputs"]  # Only keep the config that matters

    # Create the ScenarioParams object
    params = ScenarioParams(scenario_id=config["scenario_id"])
    param_names = list(params.__dict__.keys())
    print(param_names)

    # Read from the database all the parameters.
    db_cursor.execute(
        f"""SELECT {",".join(param_names)}
            FROM scenario
            WHERE scenario_id = {params.scenario_id};"""
    )
    db_values = list(db_cursor.fetchone())

    # Allow overriding from config
    for i, param_name in enumerate(param_names):
        value = config[param_name] if param_name in config else db_values[i]
        if value == -1:
            value = None
        setattr(params, param_name, value)

    return params
