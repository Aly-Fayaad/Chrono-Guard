"""Sleep, circadian and alertness analysis (vendored from the crew-health project).

Only the modules needed by :func:`crew_health.pipeline.analyze` are vendored;
the original MIT licence is kept in ``LICENSE`` next to this file.

The KSS output is a group-level prediction from the published three-process
model (Ingre et al. 2014). It is not individually calibrated, not validated in
microgravity, and not a clinical or operational decision threshold.
"""
