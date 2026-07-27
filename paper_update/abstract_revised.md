# Abstract — revised sentences

Only the result sentences change. Replacements in context:

> The results show that price-responsive and learning drivers both cut peak
> congestion inside the cordon by about a quarter (23.0 % and 23.8 %), and the
> charge does not push congestion onto the surrounding roads: the cordon
> boundary and the peripheral network fall together with the interior.
> Expectation-based drivers barely respond to the price at all, changing peak
> congestion by 0.2 %, because they read yesterday's congestion rather than
> today's fee.

## What changed and why

1. "about a fifth" becomes "about a quarter". Both rules now give 23 % to 24 %
   on the calibrated model.
2. **"behave erratically from day to day" has been removed.** On the
   uncalibrated model the El Farol rule produced a large alternate-day
   oscillation, with a day-to-day standard deviation of peak V/C around 0.24.
   After calibration that oscillation disappears: the standard deviation is
   0.021, against 0.015 for exponential decay and 0.013 for Q-learning. The
   oscillation was a property of an overloaded network, not of the attendance
   game, and a five-seed replication confirms the null. The rule is now
   *unresponsive*, not *erratic*, and the abstract should say so.
3. The displacement claim is stated with its evidence, since the calibrated
   runs record the cordon boundary and periphery explicitly, which the earlier
   runs did not.

If the flat NZ$2 charge is dropped (no calibrated run exists), the phrase
"one proposed time-of-use (ToU) cordon charge" already covers the design and
needs no change.
