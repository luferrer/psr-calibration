import numpy as np
from scipy.special import softmax
import torch
from psrcal.utils import onehot_encode, check_label
import psrcal.calibration as psrcalcal
import matplotlib.pyplot as plt

def CostFunction(log_probs, labels, C=None, norm=True):

    if C is None:
        # Use the standard 0-1 cost matrix
        C = 1 - np.eye(log_probs.shape[1])    

    # Normalize the cost matrix
    C -= C.min(axis=0)
    C = torch.tensor(C, dtype=log_probs.dtype)

    def _decisions(p):
        return (p @ C.T).argmin(axis=-1)

    probs = torch.exp(log_probs)
    costs = C[_decisions(probs),labels]
        
    if norm:
        priors = (torch.bincount(labels)/float(labels.shape[0])).type(dtype=C.dtype)
        naive_costs = C[_decisions(priors), labels]
        prior_cost = torch.mean(naive_costs)
    else:
        prior_cost = 1.0

    return torch.mean(costs)/prior_cost


def LogLoss(log_probs, labels, norm=True, priors=None):
        
    priors, weights = _get_priors_and_weights(labels, priors)
    norm_factor = LogLoss(torch.log(priors.expand(log_probs.shape[0],-1)), labels, norm=False, priors=priors) if norm else 1.0

    # The loss on each sample is weighted by the inverse of the
    # frequency of the corresponding class in the test data
    # times the external prior
    ii = torch.arange(len(labels))
    losses = -log_probs[ii, labels]
    wlosses = weights*losses
    # The line below is to turn to 0 potential infinite losses when the weight is 0.
    wlosses[weights==0] = 0
    score  = torch.mean(wlosses)

    return score / norm_factor


def LogLossSE(log_probs, ref_log_probs, norm=True):
        
    if norm:
        priors = torch.mean(torch.exp(ref_log_probs), axis=0)
        prior_entropy = -torch.sum(priors * torch.log(priors))
    else:
        prior_entropy = 1.0

    return torch.mean(torch.sum(-torch.exp(ref_log_probs) * log_probs, axis=1))/ prior_entropy



def Brier(log_probs, labels, norm=True, priors=None):
        
    priors, weights = _get_priors_and_weights(labels, priors)
    norm_factor = Brier(torch.log(priors.expand(log_probs.shape[0],-1)), labels, norm=False, priors=priors) if norm else 1.0


    # The loss on each sample is weighted by the inverse of the
    # frequency of the corresponding class in the test data
    # times the external prior
    probs         = torch.exp(log_probs)
    labels_onehot = onehot_encode(labels, n_classes=probs.shape[-1])
    losses        = (labels_onehot-probs)**2
    score         = torch.mean(torch.atleast_2d(weights).T*losses)

    return score / norm_factor


def CalLossLogLoss(log_probs, cal_log_probs, targets, priors=None):

    raw = LogLoss(log_probs, targets, priors)
    cal = LogLoss(cal_log_probs, targets, priors)

    return (raw-cal)/raw*100


def CalLossBrier(log_probs, cal_log_probs, targets, priors=None):

    raw = Brier(log_probs, targets, priors)
    cal = Brier(cal_log_probs, targets, priors)

    return (raw-cal)/raw*100


def _get_priors_and_weights(labels, priors):

    data_priors = torch.bincount(labels)/float(labels.shape[0])
    if priors is None:
        priors = data_priors
        weights = torch.tensor(1.0)
    else:
        weights = priors[labels]/data_priors[labels] 

    return priors, weights


def ECE(log_probs, target, M=15, return_values=False):
    """"Computes ECE score as defined in https://arxiv.org/abs/1706.04599"""

    probs = torch.exp(log_probs)

    N = probs.shape[0]

    if probs.ndim>1:
        confs, preds = torch.max(probs, axis=1)
    else:
        confs = probs
        preds = probs >= 0.5

    # Generate intervals
    limits = np.linspace(0, 1, num=M+1)
    lows, highs = limits[:-1], limits[1:]
    ece = 0
    ave_accs = []
    ave_confs = []
    counts = []
    limits_used = []
    for low, high in zip(lows, highs):
        ix = (low < confs) & (confs <= high)
        n = torch.sum(ix)
        if n==0:
            continue
        curr_preds = preds[ix]
        curr_confs = confs[ix]
        curr_target = target[ix]
        ave_acc  = torch.mean((curr_preds == curr_target).type(dtype=probs.dtype))
        ave_conf = torch.mean(curr_confs)
        ave_accs.append(ave_acc.detach().numpy())
        ave_confs.append(ave_conf.detach().numpy())
        counts.append(n.detach().numpy())
        limits_used.append([low, high])
        ece += n*torch.abs(ave_conf-ave_acc)

    if return_values:
        return ece * 100/N, np.array(ave_accs), np.array(ave_confs), np.array(counts), limits_used
    else:
        return ece * 100/N


def ECE_v2(log_probs, target, M=15):
    """ Computes the multi-class ECE using an alternative expression that makes it
    evident that the ECE is doing calibration of confidences then computing
    distance between the calibrated and original binned confidences. This gives
    identical results to the ECE method above."""

    log_confs, preds = torch.max(log_probs, axis=1)

    # Map the multi-class problem into a new binary problem of deciding whether 
    # the system made the correct prediction or not
    log_probs2 = log_confs
    target = preds == target

    # Calibrate the scores with histogram binning, training on test data (ie, cheating)
    log_probs2_cal, params = psrcalcal.calibrate(log_probs2, target, log_probs2, psrcalcal.HistogramBinningCal)    
    probs2_cal = torch.exp(log_probs2_cal)
    probs2_binned = params[0]

    # Compute the average absolute difference between those two scores
    return torch.mean(torch.abs(probs2_cal-probs2_binned)) * 100


def ECEbin(log_probs, target, M=15, return_values=False, l2norm=False):
    """"Computes the binary ECE score"""

    probs = torch.exp(log_probs)
    N = probs.shape[0]
    assert probs.shape[1]==2
    post2 = probs[:,1]
    target = target.double()

    # Generate intervals
    limits = np.linspace(0, 1, num=M+1)
    lows, highs = limits[:-1], limits[1:]
    ece = 0
    prop2s = []
    avep2s = []
    counts = []
    limits_used = []
    for low, high in zip(lows, highs):
        ix = (low < post2) & (post2 <= high)
        n = torch.sum(ix)
        if n==0:
            continue
        curr_post = post2[ix]
        curr_target = target[ix]
        avep2 = torch.mean(curr_post)
        prop2 = torch.mean(curr_target)
        avep2s.append(avep2.detach().numpy())
        prop2s.append(prop2.detach().numpy())
        counts.append(n.detach().numpy())
        limits_used.append([low, high])
        if l2norm:
            ece += n*(avep2-prop2)**2
        else:
            ece += n*torch.abs(avep2-prop2)

    if return_values:
        return ece * 100/N, np.array(prop2s), np.array(avep2s), np.array(counts), limits_used
    else:
        return ece * 100/N


def ECEbin_v2(log_probs, target, M=15):
    """"Computes the binary ECE using an alternative expression
    that makes it evident that the ECE is doing calibration and 
    then computing distance between the calibrated and original
    binned scores. This gives identical results to the ECEbin
    method above."""

    assert log_probs.shape[1]==2
    log_probs2 = log_probs[:,1]

    # Calibrate the scores with histogram binning, training on test data (ie, cheating)
    log_probs2_cal, params = psrcalcal.calibrate(log_probs2, target, log_probs2, psrcalcal.HistogramBinningCal)    
    probs2_cal = torch.exp(log_probs2_cal)
    probs2_binned = params[0]

    # Compute the average absolute difference between those two scores
    return torch.mean(torch.abs(probs2_cal-probs2_binned)) * 100


def plot_reliability_diagram(ys, xs, counts, limits, outfile=None, title='', figsize=None):
    """
    On the left, a reliability diagram which contains exactly the information used to compute ECE
    On the right, the standard reliability diagram.
    """
    if figsize is None:
        figsize = (9,3)
    fig, [ax1, ax2] = plt.subplots(1,2,figsize=figsize)

    gaps = np.abs(xs-ys)
    frac = counts/np.sum(counts)

    ax2.plot(xs, ys, "-*", label="freq_class2")
    ax2.plot(xs, gaps, "-*", label="gap = abs(freq_class2-ave_post_class2)")
    ax2.plot(xs, frac, "-*", label="fraction_of_samples = n/N")
    ax2.plot(xs, frac * gaps, "-*", label="fraction_of_samples * gap")
    ax2.plot([0,1],[0,1],':k')
    ax2.set_xlabel("ave_post_class2")
    ax2.set_ylim(0,1)
    ax2.set_xlim(0,1)
    ax2.legend(bbox_to_anchor=(1, 1))
    ece = np.sum(frac * gaps) * 100

    lows = np.array(limits)[:,0]
    highs = np.array(limits)[:,1]
    ax1.bar(lows,ys, width=highs-lows, align='edge', edgecolor='k')
    ax1.plot([0,1], [0,1], 'k:')
    ax1.set_xlim(0,1)
    ax1.set_ylim(0,1)
    ax1.set_xlabel("binned_post_class2")
    ax1.set_ylabel("freq_class2")
    ax1.set_title(f"{title} (ECE={ece:.1f})")
    
    plt.tight_layout()
    if outfile is not None:
        plt.savefig(outfile)


def shift(loss, off):
    K = off.shape[0]
    eof = torch.exp(off)
    So = K**0.5 * eof/eof.norm()

    def shifted_loss(log_probs, labels):
        label = check_label(labels, log_probs.shape[-1])
        qs = torch.softmax(log_probs + off, dim=1)
        return loss(torch.log(qs), label) @ So.reshape(-1, 1)

    return shifted_loss

