#!/bin/sh

# To submit this file, use: `sbatch switch_solve.slurm`

# Job label
#SBATCH --job-name=switch-solve
# Account:
#SBATCH --account=fc_switch
# Queue:
#SBATCH --partition=savio2_htc
# Wall clock limit:
#SBATCH --time=24:00:00
# Num nodes
#SBATCH --nodes=1
# Tasks per node
#SBATCH --ntasks-per-node=1
# CPU's per task
#SBATCH --cpus-per-task=6
# Email notification
#SBATCH --mail-type=all
#SBATCH --mail-user=patricia.hidalgo.g@berkeley.edu
# Node requirements
#SBATCH --mem-per-cpu=20G
# Log file paths
#SBATCH --output=logs/load_solve-%j.log
#SBATCH --error=logs/load_solve-%j.err
# Export all my environment variables to the job.
#SBATCH --export=ALL

run_dir=$PWD

module load python/2.7.8
module load virtualenv
module load pip numpy pandas
module add ipython/2.3.0
module add scipy/0.14.0
# module add ply
pip install ply==3.8
module add nose/1.3.4 
module add six/1.8.0


cd /global/home/users/phidalgo/switch/20170607_CEC2050_v0_a1/switch_source/
source venv/bin/activate
cd ..
cd $run_dir
#switch solve --verbose --log-run --solver=cplex --export-all --solver-io=nl --solver-options-string="iisfind=1" --suffixes iis
switch solve --verbose --log-run --solver=cplex --export-all
deactivate
