# Previously __main__.py was named main.py. This file is left here to not break installations that still use main.py
# as the entry-point.
# TODO Remove this file once everyone has reinstalled switch

# This import is required to maintain compatibility with previous installations.
from switch_model.__main__ import main
