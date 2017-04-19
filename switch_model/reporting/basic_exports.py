# Copyright (c) 2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
This module enables exporting basic plots and tables with processed information.

"""
import switch_model.reporting as export
import pandas as pd
import os, time, sys
from csv import reader
from itertools import cycle
from pyomo.environ import Var
from switch_model.financials import uniform_series_to_present_value, future_to_present_value

def define_arguments(argparser):
    # argparser.add_argument(
    #     "--export-marginal-costs", action='store_true', default=False,
    #     help="Exports energy marginal costs in US$/MWh per load zone and timepoint, calculated as dual variable values from the energy balance constraint."
    # )
    argparser.add_argument(
        "--export-capacities", action='store_true', default=False,
        help="Exports cummulative installed generating capacity in MW per \
        technology per period."
    )
    argparser.add_argument(
        "--export-transmission", action='store_true', default=False,
        help="Exports cummulative installed transmission capacity in MW per \
        path per period."
    )
    argparser.add_argument(
        "--export-tech-dispatch", action='store_true', default=False,
        help="Exports dispatched capacity per generator technology in MW per \
        timepoint."
    )
    argparser.add_argument(
        "--export-reservoirs", action='store_true', default=False,
        help="Exports final reservoir volumes in cubic meters per timepoint."
    )
    argparser.add_argument(
        "--export-all", action='store_true', default=False,
        help="Exports all tables and plots. Sets all other export options to \
        True."
    )
    argparser.add_argument(
        "--export-load-blocks", action='store_true', default=False,
        help="Exports tables and plots for load block formulation."
    )


def post_solve(mod, outdir):
    """
    This module's post solve function calls the plot_inv_decision and
    plot_dis_decision functions to write and plot different outputs.
    
    plot_inv_decision should be used when the quantity is indexed by periods
    
    plot_dis_decision should be used when the quantity is indexed by timepoints
    
    """
    # Import optional dependencies here instead of at the top of the file to
    # avoid breaking tests for installations that don't use this functionality
    import matplotlib.pyplot as plt
    from numpy import nan
    from cycler import cycler
    from matplotlib.backends.backend_pdf import PdfPages

    summaries_dir = os.path.join(outdir,"Summaries")
    if not os.path.exists(summaries_dir):
        os.makedirs(summaries_dir)
    else:
        print "Summaries directory exists, clearing it..."
        for f in os.listdir(summaries_dir):
            os.unlink(os.path.join(summaries_dir, f))
            
    color_map = plt.get_cmap('gist_rainbow')
    styles = cycle(['-','--','-.',':'])

    #####
    # Round doubles to the first decimal
    #for var in mod.component_objects():
    #    if not isinstance(var, Var):
    #        continue
    #    for key, obj in var.items():
    #        obj.value = round(obj.value,1)
    #    print "Finished rounding variable "+str(var)

    def plot_inv_decision(name, tab, n_data, ind, by_period):
        """
        This function plots an investment decision over all periods on a
        bar plot.
        
        Arguments are:
        
        name: Filename for the output pdf.
        
        tab: Table of data. Format should be a list of lists whose first
        row (the first list) contains column names.
        
        n_data: Number of records to plot. Used to cycle through colors and
        linestyles to differenciate different variables.
        
        ind: Name of the column to be used as index when transforming the
        table into a Pandas Dataframe. Usually represents time.
        
        by_period: A boolean indicating whether the plot should be stacked
        by period (False) or if values should be cummulative (True). In the
        former, x axis represents the investment alternatives and in the
        latter, it represents periods (hence he boolean values required).
        
        """
        if by_period:
            df = pd.DataFrame(tab[1:], 
                columns = tab[0]).set_index(ind).transpose()
            stack = False
            num_col = int(n_data)/10
        else:
            df = pd.DataFrame(tab[1:], columns = tab[0]).set_index(ind)
            stack = True
            num_col = int(n_data)/2
        fig = plt.figure()
        inv_ax = fig.add_subplot(111)
        inv_ax.grid(b=False)
        # You have to play with the color map and the line style list to 
        # get enough combinations for your particular plot
        inv_ax.set_prop_cycle(cycler('color',
                        [color_map(i/n_data) for i in range(0, n_data+1)]))
        # To locate the legend: "loc" is the point of the legend for which you
        # will specify coordinates. These coords are specified in 
        # bbox_to_anchor (can be only 1 point or couple)        
        inv_plot = df.plot(kind='bar', ax=inv_ax, 
            stacked=stack).legend(loc='lower left', fontsize=8, 
            bbox_to_anchor=(0.,1.015,1.,1.015), ncol=num_col, mode="expand")
        if by_period:
            plt.xticks(rotation=0, fontsize=10)
            fname = summaries_dir+'/'+name+'.pdf'
        else:
            plt.xticks(rotation=90, fontsize=9)
            fname = summaries_dir+'/'+name+'_stacked_by_p.pdf'
        plt.savefig(fname, bbox_extra_artists=(inv_plot,), bbox_inches='tight')
        plt.close()

    def plot_dis_decision(name, tab, n_data, ind):
        """
        This function prints a pdf with dispatch decisions plotted over all 
        periods on a line plot and also a close up of each period on the
        subsequent pages of the file.
        
        Arguments are:
        
        name: Filename for the output pdf.
        
        tab: Table of data. Format should be a list of lists whose first
        row (the first list) contains column names.
        
        n_data: Number of records to plot. Used to cycle through colors and
        linestyles to differenciate different variables.
        
        ind: Name of the column to be used as index when transforming the
        table into a Pandas Dataframe. Usually represents time. 
        
        """
        
        plots = PdfPages(os.path.join(outdir,"Summaries",name)+'.pdf')
        
        df = pd.DataFrame(tab[1:], columns = tab[0])
        
        n_scen = mod.SCENARIOS.__len__()
        #num_col = int(n_data * n_scen)/8
        num_col = 6
        
        for p in ['all']+[p for p in mod.PERIODS]:
            fig = plt.figure(figsize=(17,8), dpi=100)
            dis_ax = fig.add_subplot(111)
            dis_ax.grid(b=False)
            # You have to play with the color map and the line style list to 
            # get enough combinations for your particular plot.
            # Set up different x axis labels if all periods are being plotted
            if p == 'all':
                dis_ax.set_xticks([i*24 
                    for i in range(0,len(mod.TIMEPOINTS)/24+1)])
                dis_ax.set_xticklabels([mod.tp_timestamp[mod.TIMEPOINTS[i*24+1]]
                    for i in range(0,len(mod.TIMEPOINTS)/24)])
                # Technologies have different linestyles and scenarios have 
                # different colors
                dis_ax.set_prop_cycle(cycler('color',
                    [color_map(i/float(n_data-1)) for i in range(n_data)]) * 
                    cycler('linestyle',[next(styles) for i in range(n_scen)]))
                df_to_plot = df.drop([ind], axis=1).replace('', nan)
            else:
                n_scen = mod.PERIOD_SCENARIOS[p].__len__()
                dis_ax.set_xticks([i*6 for i in range(0,len(mod.PERIOD_TPS[p])/6+1)])
                dis_ax.set_xticklabels([mod.tp_timestamp[mod.PERIOD_TPS[p][t*6+1]] 
                    for t in range(0,len(mod.PERIOD_TPS[p])/6)])
                # Technologies have different colors and scenarios have 
                # different line styles                
                dis_ax.set_prop_cycle(cycler('color',
                    [color_map(i/float(n_data-1)) for i in range(n_data)]) * 
                    cycler('linestyle', [next(styles) for i in range(n_scen)]))
                # Before plotting, data must be filtered by period
                period_tps = [mod.tp_timestamp[tp] 
                            for tp in mod.PERIOD_TPS[p].value]
                df_to_plot = df.loc[df[ind].isin(period_tps)].drop([ind], 
                    axis=1).reset_index(drop=True).dropna(axis=1, how='all')
            # To locate the legend: "loc" is the point of the legend for which 
            # you will specify coordinates. These coords are specified in 
            # bbox_to_anchor (can be only 1 point or couple)        
            dis_plot = df_to_plot.plot(ax=dis_ax,
                linewidth=1.6).legend(loc='lower left', fontsize=8,
                bbox_to_anchor=(0., 1.015, 1., 1.015), ncol=num_col, 
                mode="expand")
            plt.xticks(rotation=90, fontsize=9)
            plots.savefig(bbox_extra_artists=(dis_plot,), bbox_inches='tight')
            plt.close()
        plots.close()

    print "Printing summaries:\n==================="
    start=time.time()

    # print "renewable energy production"
    # rpsenergy = {s:0.0 for s in mod.SCENARIOS}
    # renergy = {s:0.0 for s in mod.SCENARIOS}
    # energy = {s:0.0 for s in mod.SCENARIOS}
    # for s in mod.SCENARIOS:
    #     for tp in mod.PERIOD_TPS[mod.scenario_period[s]]:
    #         for pr in mod.ERNC_ACTIVE_IN_TP[tp]:
    #             rpsenergy[s] += mod.DispatchProj[pr,tp,s].value*mod.tp_weight[tp] / 1000000.0
    #         for pr in mod.ERNC_ACTIVE_IN_TP1[tp]:
    #             renergy[s] += mod.DispatchProj[pr,tp,s].value*mod.tp_weight[tp] / 1000000.0
    #         for pr in mod.PROJECTS_ACTIVE_IN_TIMEPOINT[tp]:
    #             energy[s] += mod.DispatchProj[pr,tp,s].value*mod.tp_weight[tp]/1000000.0
    # with open(os.path.join(summaries_dir, "rps.tab"),'w') as f:
    #     for p in mod.PERIODS:
    #         ener = sum(energy[s]*mod.scenario_probability[s] for s in mod.PERIOD_SCENARIOS[p])
    #         rpsener = sum((rpsenergy[s]/energy[s]*100.0)*mod.scenario_probability[s] for s in mod.PERIOD_SCENARIOS[p])
    #         rener = sum((renergy[s]/energy[s]*100.0)*mod.scenario_probability[s] for s in mod.PERIOD_SCENARIOS[p])
    #         f.write("Period %s expected: Total - %10.1f TWh // %3.2f ERNC // %3.2f Renewable\n" % (p,ener,rpsener,rener))
    #     for s in mod.SCENARIOS:
    #         f.write("Scen %s: Total - %10.1f TWh // %3.2f ERNC // %3.2f Renewable\n" % (s,energy[s],rpsenergy[s]/energy[s]*100, renergy[s]/energy[s]*100.0))
    
    if mod.options.export_all:
        mod.options.export_reservoirs = True
        mod.options.export_tech_dispatch = True
        mod.options.export_capacities = True
        mod.options.export_transmission = True 

    # table_name = "energy_by_gentech_periods"
    # print table_name+" ..."
    # table = export.write_table(
    #     mod, True, mod.SCENARIOS, mod.GENERATION_TECHNOLOGIES,
    #     output_file=os.path.join(summaries_dir, table_name+".csv"), 
    #     headings=("scenario", "gentech", "energy_produced_TWh"),
    #     values=lambda m, s, g: (s, g,
    #         sum(m.DispatchProj[pr,tp,s]*m.tp_weight[tp]
    #         for tp in m.PERIOD_TPS[m.scenario_period[s]]
    #             for pr in m.PROJECTS_ACTIVE_IN_TIMEPOINT[tp] 
    #                 if g==m.proj_gen_tech[pr])/1000000.0))      
    
    if mod.options.export_capacities:
        n_elements = mod.GENERATION_TECHNOLOGIES.__len__()
        index = 'gentech'
        
        table_name = "cummulative_capacity_by_tech_periods"
        print table_name+" ..."
        table = export.write_table(
            mod, mod.GENERATION_TECHNOLOGIES,
            output_file=os.path.join(summaries_dir, table_name+".csv"),
            headings=(index, 'legacy') + tuple(p 
                for p in mod.PERIODS),
            values=lambda m, gt: (gt, sum(m.BuildGen[g, bldyr] 
                for (g, bldyr) in m.GEN_BLD_YRS
                if m.gen_tech[g] == gt and bldyr not in m.PERIODS)) + 
            tuple( sum(m.GenCapacity[g, p] for g in m.GENERATION_PROJECTS 
                if m.gen_tech[g] == gt) for p in m.PERIODS))
        plot_inv_decision(table_name, table, n_elements, index, True)
        
        table_name = "capacity_installed_by_tech_periods"
        print table_name+" ..."
        table = export.write_table(
            mod, mod.GENERATION_TECHNOLOGIES,
            output_file=os.path.join(summaries_dir, table_name+".csv"),
            headings=(index, 'legacy') + tuple(p 
                for p in mod.PERIODS),
            values=lambda m, gt: (gt, sum(m.BuildGen[g, bldyr] 
                for (g, bldyr) in m.GEN_BLD_YRS
                if m.gen_tech[g] == gt and bldyr not in m.PERIODS)) + 
            tuple( sum(m.BuildGen[g, p] for g in m.GENERATION_PROJECTS 
                if m.gen_tech[g] == gt) for p in m.PERIODS))
        plot_inv_decision(table_name, table, n_elements, index, False)
    
    if mod.options.export_transmission:
        n_elements = mod.TRANSMISSION_LINES.__len__()
        index = 'path'
        
        table_name = "cummulative_transmission_by_path_periods"
        print table_name+" ..."
        table = export.write_table(
            mod, True, mod.TRANSMISSION_LINES,
            output_file=os.path.join(summaries_dir, table_name+".csv"),
            headings=(index, 'legacy') + tuple(p for p in mod.PERIODS),
            values=lambda m, tx: (tx, m.existing_trans_cap[tx]) + 
                tuple(m.TransCapacity[tx, p] for p in m.PERIODS))
        #plot_inv_decision(table_name, table, n_elements, index, True)
        
        table_name = "transmission_installation_by_path_periods"
        print table_name+" ..."
        table = export.write_table(
            mod, True, mod.TRANSMISSION_LINES,
            output_file=os.path.join(summaries_dir, table_name+".csv"),
            headings=(index, 'legacy') + tuple(p for p in mod.PERIODS),
            values=lambda m, tx: (tx, m.existing_trans_cap[tx]) + 
                tuple(m.BuildTrans[tx, p] for p in m.PERIODS))        
        plot_inv_decision(table_name, table, n_elements, index, False)
    
    
    if mod.options.export_tech_dispatch:
        n_elements = mod.GENERATION_TECHNOLOGIES.__len__() 
        index = 'timepoints'
        
        gen_projects = {}
        for g in mod.GENERATION_TECHNOLOGIES:    
            gen_projects[g] = []
            for prj in mod.PROJECTS:
                if mod.proj_gen_tech[prj]==g:
                    gen_projects[g].append(prj) 
        def print_dis(m, tp):
            tup = (m.tp_timestamp[tp],)
            for g in m.GENERATION_TECHNOLOGIES:
                for s in m.SCENARIOS:
                    if s in m.PERIOD_SCENARIOS[m.tp_period[tp]]:
                        tup += (sum(m.DispatchProj[proj, tp, s] for proj in gen_projects[g] if (proj,tp,s) in m.PROJ_DISPATCH_POINTS),)
                    else:
                        tup += ('',)
            return tup

        table_name = "dispatch_proj_by_tech_tps"
        print table_name+" ..."
        table = export.write_table(
            mod, True, mod.TIMEPOINTS,
            output_file=os.path.join(summaries_dir, table_name+".csv"),
            headings=("timepoints",) + tuple(str(g)+"-"+str(mod.scenario_stamp[s]) for g in mod.GENERATION_TECHNOLOGIES for s in mod.SCENARIOS),
            values=print_dis)
        plot_dis_decision(table_name, table, n_elements, index)
    
    if mod.options.export_reservoirs:
        n_elements = mod.RESERVOIRS.__len__()
        index = 'timepoints'
        
        def print_res(m, tp):
            tup = (m.tp_timestamp[tp],)
            for r in m.RESERVOIRS:
                for s in m.SCENARIOS:
                    if s in m.PERIOD_SCENARIOS[m.tp_period[tp]]:
                        tup += (m.ReservoirVol[r, tp, s] - m.initial_res_vol[r],)
                    else:
                        tup += ('',)
            return tup
        
        table_name = "reservoir_final_vols_tp"
        print table_name+" ..."
        table = export.write_table(
            mod, True, mod.TIMEPOINTS,
            output_file=os.path.join(summaries_dir, table_name+".csv"),
            headings=("timepoints",) + tuple(str(r)+"-"+
                str(mod.scenario_stamp[s]) for r in mod.RESERVOIRS 
                for s in mod.SCENARIOS),
            values=print_res)
        plot_dis_decision(table_name, table, n_elements, index) 
        
        ##############################################################
        # The following is a custom export to get dispatch for certain
        # Chile load zones
        lzs_to_print = ['charrua','ancoa']

        lz_hprojs = {}
        for lz in lzs_to_print:
            lz_hprojs[lz]=[]
            for proj in mod.LZ_PROJECTS[lz]:
                if proj in mod.HYDRO_PROJECTS:
                    lz_hprojs[lz].append(proj)

        def print_hgen(m, tp):
            tup = (m.tp_timestamp[tp],)
            for lz in lzs_to_print:
                for s in m.SCENARIOS:
                    if s in m.PERIOD_SCENARIOS[m.tp_period[tp]]:
                        tup += (sum(m.DispatchProj[proj, tp, s] for proj in lz_hprojs[lz] if (proj,tp,s) in m.HYDRO_PROJ_DISPATCH_POINTS),)
                    else:
                        tup += ('',)
            return tup

        table_name = "hydro_dispatch_special_nodes_tp"
        print table_name+" ..."
        table = export.write_table(
            mod, True, mod.TIMEPOINTS,
            output_file=os.path.join(summaries_dir, table_name+".csv"),
            headings=("timepoints",) + tuple(str(lz)+"-"+str(
                mod.scenario_stamp[s]) for lz in lzs_to_print 
                for s in mod.SCENARIOS),
            values=print_hgen)
        #plot_dis_decision(table_name, table, n_elements, index)
        
    if mod.options.export_load_blocks:
        def print_res(m, ym):
            tup = (ym,)
            for r in m.RESERVOIRS:
                for s in m.SCENARIOS:
                    if s in m.PERIOD_SCENARIOS[m.tp_period[next(iter(m.ym_timepoints[ym]))]]:
                        tup += (m.ReservoirVol[r, ym, s] - m.initial_res_vol[r],)
                    else:
                        tup += ('',)
            return tup
        table_name = "reservoir_vols_load_block"
        print table_name+" ..."
        tab = export.write_table(
            mod, True, mod.YEARMONTHS,
            output_file=os.path.join(summaries_dir, table_name+".csv"),
            headings=("yearmonth",) + tuple(str(r)+"-"+
                str(mod.scenario_stamp[s]) for r in mod.RESERVOIRS 
                for s in mod.SCENARIOS),
            values=print_res)
        n_data = mod.RESERVOIRS.__len__()
        ind = 'yearmonth'
        plots = PdfPages(os.path.join(outdir,"Summaries",table_name)+'.pdf')

        df = pd.DataFrame(tab[1:], columns = tab[0])

        n_scen = mod.SCENARIOS.__len__()
        #num_col = int(n_data * n_scen)/8
        num_col = 6

        for p in ['all']+[p for p in mod.PERIODS]:
            fig = plt.figure(figsize=(17,8), dpi=100)
            dis_ax = fig.add_subplot(111)
            dis_ax.grid(b=False)
            # You have to play with the color map and the line style list to 
            # get enough combinations for your particular plot.
            # Set up different x axis labels if all periods are being plotted
            if p == 'all':
                dis_ax.set_xticks([i*5
                    for i in range(0,len(mod.YEARMONTHS)/5+1)])
                dis_ax.set_xticklabels([mod.YEARMONTHS[i*5+1]
                    for i in range(0,len(mod.YEARMONTHS)/5)])
                # Technologies have different linestyles and scenarios have 
                # different colors
                dis_ax.set_prop_cycle(cycler('color',
                    [color_map(i/float(n_data-1)) for i in range(n_data)]) * 
                    cycler('linestyle',[next(styles) for i in range(n_scen)]))
                df_to_plot = df.drop([ind], axis=1).replace('', nan)
            else:
                n_scen = mod.PERIOD_SCENARIOS[p].__len__()
                dis_ax.set_xticks([i*5 for i in range(0,24)])
                dis_ax.set_xticklabels([mod.YEARMONTHS[i] 
                    for i in range(1,25)])
                # Technologies have different colors and scenarios have 
                # different line styles                
                dis_ax.set_prop_cycle(cycler('color',
                    [color_map(i/float(n_data-1)) for i in range(n_data)]) * 
                    cycler('linestyle', [next(styles) for i in range(n_scen)]))
                # Before plotting, data must be filtered by period
                period_yms = [(p+y)*100+i for y in [0,1] for i in range(1,13)]
                df_to_plot = df.loc[df[ind].isin(period_yms)].drop([ind], 
                    axis=1).reset_index(drop=True).dropna(axis=1, how='all')
            # To locate the legend: "loc" is the point of the legend for which 
            # you will specify coordinates. These coords are specified in 
            # bbox_to_anchor (can be only 1 point or couple)        
            dis_plot = df_to_plot.plot(ax=dis_ax,
                linewidth=1.6).legend(loc='lower left', fontsize=8,
                bbox_to_anchor=(0., 1.015, 1., 1.015), ncol=num_col, 
                mode="expand")
            plt.xticks(rotation=90, fontsize=9)
            plots.savefig(bbox_extra_artists=(dis_plot,), bbox_inches='tight')
            plt.close()
        plots.close()
    ##############################################################
    
    def calc_tp_costs_in_period_one_scenario(m, p, s):
        return (sum(sum(
            # This are total costs in each tp for a scenario
            getattr(m, tp_cost)[t, s].expr() * m.tp_weight_in_year[t]
                    for tp_cost in m.cost_components_tp)
                    # Now, summation over timepoints 
                        for t in m.PERIOD_TPS[p]) *
            # Conversion to lump sum at beginning of period
            uniform_series_to_present_value(
                0, m.period_length_years[p]) *
            # Conversion to base year
            future_to_present_value(
                m.discount_rate, (m.period_start[p] - m.base_financial_year)))

    """
    Writing Objective Function value.
    """
    print "total_system_costs.txt..."
    with open(os.path.join(summaries_dir, "total_system_costs.txt"),'w+') as f:
        f.write("Total Expected System Costs: %.2f \n" % mod.SystemCost())
        f.write("Total Investment Costs: %.2f \n" % sum(
            mod.AnnualCostPerPeriod[p].expr() for p in mod.PERIODS))
        f.write("Total Expected Operations Costs: %.2f \n" % sum(
            mod.TpCostPerPeriod[p].expr() for p in mod.PERIODS))
        for p in mod.PERIODS:
            f.write("PERIOD %s\n" % p)
            f.write("  Investment Costs: %.2f \n" % mod.AnnualCostPerPeriod[p].expr())    
            f.write("  Expected Operations Costs: %.2f \n" % mod.TpCostPerPeriod[p].expr())
            for s in mod.PERIOD_SCENARIOS[p]:
                f.write("    Operational Costs of scenario %s with probability %s: %.2f\n" % (s, mod.scenario_probability[s], calc_tp_costs_in_period_one_scenario(mod, p, s)))
  
    
    print "\nTime taken writing summaries: %.2f s." % (time.time()-start)



    # if mod.options.export_marginal_costs:
    #     """
    #     This table writes out the marginal costs of supplying energy in each timepoint in US$/MWh.
    #     """
    #     print "marginal_costs_lz_tp.csv..."
    #     export.write_table(
    #         mod, mod.TIMEPOINTS, mod.LOAD_ZONES,
    #         output_file=os.path.join(summaries_dir, "marginal_costs_lz_tp.csv"),
    #         headings=("timepoint","load_zones","marginal_cost"),
    #         values=lambda m, tp, lz: (m.tp_timestamp[tp], lz, m.dual[m.Energy_Balance[lz, tp]] / (m.tp_weight_in_year[tp] * uniform_series_to_present_value(
    #                 m.discount_rate, m.period_length_years[m.tp_period[tp]]) * future_to_present_value(
    #                 m.discount_rate, (m.period_start[m.tp_period[tp]] - m.base_financial_year)))
    #         ))
    #     df = pd.read_csv('outputs/Summaries/marginal_costs_lz_tp.csv',sep='\t')
    #     lz_dfs = []
    #     for lz in mod.LOAD_ZONES:
    #         lz_dfs.append(df[df.load_zones == lz].drop(['load_zones','timepoint'],axis=1).reset_index(drop=True))
    #         lz_dfs[-1].columns = [lz]
    #     DF = pd.concat(lz_dfs, axis=1)
    #     fig = plt.figure(1)
    #     mc_ax = fig.add_subplot(211)
    #     # GO cycling through the rainbow to get line colours
    #     cm = plt.get_cmap('gist_rainbow')
    #     # You have to play with the color map and the line style list to get enough combinations for your particular plot
    #     mc_ax.set_prop_cycle(cycler('linestyle',['-',':','--','-.']) * cycler('color',[cm(i/5.0) for i in range(0,6)]))
    #     # to locate the legend: "loc" is the point of the legend for which you will specify cooridnates. These coords are specified in bbox_to_anchor (can be only 1 point or couple)
    #     mc_plot = DF.plot(ax=mc_ax,linewidth=1.5).legend(loc='upper center', fontsize=10, bbox_to_anchor=(0.,-0.15,1.,-0.15), ncol=3, mode="expand")
    #     plt.xticks([i*24 for i in range(1,len(mod.TIMEPOINTS)/24+1)],[mod.tp_timestamp[mod.TIMEPOINTS[i*24]] for i in range(1,len(mod.TIMEPOINTS)/24+1)],rotation=40,fontsize=7)
    #     plt.savefig('outputs/Summaries/marginal_costs.pdf',bbox_extra_artists=(mc_plot,))

    # print "energy_produced_in_period_by_each_project.csv..."
    # export.write_table(
    #     mod, mod.PERIODS, mod.PROJECTS,
    #     output_file=os.path.join(summaries_dir, "energy_produced_in_period_by_each_project.csv"), 
    #     headings=("period", "project", "energy_produced_GWh"),
    #     values=lambda m, p, proj: (p, proj,) + tuple(
    #         sum(m.DispatchProj[proj,tp]*m.tp_weight[tp] for tp in m.PERIOD_TPS[p])/1000)
    #     )

    # """
    # This table writes out the fuel consumption in MMBTU per hour. 
    # """
    # print "fuel_consumption_tp_hourly.csv..."
    # export.write_table(
    #     mod, mod.TIMEPOINTS,
    #     output_file=os.path.join(summaries_dir, "fuel_consumption_tp_hourly.csv"),
    #     headings=("timepoint",) + tuple(f for f in mod.FUELS),
    #     values=lambda m, tp: (m.tp_timestamp[tp],) + tuple(
    #         sum(m.ProjFuelUseRate[proj, t, f] for (proj,t) in m.PROJ_WITH_FUEL_DISPATCH_POINTS 
    #             if m.g_energy_source[m.proj_gen_tech[proj]] == f and t == tp)
    #         for f in m.FUELS)
    #     )
    
    # """
    # This table writes out the fuel consumption in total MMBTU consumed in each period.
    # """
    # print "fuel_consumption_periods_total.csv..."
    # export.write_table(
    #     mod, mod.PERIODS,
    #     output_file=os.path.join(summaries_dir, "fuel_consumption_periods_total.csv"),
    #     headings=("period",) + tuple(f for f in mod.FUELS),
    #     values=lambda m, p: (p,) + tuple(
    #         sum(m.ProjFuelUseRate[proj, tp, f] * m.tp_weight[tp] for (proj, tp) in m.PROJ_WITH_FUEL_DISPATCH_POINTS 
    #             if tp in m.PERIOD_TPS[p] and m.g_energy_source[m.proj_gen_tech[proj]] == f)
    #         for f in m.FUELS)
    # )
