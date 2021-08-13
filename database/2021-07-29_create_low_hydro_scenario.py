"""
####################
Create a low hydro scenario

Date applied: 2021-07-29
Description:
This script adds a scenario to the database for low hydro power.
The worst year for hydro is 2015. As such we use those values for every year unless a plant is missing
in 2015 in which case we use the lowest value in the other years for that plant.
#################
"""
import time

from switch_model.utilities import query_yes_no, format_seconds
from switch_model.wecc.utilities import connect
import pandas as pd

raw_data_scenario = 21
all_plants_scenario = 23
worst_year = 2015

new_start_year = 2020
new_end_year = 2050
new_scenario_id = 24
new_scenario_name = "Lowest year (2015) repeated. Using EIA and AMPL Canada and Mex data."
new_scenario_description = "Lowest year (2015) repeated from 2020 to 2050, based on data from id 21 (EIA + AMPL Canada & Mex)."


def main():
    db_conn = connect()
    db_cursor = db_conn.cursor()

    # 1. Get all the hydro plants
    db_cursor.execute(
        f"""
        SELECT DISTINCT generation_plant_id FROM hydro_historical_monthly_capacity_factors
        WHERE hydro_simple_scenario_id={all_plants_scenario};
    """)
    hydro_plants = pd.DataFrame(db_cursor.fetchall(), columns=["generation_plant_id"])["generation_plant_id"]

    # 2. Get all the hydro flow data for the worst year
    db_cursor.execute(
        f"""
        SELECT generation_plant_id, month, hydro_min_flow_mw, hydro_avg_flow_mw FROM hydro_historical_monthly_capacity_factors
        WHERE hydro_simple_scenario_id={raw_data_scenario} and year={worst_year};
    """)
    worst_year_data = pd.DataFrame(db_cursor.fetchall(),
                                   columns=["generation_plant_id", "month", "hydro_min_flow_mw", "hydro_avg_flow_mw"])

    # 3. Identify plants where data is missing
    missing_hydro_plants = hydro_plants[~hydro_plants.isin(worst_year_data["generation_plant_id"])].values

    # 4. For each missing plant get the data for all the years
    db_cursor.execute(
        f"""
        SELECT generation_plant_id, year, month, hydro_min_flow_mw, hydro_avg_flow_mw FROM hydro_historical_monthly_capacity_factors
        WHERE hydro_simple_scenario_id={raw_data_scenario} and generation_plant_id in ({",".join(missing_hydro_plants.astype(str))});
    """)
    missing_plants_data = pd.DataFrame(db_cursor.fetchall(),
                                       columns=["generation_plant_id", "year", "month", "hydro_min_flow_mw",
                                                "hydro_avg_flow_mw"])

    # 5. Pick the year with the least flow
    # Aggregate by year
    missing_data_by_year = missing_plants_data.groupby(["generation_plant_id", "year"], as_index=False)[
        "hydro_avg_flow_mw"].mean()
    # Select years where the flow is at its lowest
    year_to_use = \
    missing_data_by_year.loc[missing_data_by_year.groupby("generation_plant_id")["hydro_avg_flow_mw"].idxmin()][
        ["generation_plant_id", "year"]]
    # Essentially filter missing_plants_data to only include keys from the right table, aka plants and years that are lowest
    missing_plants_data = missing_plants_data.merge(
        year_to_use,
        on=["generation_plant_id", "year"],
        how="right"
    ).drop("year", axis=1)

    # 6. Add the missing data to our worst year data and verify we have data for all the plants
    worst_year_data = pd.concat([worst_year_data, missing_plants_data])
    assert all(hydro_plants.isin(worst_year_data["generation_plant_id"]))

    # 7. Cross join the series with all the years from 2020 to 2050
    years = pd.Series(range(new_start_year, new_end_year + 1), name="year")
    worst_year_data = worst_year_data.merge(
        years,
        how="cross"
    )
    worst_year_data["hydro_simple_scenario_id"] = new_scenario_id

    # 8. Complete some data checks
    assert len(worst_year_data) == 12 * (new_end_year - new_start_year + 1) * len(hydro_plants)

    # 9. Add data to database
    print(f"hydro_simple_scenario: {new_scenario_id}")
    print(f"name: {new_scenario_name}")
    print(f"description: {new_scenario_description}")
    print(f"Num hydro plants: {worst_year_data.generation_plant_id.nunique()}")
    print(f"From year: {new_start_year}")
    print(f"To year: {new_end_year}")
    print(f"Example data:\n{worst_year_data.head()}")

    if not query_yes_no("\nAre you sure you want to add this data to the database?", default="no"):
        raise SystemExit

    db_cursor.execute(
        "INSERT INTO hydro_simple_scenario(hydro_simple_scenario_id, name, description) "
        f"VALUES ('{new_scenario_id}','{new_scenario_name}','{new_scenario_description}')"
    )

    n = len(worst_year_data)
    start_time = time.time()
    for i, r in enumerate(worst_year_data.itertuples(index=False)):
        if i !=0 and i % 1000 == 0:
            print(
                f"{i}/{n} inserts completed. Estimated time remaining {format_seconds((n - i) * (time.time() - start_time) / i)}")
        db_cursor.execute(
            f"INSERT INTO hydro_historical_monthly_capacity_factors(hydro_simple_scenario_id, generation_plant_id, year, month, hydro_min_flow_mw, hydro_avg_flow_mw) "
            f"VALUES ({r.hydro_simple_scenario_id},{r.generation_plant_id},{r.year},{r.month},{r.hydro_min_flow_mw},{r.hydro_avg_flow_mw})"
        )

    db_conn.commit()
    db_cursor.close()
    db_conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
