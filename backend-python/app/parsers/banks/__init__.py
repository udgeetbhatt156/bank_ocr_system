"""Bank-specific parser implementations."""

from app.parsers.banks.peoplessouth import PeopleSouthParser
from app.parsers.banks.sofi import SofiParser
from app.parsers.banks.palmetto_state_bank import PalmettoStateBankParser
from app.parsers.banks.banc_first import BancFirstParser
from app.parsers.banks.timberland_bank import TimberlandBankParser
from app.parsers.banks.washington_trust_bank import WashingtonTrustBankParser

__all__ = [
    "PeopleSouthParser",
    "SofiParser",
    "PalmettoStateBankParser",
    "BancFirstParser",
    "TimberlandBankParser",
    "WashingtonTrustBankParser",
]
