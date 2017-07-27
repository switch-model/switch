#!/bin/sh

# To submit this file, use: `sbatch switch_stochastic_solve.slurm`

# Job label
#SBATCH --job-name=switch-solve
# Account:
#SBATCH --account=fc_switch
# Queue:
#SBATCH --partition=savio_bigmem
# Wall clock limit:
#SBATCH --time=72:00:00
# Num nodes
#SBATCH --nodes=1
# Tasks per node
#SBATCH --ntasks-per-node=1
# CPU's per task
#SBATCH --cpus-per-task=5
# Email notification
#SBATCH --mail-type=all
#SBATCH --mail-user=patricia.hidalgo.g@berkeley.edu
# Node requirements
#SBATCH --mem-per-cpu=70G
# Log file paths
#SBATCH --output=logs/load_solve-%j.log
#SBATCH --error=logs/load_solve-%j.err
# Export all my environment variables to the job.
#SBATCH --export=ALL

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
cd 27_stochastic_full_savio_print_results/
runef --model-directory=. --instance-directory=inputs/pysp_inputs --solve \
        --solver=cplexamp --output-solver-log --output-times --traceback \
        --solution-writer=pyomo.pysp.plugins.csvsolutionwriter \
        --solution-writer=switch_model.wecc.pyspsolutionwritertemplate
