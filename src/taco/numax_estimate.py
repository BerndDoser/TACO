import os

import rpy2.robjects as ro
from rpy2.robjects import pandas2ri
from rpy2.robjects.conversion import localconverter
from rpy2.robjects.packages import STAP


def numax_estimate(pds, variance, nyquist, filterwidth=0.2):
    """
    Make a rough numax estimation using the periodogram, the variance of the time-series
    and the Nyquist frequency.

    Parameters:
        pds(pandas.DataFrame):Periodogram
            Columns:
                Name: frequency, dtype: float[micro-Hertz]
                Name: power, dtype: float
        variance(float):Variance of the time-series
        nyquist(float):Nyquist frequency
        filterwidth(float):The width of the log-median filter used to remove the background
                           for the wavelet numax estimation
    """

    with open(os.path.join(os.path.dirname(__file__),'numax_estimate.R'), 'r') as f:
        numax_estimate = STAP(f.read(), "numax_estimate_r")

        with localconverter(ro.default_converter + pandas2ri.converter):
            r_pds = ro.conversion.py2rpy(pds)
            return numax_estimate.numax_estimate_r(r_pds, variance, nyquist, filterwidth)
            #return numax_var, numax_CWTMexHat, numax_Morlet, numax0
