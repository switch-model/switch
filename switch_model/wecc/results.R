rm(list = ls())

# change for your run's directory:
setwd("/Users/pehidalg/Documents/20170607_CEC2050_v0_a1/10_17_validation_id20_STORAGE_rps_biomass/outputs")
library("ggplot2")

dispatch <- read.csv("./dispatch.txt",stringsAsFactors=F, header = T , fill = TRUE, sep = "\t", quote = "\"", dec = ".")
dispatch$DispatchGen_in_yr <- dispatch$DispatchGen * dispatch$tp_weight_in_year

dispatch_period_gen_tech <- aggregate(dispatch$DispatchGen_in_yr, by=list(dispatch$gen_tech, dispatch$tp_period), FUN=sum)

dispatch_period_energy_source <- aggregate(dispatch$DispatchGen_in_yr, by=list(dispatch$gen_energy_source, dispatch$tp_period), FUN=sum)
names(dispatch_period_energy_source)[1]<-'gen_energy_source'
names(dispatch_period_energy_source)[2]<-'period'
names(dispatch_period_energy_source)[3]<-'Gen_MWh_yr'

tot_MWh_per_period <- aggregate(dispatch_period_energy_source$Gen_MWh_yr, 
                                by = list(dispatch_period_energy_source$period),
                                FUN=sum, na.rm=TRUE)
names(tot_MWh_per_period)[1] <- 'period'
names(tot_MWh_per_period)[2] <- 'MWh'

dispatch_energy_source_2020 <- subset(dispatch_period_energy_source, dispatch_period_energy_source$period==2020)
dispatch_energy_source_2030 <- subset(dispatch_period_energy_source, dispatch_period_energy_source$period==2030)
dispatch_energy_source_2040 <- subset(dispatch_period_energy_source, dispatch_period_energy_source$period==2040)
dispatch_energy_source_2050 <- subset(dispatch_period_energy_source, dispatch_period_energy_source$period==2050)

# adding percentages column to then plot
dispatch_energy_source_2020$percentage <- dispatch_energy_source_2020$Gen_MWh_yr / subset(tot_MWh_per_period$MWh, tot_MWh_per_period$period == 2020)*100
dispatch_energy_source_2030$percentage <- dispatch_energy_source_2030$Gen_MWh_yr / subset(tot_MWh_per_period$MWh, tot_MWh_per_period$period == 2030)*100
dispatch_energy_source_2040$percentage <- dispatch_energy_source_2040$Gen_MWh_yr / subset(tot_MWh_per_period$MWh, tot_MWh_per_period$period == 2040)*100
dispatch_energy_source_2050$percentage <- dispatch_energy_source_2050$Gen_MWh_yr / subset(tot_MWh_per_period$MWh, tot_MWh_per_period$period == 2050)*100


