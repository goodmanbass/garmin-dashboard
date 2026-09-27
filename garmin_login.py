"""One-time Garmin Connect login.

Run this yourself in a terminal window. It asks for your Garmin email and
password, exchanges them for OAuth tokens, and saves the tokens to
~/.garminconnect. Your password is never stored and never leaves this script.

After this runs once, garmin_pull.py works without any password for about a
year, at which point you just run this again.
"""

import getpass
import sys
from pathlib import Path

from garminconnect import Garmin

TOKENSTORE = Path.home() / ".garminconnect"


def main() -> int:
    print("Garmin Connect login")
    print("-" * 40)
    print(f"Tokens will be saved to: {TOKENSTORE}\n")

    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (hidden as you type): ")

    if not email or not password:
        print("\nEmail and password are both required.")
        return 1

    def prompt_mfa() -> str:
        return input("MFA code from your email/authenticator: ").strip()

    TOKENSTORE.mkdir(parents=True, exist_ok=True)
    client = Garmin(email=email, password=password, prompt_mfa=prompt_mfa)

    try:
        # Passing the tokenstore makes login() persist the OAuth tokens itself.
        client.login(str(TOKENSTORE))
    except Exception as exc:
        print(f"\nLogin failed: {exc}")
        return 1

    try:
        name = client.get_full_name()
    except Exception:
        name = "(name unavailable)"

    print(f"\nLogged in as {name}")
    print(f"Tokens saved to {TOKENSTORE}")
    print("\nDone. You can close this window and tell Claude it worked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
