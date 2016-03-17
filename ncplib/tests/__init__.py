import os
from hypothesis import settings


settings.register_profile("ci", settings())
settings.register_profile("dev", settings(timeout=0.5, min_satisfying_examples=1))
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))
