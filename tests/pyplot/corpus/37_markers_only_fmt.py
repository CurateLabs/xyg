import numpy as np

import xyg.pyplot as plt

rng = np.random.default_rng(9)
y = rng.random(15)
plt.plot(y, "o")
plt.plot(y + 1, "x")
