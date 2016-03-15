import os
from pyomo.environ import *
from switch_mod import timescales

def define_components(m):
    
    m.ev_gwh_annual = Param(m.LOAD_ZONES, m.PERIODS, default=0.0)
    
    # TODO: calculate these data better and get them from a database
    # total miles traveled by vehicle fleet (assuming constant at Oahu's 2007 level from http://honolulucleancities.org/vmt-reduction/ )
    total_vmt = 13142000*365
    # annual vehicle miles per vehicle (HI avg from http://www.fhwa.dot.gov/ohim/onh00/onh2p11.htm)
    vmt_per_vehicle = 11583
    ev_vmt_per_kwh = 4.0    # from MF's LEAF experience
    ice_vmt_per_mmbtu = (40.0 / 114000.0) * 1e6   # assuming 40 mpg @ 114000 Btu/gal gasoline
    ice_fuel_market = 'Hawaii_Diesel' # we assume gasoline for the ICE vehicles costs the same as diesel
                        # note: this is the utility price, which is actually lower than retail gasoline
    ice_fuel_tier = 'base'

    # extra (non-fuel) annual cost of owning an EV vs. conventional vehicle (mostly for batteries)
    ev_extra_vehicle_cost_per_year = 1000.0
    
    m.ev_vmt_annual = Param(m.LOAD_ZONES, m.PERIODS, initialize=lambda m, z, p:
        m.ev_gwh_annual[z, p] * 1e6 * ev_vmt_per_kwh
    )
    m.ev_count = Param(m.LOAD_ZONES, m.PERIODS, initialize=lambda m, z, p:
        m.ev_vmt_annual[z, p] / vmt_per_vehicle
    )

    # calculate the extra annual cost (non-fuel) of all EVs, relative to ICEs
    m.ev_extra_annual_cost = Param(m.PERIODS, initialize=lambda m, p:
        sum(ev_extra_vehicle_cost_per_year * m.ev_count[z, p] for z in m.LOAD_ZONES)
    )

    # calculate total fuel cost for ICE (non-EV) VMTs
    m.ice_fuel_cost = Param(m.PERIODS, initialize=lambda m, p:
        sum(
            (total_vmt - m.ev_vmt_annual[z, p]) / ice_vmt_per_mmbtu * m.rfm_supply_tier_cost[ice_fuel_market, p, ice_fuel_tier]
            for z in m.LOAD_ZONES
        )
    )
        
    # add cost components to account for the vehicle miles traveled via EV or ICE
    # (not used because it interferes with calculation of cost per kWh for electricity)
    # m.cost_components_annual.append('ev_extra_annual_cost')
    # m.cost_components_annual.append('ice_fuel_cost')

    # calculate the amount of EV energy to provide during each timeseries
    # (assuming that total EV energy requirements are the same every day)
    m.ev_mwh_ts = Param(m.LOAD_ZONES, m.TIMESERIES, initialize=lambda m, z, ts:
        m.ev_gwh_annual[z, m.ts_period[ts]] * 1000.0 * m.ts_duration_hrs[ts] / timescales.hours_per_year
    )

    # decide when to provide the EV energy
    m.ChargeEVs = Var(m.LOAD_ZONES, m.TIMEPOINTS, within=NonNegativeReals)
    
    # make sure to charge all EVs
    # NOTE: prior to 2016-01-14, this failed to account for multi-hour timepoints,
    # so, e.g., it would double the average load if the timepoints were 2 hours long
    m.ChargeEVs_min = Constraint(m.LOAD_ZONES, m.TIMESERIES, rule=lambda m, z, ts:
        sum(m.ChargeEVs[z, tp] for tp in m.TS_TPS[ts]) * m.ts_duration_of_tp[ts] 
        == m.ev_mwh_ts[z, ts]
    )

    # add the EV load to the model's energy balance
    m.LZ_Energy_Components_Consume.append('ChargeEVs')
    
    
    

def load_inputs(m, switch_data, inputs_dir):
    """
    Import ev data from a .tab file. 
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'ev_energy.tab'),
        auto_select=True,
        param=(m.ev_gwh_annual))
