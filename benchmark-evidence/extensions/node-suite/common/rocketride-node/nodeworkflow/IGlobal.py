"""Study-only RocketRide node lifecycle."""

from rocketlib import IGlobalBase


class IGlobal(IGlobalBase):
    def beginGlobal(self):
        pass

    def endGlobal(self):
        pass
