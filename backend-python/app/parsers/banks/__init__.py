"""Bank-specific parser implementations."""

from app.parsers.banks.peoplessouth import PeopleSouthParser
from app.parsers.banks.sofi import SofiParser
from app.parsers.banks.palmetto_state_bank import PalmettoStateBankParser
from app.parsers.banks.banc_first import BancFirstParser
from app.parsers.banks.timberland_bank import TimberlandBankParser
from app.parsers.banks.washington_trust_bank import WashingtonTrustBankParser
from app.parsers.banks.indiana_members_cu import IndianaMembersCUParser
from app.parsers.banks.forbright import ForbrightBankParser
from app.parsers.banks.wayne_bank import WayneBankParser
from app.parsers.banks.first_kansas_bank import FirstKansasBankParser
from app.parsers.banks.lake_michigan_credit_union import LakeMichiganCreditUnionParser
from app.parsers.banks.mercury_bank import MercuryBankParser
from app.parsers.banks.exchange_bank import ExchangeBankParser
from app.parsers.banks.fulton_bank import FultonBankParser
# from app.parsers.banks.first_service_cu import FirstServiceCUParser

__all__ = [
    "PeopleSouthParser",
    "SofiParser",
    "PalmettoStateBankParser",
    "BancFirstParser",
    "TimberlandBankParser",
    "WashingtonTrustBankParser",
    "IndianaMembersCUParser",
    "ForbrightBankParser",
    "WayneBankParser",
    "FirstKansasBankParser",
    "LakeMichiganCreditUnionParser",
    "MercuryBankParser",
    "ExchangeBankParser",
    "FultonBankParser",
    # "FirstServiceCUParser",
]

