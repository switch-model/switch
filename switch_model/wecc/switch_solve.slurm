#!/bin/sh

# To submit this file, use: `sbatch switch_solve.slurm`

# Job label
#SBATCH --job-name=switch-solve
# Account:
#SBATCH --account=fc_switch
# Queue:
#SBATCH --partition=savio
# Wall clock limit:
#SBATCH --time=01:00:00
# Num nodes
#SBATCH --nodes=1
# Tasks per node
#SBATCH --ntasks-per-node=1
# CPU's per task
#SBATCH --cpus-per-task=1
# Email notification
#SBATCH --mail-type=all
##SBATCH --mail-user= patricia.hidalgo.g@berkeley.edu
# Node requirements
#SBATCH --mem-per-cpu=30G
# Log file paths
#SBATCH --output=logs/load_solve-%j.log
#SBATCH --error=logs/load_solve-%j.err
# Export all my environment variables to the job.
#SBATCH --export=ALL

cd /global/home/users/phidalgo/switch/20170607_CEC2050_v0_a1/switch_source/
source venv/bin/activate
cd ..
cd 06_15_full/
switch solve --verbose --log-run --solver=cplex --solver-io=nl --solver-options-string="iisfind=1" --suffixes iis
deactivate
