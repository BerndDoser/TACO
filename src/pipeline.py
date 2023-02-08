#!/usr/bin/env python3

""" TACO pipline module """

import argparse
import subprocess
from pathlib import Path

import pandas as pd
import yaml
from codetiming import Timer

import taco
import csv

def get_kic_id(input_file):
    """ Returns the KIC identifier from raw data file """

    kic = float("nan")
    h = open(input_file, 'r')
    content = h.readlines()

    for line in content:
        if "KIC" in line:
            kic = line.split()[-1]

    return kic


def get_git_revision_short_hash() -> str:
    result = 'N/A'
    try:
        result = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
    except Exception:
        print('No git revision hash found.')
    return result


def pipeline(argv):
    """ TACO pipeline """

    t = Timer("total")
    t.start()

    if not argv.quiet:
        print(" ==========")
        print("    TACO")
        print(" ==========\n")
        print('Print level: ', argv.verbose)

    # Read pipeline settings
    with open(argv.settings_file, 'r', encoding="utf-8") as stream:
        settings = yaml.load(stream, Loader = yaml.Loader)

    if argv.verbose > 1:
        print("settings: ", settings)

    input_files = [f for f in Path(argv.input_directory).iterdir()
        if (f.is_file() and f.suffix == '.dat')]

    if not argv.quiet:
        print('Number of input files: ', len(input_files))

    # open a csv files to log the stars that have been processed + their flags
    path_to_file = 'stars.csv'
    path = Path(path_to_file)
    if path.is_file():
      print(f'The file {path_to_file} exists')
    else:
        with open('stars.csv', mode = 'w') as fstar:
            writer = csv.writer(fstar, delimiter = ',')
            writer.writerow(['ID', 'flag_numax', 'flag_mle_resolved','flag_02','flag_mle_mixed','flag_mle_final'])
        fstar.close()
        
    data = pd.read_csv('stars.csv')
    stars_done = data['ID'].tolist()
    # Loop over input directories
    for input_file in input_files:
        input_name = input_file.stem
        print('Current input name: ', input_name)
        if input_name in stars_done:
          print(f'This star has already been analysed and will not be redone')
        else:
            Path(argv.output_directory, input_name).mkdir(exist_ok = True)
            ts_raw = pd.read_csv(input_file, comment = '#', header = None, delim_whitespace = True)
            with open('stars.csv', mode = 'a') as fstar:
                writer = csv.writer(fstar, delimiter = ',')
                #set all flags to 1
                flag_numax = [1]
                flag_mle_resolved = [1]
                flag_02 = [1]
                flag_mle_mixed = [1]
                flag_mle_final = [1]

                # Set Kepler Input Catalogue (KIC) identification number and raw_data filename
                data = pd.DataFrame({"KIC": [get_kic_id(input_file)],
                                "raw_data": [input_name],
                                "git-rev-hash": [get_git_revision_short_hash()]})

                # 0) Filter
                print('0) Filter lightcurves')
                ts_filtered, data = taco.filter(ts_raw, data,
                    **settings['pipeline'][0]['filter'],
                    output_directory = Path(argv.output_directory, input_name))

                # 1) PDS
                print('1) Compute PDS')
                pds = taco.calc_pds(ts_filtered, **settings['pipeline'][1]['pds'],
                    output_directory = Path(argv.output_directory, input_name))

                # 2) Oversampled PDS
                print('2) Compute oversampled PDS')
                oversampled_pds = taco.calc_pds(ts_filtered, **settings['pipeline'][2]['oversampled_pds'],
                    output_directory = Path(argv.output_directory, input_name))
                
                # Set Nyquist frequency
                data["nuNyq"] = pds["frequency"].iloc[-1]

                # 3) Estimate numax
                print('3) Estimate numax')
                data, flag_numax = taco.numax_estimate(pds, data,
                    **settings['pipeline'][3]['numax_estimate'])
                    
                data.to_csv(Path(argv.output_directory, input_name, "data.csv"), index = False)

                if flag_numax[0] == 0.0:
                    # 4) Background fit
                    print('4) Fit background')
                    pds_bgr, oversampled_pds_bgr, data = taco.background_fit(
                        pds, oversampled_pds, data,
                        **settings['pipeline'][4]['background_fit'])
                
                    data.to_csv(Path(argv.output_directory, input_name, "data.csv"), index = False)
                    pds_bgr.to_csv(Path(argv.output_directory, input_name, "pds_bgr.csv"), index = False)

                
                    # 5) Find peaks
                    print('5) Find resolved peaks')
                    peaks = taco.peak_find(pds_bgr, oversampled_pds_bgr, data,
                        **settings['pipeline'][5]['peak_find'])
    
                    # 6) MLE
                    if (len(peaks.frequency)) >= 1:
                        print('6) MLE fit peaks')
                        peaks_mle, flag_mle_resolved, data = taco.peaks_mle(pds_bgr, peaks, data,
                            **settings['pipeline'][6]['peaks_mle'])
                        data.to_csv(Path(argv.output_directory, input_name, "data.csv"), index = False)
                        peaks_mle.to_csv(Path(argv.output_directory, input_name, "peaks_mle.csv"), index = False)
            
                        # 7) Bag mode id02
                        if (((len(peaks_mle.frequency)) >= 3) and (flag_mle_resolved[0] == 0.0)):
                            print('7) Identify 0,2 modes')
                            peaks_mle, flag_02, data = taco.peak_bag_mode_id02(pds_bgr, peaks_mle, data)
                            data.to_csv(Path(argv.output_directory, input_name, "data.csv"), index = False)
                            peaks_mle.to_csv(Path(argv.output_directory, input_name, "peaks_mle.csv"), index = False)
        
                            # 8) Find mixed peaks
                            if flag_02[0] == 0.0:
                                print('8) Find mixed peaks')
                                mixed_peaks = taco.peak_find(
                                    pds_bgr, oversampled_pds_bgr, data, peaks = peaks_mle, removel02 = True,
                                    **settings['pipeline'][7]['peak_find'])
                                data.to_csv(Path(argv.output_directory, input_name, "data.csv"), index = False)
                                peaks_mle.to_csv(Path(argv.output_directory, input_name, "peaks_mle.csv"), index = False)

                                # 9) MLE with mixed peaks
                                print('9) MLE fit mixed peaks')
                                mixed_peaks, flag_mle_mixed, data = taco.peaks_mle(
                                    pds_bgr, peaks_mle, data, mixed_peaks = mixed_peaks, removel02 = True,
                                    **settings['pipeline'][8]['peaks_mle'])
                                data.to_csv(Path(argv.output_directory, input_name, "data.csv"), index = False)
                                peaks_mle.to_csv(Path(argv.output_directory, input_name, "peaks_mle.csv"), index = False)

                                # 10) Final fit
                                if (flag_mle_mixed[0] == 0.0):
                                    print('10) Final fit all peaks')
                                    mixed_peaks, flag_mle_final, data = taco.peaks_mle(pds_bgr, peaks_mle, data,
                                        mixed_peaks = mixed_peaks, finalfit = True,
                                        **settings['pipeline'][9]['peaks_mle'])
                                    data.to_csv(Path(argv.output_directory, input_name, "data.csv"), index = False)
                                    peaks_mle.to_csv(Path(argv.output_directory, input_name, "peaks_mle.csv"), index = False)

                                    # 11) Bag_period_spacing
                                    if (flag_mle_final[0] == 0.0):
                                        print('11) Find period spacing')
                                        pds_bgr, mixed_peaks, data = taco.peak_bag_period_spacing(pds_bgr, mixed_peaks, data,
                                            **settings['pipeline'][10]['peak_bag_period_spacing'])
                                        data.to_csv(Path(argv.output_directory, input_name, "data.csv"), index = False)
                                        peaks_mle.to_csv(Path(argv.output_directory, input_name, "peaks_mle.csv"), index = False)

                # Write final results
                writer.writerow([input_name, flag_numax[0], flag_mle_resolved[0], flag_02[0], flag_mle_mixed[0], flag_mle_final[0]])
            fstar.close()
    t.stop()
    

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="TACO pipeline")
    parser.add_argument('--input_directory', '-i', default='.',
                        help="Input directory of processable raw data (default = '.').")
    parser.add_argument('--output_directory', '-o', default='.',
                        help="Output directory for resulting data (default = '.').")
    parser.add_argument('--settings-file', '-s', default='pipeline_settings.yaml',
                        help="File with pipeline settings in Yaml (default = 'pipeline_settings.yaml').")
    parser.add_argument('--verbose', '-v', default=0, action='count',
                        help="Print level.")
    parser.add_argument('--quiet', '-q', action='store_true',
                        help="No output")

    pipeline(parser.parse_args())
