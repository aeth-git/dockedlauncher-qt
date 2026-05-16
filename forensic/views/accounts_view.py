"""Configured accounts view."""
from .base_view import BaseTabView


class AccountsView(BaseTabView):
    TAB_NAME = "Accounts"
    COLUMNS = [
        ("type_label",   "Account Type"),
        ("username",     "Username / Email"),
        ("display_name", "Display Name"),
        ("account_type", "Type ID"),
        ("oauth_active", "OAuth Active"),
    ]
