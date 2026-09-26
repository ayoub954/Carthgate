"""Provider registry (order matters: references before dependent sources)."""
from __future__ import annotations

from .commerce import AuthorizedCommerceProvider, SocialCommerceProvider
from .comtrade import ComtradeProvider
from .ins import INSDataProvider
from .institutional import CustomsProvider, RNEProvider, SINDAProvider, TariffProvider
from .reference import CountryReferenceProvider, EntryPointProvider, GovernorateProvider, HSNomenclatureProvider
from .worldbank import WorldBankProvider


def all_providers():
    return [
        CountryReferenceProvider(),
        HSNomenclatureProvider(),
        GovernorateProvider(),
        EntryPointProvider(),
        INSDataProvider(),
        ComtradeProvider(),
        WorldBankProvider(),
        AuthorizedCommerceProvider(),
        SocialCommerceProvider(),
        CustomsProvider(),
        SINDAProvider(),
        RNEProvider(),
        TariffProvider(),
    ]
