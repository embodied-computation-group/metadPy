# Author: Nicolas Legrand <nicolas.legrand@cfin.au.dk>

import numbers
import os
import sys

from theano.compile.ops import OutputGuard
from metadPy.sdt import dprime, criterion
from metadPy.utils import discreteRatings, trials2counts
import numpy as np


def hmetad(
    data=None,
    nR_S1=None,
    nR_S2=None,
    stimuli=None,
    accuracy=None,
    confidence=None,
    nRatings=None,
    within=None,
    between=None,
    subject=None,
    nbins=4,
    padCells=False,
    padAmount=None,
    chains=3,
    tune=1000,
    draws=1000,
    cores=None,
    sample_model=True,
):
    """Estimate parameters of the Hierarchical Bayesian meta-d'

    Parameters
    ----------
    data : :py:class:`pandas.DataFrame` or None
        Dataframe. Note that this function can also directly be used as a
        Pandas method, in which case this argument is no longer needed.
    nR_S1 : 1d array-like, list, string or None
        Confience ratings (stimuli 1, correct and incorrect).
    nR_S2 : 1d array-like, list, string or None
        Confience ratings (stimuli 2, correct and incorrect).
    stimuli : string
        Name of the column containing the stimuli.
    accuracy : string
        Name of the columns containing the accuracy.
    confidence : string
        Name of the column containing the confidence ratings.
    nRatings : int
        Number of discrete ratings. If a continuous rating scale was used, and
        the number of unique ratings does not match `nRatings`, will convert to
        discrete ratings using :py:func:`metadPy.utils.discreteRatings`.
    within : string
        Name of column containing the within factor (condition comparison).
    between : string
        Name of column containing the between subject factor (group
        comparison).
    subject : string
        Name of column containing the subject identifier (only required if a
        within-subject or a between-subject factor is provided).
    nbins : int
        If a continuous rating scale was using, `nbins` define the number of
        discrete ratings when converting using
        :py:func:`metadPy.utils.discreteRatings`. The default value is `4`.
    padCells : boolean
        If `True`, each response count in the output has the value of padAmount
        added to it. Padding cells is desirable if trial counts of 0 interfere
        with model fitting. If False, trial counts are not manipulated and 0s
        may be present in the response count output. Default value for padCells
        is 0.
    padAmount : float
        The value to add to each response count if padCells is set to 1.
        Default value is 1/(2*nRatings)
    chains : int
        The number of chains to sample. Defaults to `3`.
    tune : int
        Number of iterations to tune. Defaults to `1000`.
    draws : int
        The number of samples to draw. Defaults to `1000`.

    Returns
    -------
    model : dict
        The fitted model.

    Examples
    --------
    1. Subject-level

    2. Group-level

    3. Repeated measures

    Notes
    -----
    This function will compute hierarchical Bayesian estimation of
    metacognitive efficiency as described in [1]_. The model can be fitter at
    the subject level, at the group level and can account for repeated measures
    by providing the corresponding `subject`, `between` and `within` factors.

    References
    ----------
    .. [1] Fleming, S.M. (2017) HMeta-d: hierarchical Bayesian estimation of
    metacognitive efficiency from confidence ratings, Neuroscience of
    Consciousness, 3(1) nix007, https://doi.org/10.1093/nc/nix007
    """
    modelScript = os.path.dirname(__file__) + "/models/"
    sys.path.append(modelScript)

    if nRatings is None:
        raise ValueError("You should provide the number of ratings")

    if data is None:
        if (nR_S1 is None) or (nR_S2 is None):
            raise ValueError(
                "If data is None, you should provide"
                " the nR_S1 and nR_S2 vectors instead."
            )
    else:
        if data[confidence].nunique() > nRatings:
            # If a continuous rating scale was used (if N unique ratings > nRatings)
            # transform confidence to discrete ratings
            print(
                "The confidence columns contains more unique values than nRatings",
                "The ratings are going to be discretized using discreteRatings",
            )
            new_ratings, out = discreteRatings(data[confidence].to_numpy(), nbins=nbins)
            data.loc[:, confidence] = new_ratings

    ###############
    # Subject level
    if (within is None) & (between is None) & (subject is None):

        if data is not None:
            nR_S1, nR_S2 = trials2counts(
                data=data,
                stimuli=stimuli,
                accuracy=accuracy,
                confidence=confidence,
                nRatings=nRatings,
                padCells=padCells,
                padAmount=padAmount,
            )

        pymcData = extractParameters(np.asarray(nR_S1), np.asarray(nR_S2))

        from subjectLevel import hmetad_subjectLevel

        output = hmetad_subjectLevel(
            pymcData,
            chains=chains,
            tune=tune,
            draws=draws,
            cores=cores,
            sample_model=sample_model,
        )

    #############
    # Group level
    elif (within is None) & (between is None) & (subject is not None):

        pymcData = preprocess_group(data)
        from groupLevel import hmetad_groupLevel

        output = hmetad_groupLevel(
            pymcData,
            chains=chains,
            tune=tune,
            draws=draws,
            cores=cores,
            sample_model=sample_model,
        )

    ###################
    # Repeated-measures
    elif (within is not None) & (between is None) & (subject is not None):

        pymcData = preprocess_rm1way(
            data, subject, within, stimuli, accuracy, confidence, nRatings
        )

        from rm1way import hmetad_rm1way

        output = hmetad_rm1way(
            pymcData,
            chains=chains,
            tune=tune,
            draws=draws,
            cores=cores,
            sample_model=sample_model,
        )

    else:
        raise ValueError("Invalid design specification provided. No model fitted.")

    if sample_model is True:
        model, trace = output
        return model, trace
    else:
        model = output
        return model


def extractParameters(nR_S1, nR_S2):
    """Extract rates and task parameters.

    Parameters
    ----------
    nR_S1, nR_S2 : 1d array-like or list
        Total number of responses in each response category, conditional on
        presentation of S1 and S2. e.g. if `nR_S1 = [100 50 20 10 5 1]`, then
        when stimulus S1 was presented, the subject had the following response
        counts:
            * responded S1, rating=3 : 100 times
            * responded S1, rating=2 : 50 times
            * responded S1, rating=1 : 20 times
            * responded S2, rating=1 : 10 times
            * responded S2, rating=2 : 5 times
            * responded S2, rating=3 : 1 time

    Return
    ------
    data : dict
        Dictionnary of rates and task parameters.

    See also
    --------
    hmetad
    """
    if isinstance(nR_S1, list):
        nR_S1 = np.array(nR_S1)
    if isinstance(nR_S2, list):
        nR_S2 = np.array(nR_S2)

    Tol = 1e-05
    nratings = int(len(nR_S1) / 2)

    # Adjust to ensure non-zero counts for type 1 d' point estimate
    adj_f = 1 / ((nratings) * 2)

    nR_S1_adj = nR_S1 + adj_f
    nR_S2_adj = nR_S2 + adj_f

    ratingHR, ratingFAR = [], []
    for c in range(1, int(nratings * 2)):
        ratingHR.append(sum(nR_S2_adj[c:]) / sum(nR_S2_adj))
        ratingFAR.append(sum(nR_S1_adj[c:]) / sum(nR_S1_adj))

    d1 = dprime(ratingHR[nratings - 1], ratingFAR[nratings - 1])
    c1 = criterion(ratingHR[nratings - 1], ratingFAR[nratings - 1])
    counts = np.hstack([nR_S1, nR_S2])

    # Type 1 counts
    N = sum(counts[: (nratings * 2)])
    S = sum(counts[(nratings * 2) : (nratings * 4)])
    H = sum(counts[(nratings * 3) : (nratings * 4)])
    M = sum(counts[(nratings * 2) : (nratings * 3)])
    FA = sum(counts[(nratings) : (nratings * 2)])
    CR = sum(counts[:(nratings)])

    # Data preparation for model
    data = {
        "d1": d1,
        "c1": c1,
        "counts": counts,
        "nratings": nratings,
        "Tol": Tol,
        "FA": FA,
        "CR": CR,
        "M": M,
        "H": H,
        "N": N,
        "S": S,
    }

    return data


def preprocess_group(data):
    """Preprocess group data."""
    pymcData = {
        "nSubj": data[subject].nunique(),
        "subID": np.arange(data[subject].nunique(), dtype="int"),
        "hits": [],
        "falsealarms": [],
        "s": [],
        "n": [],
        "counts": [],
        "nRatings": nRatings,
        "Tol": 1e-05,
        "cr": [],
        "m": [],
    }

    for sub in data[subject].unique():
        nR_S1, nR_S2 = trials2counts(
            data=data[data[subject] == sub],
            stimuli=stimuli,
            accuracy=accuracy,
            confidence=confidence,
            nRatings=nRatings,
        )

        this_data = extractParameters(nR_S1, nR_S2)
        pymcData["s"].append(this_data["S"])
        pymcData["n"].append(this_data["N"])
        pymcData["m"].append(this_data["M"])
        pymcData["cr"].append(this_data["CR"])
        pymcData["counts"].append(this_data["counts"])
        pymcData["hits"].append(this_data["H"])
        pymcData["falsealarms"].append(this_data["FA"])

    pymcData["s"] = np.array(pymcData["s"], dtype="int")
    pymcData["n"] = np.array(pymcData["n"], dtype="int")
    pymcData["m"] = np.array(pymcData["m"], dtype="int")
    pymcData["cr"] = np.array(pymcData["cr"], dtype="int")
    pymcData["counts"] = np.array(pymcData["counts"], dtype="int")
    pymcData["hits"] = np.array(pymcData["hits"], dtype="int")
    pymcData["falsealarms"] = np.array(pymcData["falsealarms"], dtype="int")
    pymcData["nRatings"] = 4
    pymcData["nSubj"] = data[subject].nunique()
    pymcData["subID"] = np.arange(20, dtype="int")
    pymcData["Tol"] = 1e-05

    return pymcData


def preprocess_rm1way(data, subject, within, stimuli, accuracy, confidence, nRatings):
    """Preprocess repeated measures data."""
    pymcData = {
        "nSubj": data[subject].nunique(),
        "subID": [],
        "nCond": data[within].nunique(),
        "condition": [],
        "hits": [],
        "falsealarms": [],
        "s": [],
        "n": [],
        "nRatings": nRatings,
        "Tol": 1e-05,
        "cr": [],
        "m": [],
    }
    pymcData["counts"] = np.zeros(
        (pymcData["nSubj"], pymcData["nCond"], pymcData["nRatings"] * 4)
    )
    pymcData["hits"] = np.zeros((pymcData["nSubj"], pymcData["nCond"]))
    pymcData["falsealarms"] = np.zeros((pymcData["nSubj"], pymcData["nCond"]))
    pymcData["s"] = np.zeros((pymcData["nSubj"], pymcData["nCond"]))
    pymcData["n"] = np.zeros((pymcData["nSubj"], pymcData["nCond"]))
    pymcData["m"] = np.zeros((pymcData["nSubj"], pymcData["nCond"]))
    pymcData["cr"] = np.zeros((pymcData["nSubj"], pymcData["nCond"]))
    pymcData["condition"] = np.zeros((pymcData["nSubj"], pymcData["nCond"]))
    pymcData["subID"] = np.zeros((pymcData["nSubj"], pymcData["nCond"]))
    pymcData["c1"] = np.zeros((pymcData["nSubj"], pymcData["nCond"]))
    pymcData["d1"] = np.zeros((pymcData["nSubj"], pymcData["nCond"]))

    for nSub, sub in enumerate(data[subject].unique()):
        for nCond, cond in enumerate(data[within].unique()):
            nR_S1, nR_S2 = trials2counts(
                data=data[(data[subject] == sub) & (data[within] == cond)],
                stimuli=stimuli,
                accuracy=accuracy,
                confidence=confidence,
                nRatings=nRatings,
            )

            this_data = extractParameters(nR_S1, nR_S2)
            pymcData["subID"][nSub, nCond] = nSub
            pymcData["condition"][nSub, nCond] = nCond
            pymcData["s"][nSub, nCond] = this_data["S"]
            pymcData["n"][nSub, nCond] = this_data["N"]
            pymcData["m"][nSub, nCond] = this_data["M"]
            pymcData["cr"][nSub, nCond] = this_data["CR"]
            pymcData["hits"][nSub, nCond] = this_data["H"]
            pymcData["falsealarms"][nSub, nCond] = this_data["FA"]
            pymcData["c1"][nSub, nCond] = this_data["c1"]
            pymcData["d1"][nSub, nCond] = this_data["d1"]
            pymcData["counts"][nSub, nCond, :] = this_data["counts"]

    pymcData["subID"] = np.array(pymcData["subID"], dtype="int")
    pymcData["condition"] = np.array(pymcData["condition"], dtype="int")
    pymcData["s"] = np.array(pymcData["s"], dtype="int")
    pymcData["n"] = np.array(pymcData["n"], dtype="int")
    pymcData["m"] = np.array(pymcData["m"], dtype="int")
    pymcData["cr"] = np.array(pymcData["cr"], dtype="int")
    pymcData["counts"] = np.array(pymcData["counts"], dtype="int")
    pymcData["hits"] = np.array(pymcData["hits"], dtype="int")
    pymcData["falsealarms"] = np.array(pymcData["falsealarms"], dtype="int")

    return pymcData
