''' Calculate the MSD of the boomerang particles from their trajectory
data. After running a simulation with boomerang.py, the 
trajectory will be saved.  Analyze it with this script to create
a pkl file with MSD data.

example usage:

  python calculate_boomerang_msd_from_trajectories.py -dt 0.1 -N 100000 -scheme RFD 
              -n_runs 4 -gfactor 1 --data-name=example

This call would analyze trajectories from 4 runs performed with the
given parameters using --data-name=example-1 --data-name=example-2
--data-name=example-3 and --data-name=example-4.
'''

import argparse
import pickle
import cProfile
import logging
import numpy as np
import os
import pstats
import io
import sys
sys.path.append('..')

from . import boomerang as bm
from config_local import DATA_DIR
from quaternion_integrator.quaternion import Quaternion
from general_application_utils import MSDStatistics
from general_application_utils import calc_msd_data_from_trajectory
from general_application_utils import read_trajectory_from_txt
from general_application_utils import StreamToLogger

# Make sure data folder exists
if not os.path.isdir(os.path.join(os.getcwd(), 'data')):
  os.mkdir(os.path.join(os.getcwd(), 'data'))


def calc_boomerang_cp(location, orientation):
  ''' Function to get boomerang cross point, which is tracked as location.'''
  return location

def calc_boomerang_coh(location, orientation):
  ''' Function to get boomerang CoH, which is tracked as location.
  this is for the 15 blob boomerang.'''
  r_vectors = bm.get_boomerang_r_vectors_15(location, orientation)
  dist = 1.07489
  coh = (location + 
         np.cos(np.pi/4.)*(dist/2.1)*(r_vectors[0] - location) +
         np.sin(np.pi/4.)*(dist/2.1)*(r_vectors[14] - location))
  
  return coh

def calc_boomerang_cod(location, orientation):
  ''' Function to get boomerang CoD, which is tracked as location.
  this is for the 15 blob boomerang.'''
  r_vectors = bm.get_boomerang_r_vectors_15(location, orientation)
  dist = 0.96087
  coh = (location + 
         np.cos(np.pi/4.)*(dist/2.1)*(r_vectors[0] - location) +
         np.cos(np.pi/4.)*(dist/2.1)*(r_vectors[14] - location))
  
  return coh

def calc_boomerang_experimental(location, orientation):
  ''' Function to get boomerang CoH from the chakrabarty paper,
  which is tracked as location. this is for the 15 blob boomerang.'''
  r_vectors = bm.get_boomerang_r_vectors_15(location, orientation)
  dist = 1.16
  experiment_pt = (location + 
                   np.cos(np.pi/4.)*(dist/2.1)*(r_vectors[0] - location) +
                   np.cos(np.pi/4.)*(dist/2.1)*(r_vectors[14] - location))
  
  return experiment_pt


def calc_boomerang_tip(location, orientation):
  ''' Function to get boomerang cross point, which is tracked as location.'''
  r_vectors = bm.get_boomerang_r_vectors_15(location, orientation)
  tip = r_vectors[0]
  return tip


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Calculate rotation and '
                                   'translation MSD from a trajectory '
                                   'generated by boomerang.py. '
                                   'This assumes the data files are named '
                                   'similar to the following: \n '
                                   'boomerang-trajectory-dt-0.1-N-'
                                   '100000-scheme-RFD-g-2-example-name-#.txt\n'
                                   'where # ranges from 1 to n_runs. '
                                   'boomerang.py uses this '
                                   'convention.')
  parser.add_argument('-scheme', dest='scheme', type=str, default='RFD',
                      help='Scheme of data to analyze.  Options are '
                      'RFD, FIXMAN, or EM.  Defaults to RFD.')
  parser.add_argument('-free', dest='free', type=str, default='',
                      help='Is this boomerang free in 3 space, or confined '
                      'near a wall?')
  parser.add_argument('-dt', dest='dt', type=float,
                      help='Timestep of runs to analyze.')
  parser.add_argument('-N', dest='n_steps', type=int,
                      help='Number of steps taken in trajectory '
                      'data to be analyzed.')
  parser.add_argument('-gfactor', dest='gfactor', type=float,
                      help='Factor of earths gravity that simulation was '
                      'performed in.  For example, 2 will analyze trajectories '
                      'from simulations that  are performed in double '
                      'earth gravity.')
  parser.add_argument('--data-name', dest='data_name', type=str,
                      help='Data name of trajectory runs to be analyzed.')
  parser.add_argument('-n_runs', dest='n_runs', type=int,
                      help='Number of trajectory runs to be analyzed.')
  parser.add_argument('-point', dest='point', type=str, default = 'COH',
                      help='Point to use to measure translational MSD. Must be '
                      'COH, COD, CP, EXP, or TIP.')
  parser.add_argument('-end', dest='end', type=float,
                      help='How far to analyze MSD (how large of a time window '
                      'to use).  This is in the same time units as dt.')
  parser.add_argument('--out-name', dest='out_name', type=str, default='',
                      help='Optional output name to add to the output Pkl '
                      'file for organization.  For example could denote '
                      'analysis using cross point v. vertex.')
  parser.add_argument('--profile', dest='profile', type=bool, default=False,
                      help='True or False: Do we profile this run or not. '
                      'Defaults to False. Put --profile 1 to profile.')

  args=parser.parse_args()
  if args.profile:
    pr = cProfile.Profile()
    pr.enable()


  # List files here to process.  They must have the same timestep, etc..
  scheme = args.scheme
  dt = args.dt
  end = args.end
  N = args.n_steps
  data_name = args.data_name
  trajectory_length = 100

  if args.point not in ['COH', 'COD', 'TIP', 'CP', 'EXP']:
    raise Exception('Point must be one of: COH, COD, TIP, EXP, CP.')
  
  # Set up logging
  log_filename = 'boomerang-msd-calculation-dt-%f-N-%d-g-%s-%s' % (
    dt, N, args.gfactor, args.data_name)
  if args.free:
    log_filename = 'free-' + log_filename
  if args.out_name:
    log_filename = log_filename + ('-%s' % args.out_name)
  log_filename = './logs/' + log_filename + '.log'

  progress_logger = logging.getLogger('Progress Logger')
  progress_logger.setLevel(logging.INFO)
  # Add the log message handler to the logger
  logging.basicConfig(filename=log_filename,
                      level=logging.INFO,
                      filemode='w')
  sl = StreamToLogger(progress_logger, logging.INFO)
  sys.stdout = sl
  sl = StreamToLogger(progress_logger, logging.ERROR)
  sys.stderr = sl

  trajectory_file_names = []
  for k in range(1, args.n_runs+1):
    if data_name:
      if args.free:
        trajectory_file_names.append(
          'free-boomerang-trajectory-dt-%g-N-%s-scheme-%s-%s-%s.txt' % (
            dt, N, scheme, data_name, k))
      else:
        trajectory_file_names.append(
        'boomerang-trajectory-dt-%g-N-%s-scheme-%s-g-%s-%s-%s.txt' % (
            dt, N, scheme, args.gfactor, data_name, k))
    else:
      if args.free:
        trajectory_file_names.append(
          'free-boomerang-trajectory-dt-%g-N-%s-scheme-%s-%s.txt' % (
            dt, N, scheme, k))
      else:
        trajectory_file_names.append(
          'boomerang-trajectory-dt-%g-N-%s-scheme-%s-g-%s-%s.txt' % (
            dt, N, scheme, args.gfactor, k))

  ##########
  msd_runs = []
  ctr = 0
  for name in trajectory_file_names:
    ctr += 1
    data_file_name = os.path.join(DATA_DIR, 'boomerang', name)
    # Check correct timestep.
    params, locations, orientations = read_trajectory_from_txt(data_file_name)
    if (abs(float(params['dt']) - dt) > 1e-7):
      raise Exception('Timestep of data does not match specified timestep.')
    if int(params['n_steps']) != N:
      raise Exception('Number of steps in data does not match specified '
                      'Number of steps.')
    
    # Calculate MSD data (just an array of MSD at each time.)
    if args.point == 'COD':
      msd_data = calc_msd_data_from_trajectory(locations, orientations, 
                                               bm.calculate_boomerang_cod, dt, end,
                                               trajectory_length=trajectory_length)
    elif args.point == 'COH':
      msd_data = calc_msd_data_from_trajectory(locations, orientations, 
                                               bm.calculate_boomerang_coh, dt, end,
                                               trajectory_length=trajectory_length)
    elif args.point == 'TIP':
      msd_data = calc_msd_data_from_trajectory(locations, orientations, 
                                               calc_boomerang_tip, dt, end,
                                               trajectory_length=trajectory_length)
    elif args.point == 'CP':
      msd_data = calc_msd_data_from_trajectory(locations, orientations, 
                                               calc_boomerang_cp, dt, end,
                                               trajectory_length=trajectory_length)
    elif args.point == 'EXP':
      msd_data = calc_msd_data_from_trajectory(locations, orientations, 
                                               calc_boomerang_experimental, dt, end,
                                               trajectory_length=trajectory_length)
    # append to calculate Mean and Std.
    msd_runs.append(msd_data)
    print('Completed run %s of %s' % (ctr, len(trajectory_file_names)))

  mean_msd = np.mean(np.array(msd_runs), axis=0)
  std_msd = np.std(np.array(msd_runs), axis=0)/np.sqrt(len(trajectory_file_names))
  data_interval = int(end/dt/trajectory_length) + 1
  time = np.arange(0, len(mean_msd))*dt*data_interval

  msd_statistics = MSDStatistics(params)
  msd_statistics.add_run(scheme, dt, [time, mean_msd, std_msd])

  # Save MSD data with pickle.
  if args.out_name:
    if args.free:
      msd_data_file_name = os.path.join(
        DATA_DIR, 'boomerang',
        'free-boomerang-msd-dt-%s-N-%s-end-%s-scheme-%s-runs-%s-%s-%s.pkl' %
        (dt, N, end, scheme, len(trajectory_file_names), data_name,
         args.out_name))      
    else:
      msd_data_file_name = os.path.join(
        DATA_DIR, 'boomerang',
        'boomerang-msd-dt-%s-N-%s-end-%s-scheme-%s-g-%s-runs-%s-%s-%s.pkl' %
        (dt, N, end, scheme, args.gfactor, len(trajectory_file_names), data_name,
         args.out_name))
  else:
    if args.free:
      msd_data_file_name = os.path.join(
        DATA_DIR, 'boomerang',
        'free-boomerang-msd-dt-%s-N-%s-end-%s-scheme-%s-runs-%s-%s.pkl' %
        (dt, N, end, scheme, len(trajectory_file_names), data_name))
    else:
      msd_data_file_name = os.path.join(
        DATA_DIR, 'boomerang',
        'boomerang-msd-dt-%s-N-%s-end-%s-scheme-%s-g-%s-runs-%s-%s.pkl' %
        (dt, N, end, scheme, args.gfactor, len(trajectory_file_names), data_name))

  with open(msd_data_file_name, 'wb') as f:
    pickle.dump(msd_statistics, f)
  
  if args.profile:
    pr.disable()
    s = io.StringIO()
    sortby = 'cumulative'
    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    ps.print_stats()
    print(s.getvalue())
  
  
